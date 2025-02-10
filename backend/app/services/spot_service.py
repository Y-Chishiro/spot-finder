from typing import List, Dict, Any, AsyncGenerator
from fastapi import HTTPException, Request
from app.core.config import get_settings
from app.models.spot import (
    TextSearchQuery, PlaceResult, NewsArticle,
    PlaceWithNews, SpotSeekState, SpotSearchResponse
)
import httpx, json
from datetime import datetime, timezone, timedelta

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END

settings = get_settings()


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class SpotService:
    def __init__(self):
        self.maps_api_key = settings.GOOGLE_MAPS_API_KEY
        self.custom_search_api_key = settings.CUSTOM_SEARCH_API_KEY
        self.custom_search_cx = settings.CUSTOM_SEARCH_CX

        # Geminiモデルの初期化
        self.model = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash-002",
            temperature=0
        )

        # ワークフローグラフの構築
        self.workflow = self._build_workflow()

    def _build_workflow(self) -> StateGraph:
        # グラフの作成
        workflow = StateGraph(SpotSeekState)

        # ノードの追加
        workflow.add_node("generate_query", self._generate_query_node)
        workflow.add_node("search_spots", self._search_spots_node)
        workflow.add_node("get_place_details", self._get_place_details_node)
        workflow.add_node("get_place_news", self._get_place_news_node)
        workflow.add_node("rank_places", self._rank_places_node)
        workflow.add_node("generate_summary", self._generate_summary_node)

        # エントリーポイントの定義
        workflow.set_entry_point("generate_query")

        # エッジの定義
        workflow.add_edge("generate_query", "search_spots")
        workflow.add_edge("search_spots", "get_place_details")
        workflow.add_edge("get_place_details", "get_place_news")
        workflow.add_edge("get_place_news", "rank_places")
        workflow.add_edge("rank_places", "generate_summary")
        workflow.add_edge("generate_summary", END)

        return workflow.compile()

    async def _generate_query_node(self, state: SpotSeekState) -> Dict[str, Any]:
        user_request = state.user_request

        prompt = ChatPromptTemplate.from_messages([
            ("system", """
あなたはユーザに変わってユーザのお出かけの要望をヒアリングし、GoogleMapのTextSearchAPIに投げる適切なクエリを作る必要があります。

textQuery作成は以下のステップで作成する！！これは絶対に守ること！！！
1. humanの入力を分析し、キーワードを3つ抽出する。短い単語で区切る。
2. そのキーワードをスペースを挟んで並べる
3. その文章をtextQueryとする。

例：
user_request=神田でラーメン食べたい
textQuery=神田 ラーメン

languageCode='ja'
pageSize=5

出力前に、以下を満たしているか、必ず確認すること。
・textQueryは2個か3個の名詞を半角スペース区切りで繋いだ文章とする。
            """),
            ("human", f"{user_request}")
        ])

        chain = prompt | self.model.with_structured_output(TextSearchQuery)
        query = await chain.ainvoke({})

        return {"query": query}

    async def _search_spots_node(self, state: SpotSeekState) -> Dict[str, Any]:
        query = state.query

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.maps_api_key,
            "X-Goog-FieldMask": "places.id"
        }

        data = query.model_dump(exclude_none=True)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers=headers,
                json=data
            )

            if response.status_code == 200:
                result = response.json()
                place_ids = [place["id"] for place in result.get("places", [])]
                return {"candidate_place_ids": place_ids}
            else:
                raise Exception(f"Places API Error: {response.text}")

    async def _get_place_details_node(self, state: SpotSeekState) -> Dict[str, Any]:
        places = []
        for place_id in state.candidate_place_ids:
            params = {
                "place_id": place_id,
                "key": self.maps_api_key,
                "language": "ja"
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params=params
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get("status") == "OK":
                        place = PlaceResult.model_validate(result["result"])
                        places.append(place)

        return {"candidate_places": places}

    async def _get_place_news_node(self, state: SpotSeekState) -> Dict[str, Any]:
        enriched_places = []
        for place in state.candidate_places:
            query = f"{place.name} ニュース"
            params = {
                "key": self.custom_search_api_key,
                "cx": self.custom_search_cx,
                "q": query,
                "num": 10
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=params
                )

                if response.status_code == 200:
                    result = response.json()
                    news_articles = []
                    for item in result.get("items", []):
                        pagemap = item.get("pagemap", {})
                        metatags_list = pagemap.get("metatags", [])
                        for meta in metatags_list:
                            if "og:title" in meta:
                                try:
                                    article = NewsArticle.model_validate(meta)
                                    news_articles.append(article)
                                except Exception as e:
                                    print(f"News parsing error: {e}")
                                break

                    enriched = PlaceWithNews(
                        place=place,
                        news_articles=news_articles
                    )
                    enriched_places.append(enriched)

        return {"enriched_places": enriched_places}

    async def _rank_places_node(self, state: SpotSeekState) -> Dict[str, Any]:
        places = state.enriched_places
        calculated_score = 10

        for place in places:
            place.relevance_score = calculated_score
            calculated_score = calculated_score - 1

        sorted_places = sorted(
            places,
            key=lambda x: x.relevance_score or 0,
            reverse=True
        )

        return {"enriched_places": sorted_places}

    def _prepare_summary_prompt(self, state: SpotSeekState) -> str:
        """サマリー生成用のプロンプトを構築"""
        prompt_text = f"""
    さて、あなたはお出かけ先を探そうとする友人を手伝おうとしています。
    あなたの友人は、「{state.user_request}」という要望を持っています。

    あなたの仕事は、その友人の要望に応えることです。
    お店探しというステップは難しく、最終的にユーザが納得しないといけません。
    そのためにはユーザの要望にどれだけ合致しているかももちろんですが、レビューが良いことや、例えばスポットがニュースに取り上げられていることも重要な手掛かりとなります。
    どうすればユーザが自分の意思決定に満足度を持てるかを常に注意しながら、スポットをオススメする文言を考えてください。

    そこで、あなたは以下のステップを踏んで情報探しをすることにしました。
    ・まず、お題をもとにGoogleMapでスポットを検索します。
    ・上位のスポットについて、口コミの点数や件数、上位レビュー5件を確認します。
    ・また、スポットの名前でニュース記事についても検索します。
    ・これらの情報をもとに、候補のスポットをオススメ順に並び替えて、5点満点で評価しながらおすすめの文言を伝えます。

    今回、GoogleMapでは{len(state.enriched_places)}件のスポットが見つかっています。
    それぞれの情報を以下に送ります。
    """

        for i, place in enumerate(state.enriched_places, 1):
            prompt_text += f"""
    スポット候補{i}件目：{place.place.name}
    レビューの点数（5点満点）：{place.place.rating}
    レビューの件数：{place.place.user_ratings_total}
    """

            for j, review in enumerate(place.place.reviews or [], 1):
                prompt_text += f"レビュー{j}件目：{review.author_name}さん、評価は{review.rating}点、レビュー内容は次のとおり。{review.text}\n"

            for j, news in enumerate(place.news_articles, 1):
                prompt_text += f"記事{j}件目：「{news.site_name}」というサイトが「{news.title}」というタイトルの記事。概要は「{news.description}」。\n"

            prompt_text += "\n"

        prompt_text += f"""
    最後に、ユーザからの要望を改めて伝えます。
    「{state.user_request}」
    これまでの情報をもとに、どのスポットがユーザの希望を満たすかどうかを踏まえた上で、総合的な評価コメントを書いてください。
    得られた情報だけではユーザの希望を満たすかどうかわからないときは、素直にそう書いてください。
    自信満々で回答できるときは、自信満々に回答してください。
    """

        return prompt_text

    async def _generate_summary_node(self, state: SpotSeekState) -> Dict[str, Any]:
        prompt_text = self._prepare_summary_prompt(state)
#         prompt_text = f"""
# さて、あなたはお出かけ先を探そうとする友人を手伝おうとしています。
# あなたの友人は、「{state.user_request}」という要望を持っています。

# あなたの仕事は、その友人の要望に応えることです。
# お店探しというステップは難しく、最終的にユーザが納得しないといけません。
# そのためにはユーザの要望にどれだけ合致しているかももちろんですが、レビューが良いことや、例えばスポットがニュースに取り上げられていることも重要な手掛かりとなります。
# どうすればユーザが自分の意思決定に満足度を持てるかを常に注意しながら、スポットをオススメする文言を考えてください。

# そこで、あなたは以下のステップを踏んで情報探しをすることにしました。
# ・まず、お題をもとにGoogleMapでスポットを検索します。
# ・上位のスポットについて、口コミの点数や件数、上位レビュー5件を確認します。
# ・また、スポットの名前でニュース記事についても検索します。
# ・これらの情報をもとに、候補のスポットをオススメ順に並び替えて、5点満点で評価しながらおすすめの文言を伝えます。

# 今回、GoogleMapでは{len(state.enriched_places)}件のスポットが見つかっています。
# それぞれの情報を以下に送ります。
# """

#         for i, place in enumerate(state.enriched_places, 1):
#             prompt_text += f"""
# スポット候補{i}件目：{place.place.name}
# レビューの点数（5点満点）：{place.place.rating}
# レビューの件数：{place.place.user_ratings_total}
# """

#             for j, review in enumerate(place.place.reviews or [], 1):
#                 prompt_text += f"レビュー{j}件目：{review.author_name}さん、評価は{review.rating}点、レビュー内容は次のとおり。{review.text}\n"

#             for j, news in enumerate(place.news_articles, 1):
#                 prompt_text += f"記事{j}件目：「{news.site_name}」というサイトが「{news.title}」というタイトルの記事。概要は「{news.description}」。\n"

#             prompt_text += "\n"

#         prompt_text += f"""
# 最後に、ユーザからの要望を改めて伝えます。
# 「{state.user_request}」
# これまでの情報をもとに、どのスポットがユーザの希望を満たすかどうかを踏まえた上で、総合的な評価コメントを書いてください。
# 得られた情報だけではユーザの希望を満たすかどうかわからないときは、素直にそう書いてください。
# 自信満々で回答できるときは、自信満々に回答してください。
# """

        prompt = ChatPromptTemplate.from_template("{text}")
        chain = prompt | self.model | StrOutputParser()
        summary = await chain.ainvoke({"text": prompt_text})

        # print(summary)

        return {"summary": summary}

    async def search_and_summarize(self, user_request: str) -> SpotSearchResponse:
        # 初期状態の作成
        initial_state = SpotSeekState(user_request=user_request)

        try:
            # ワークフローの実行
            final_state = await self.workflow.ainvoke(initial_state)

            # final_stateの内容をデバッグ出力
            # print("Final state:", final_state)
            print("summary:", final_state.get("summary", ""))

            return SpotSearchResponse(
                places=final_state["enriched_places"],
                summary=final_state.get("summary", "")  # get()を使ってデフォルト値を設定
            )
        except Exception as e:
            print(f"Error in workflow: {e}")
            # エラーの詳細を確認するためにfinal_stateの内容を出力
            print(f"Final state content: {final_state if 'final_state' in locals() else 'Not available'}")
            raise

    ################# ストリーミング用のメソッド #################

    async def preprocess_search(self, user_request: str) -> Dict[str, Any]:
        """前処理：スポット情報の取得"""
        # 既存のワークフローの一部を実行
        initial_state = SpotSeekState(user_request=user_request)
        state = initial_state

        # generate_queryからrank_placesまでを実行
        workflow_steps = {
            "generate_query": self._generate_query_node,
            "search_spots": self._search_spots_node,
            "get_place_details": self._get_place_details_node,
            "get_place_news": self._get_place_news_node,
            "rank_places": self._rank_places_node
        }

        for step_name, step_func in workflow_steps.items():
            result = await step_func(state)
            for key, value in result.items():
                setattr(state, key, value)

        return {
            "places": state.enriched_places,
            "user_request": user_request,
            "state": state
        }

    async def stream_llm_summary(self, search_results: Dict[str, Any], request: Request) -> AsyncGenerator[str, None]:
        """LLMサマリーのストリーミング生成"""
        try:
            # 初期レスポンスを生成
            initial_response = {
                "type": "places",
                "content": {
                    "places": [place.dict() for place in search_results["places"]]
                }
            }
            yield f"data: {json.dumps(initial_response, cls=DateTimeEncoder, ensure_ascii=False)}\n\n"

            # Geminiの設定をストリーミングモードに
            streaming_model = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash-002",
                temperature=0,
                stream=True
            )

            # プロンプトの準備（既存の_generate_summary_nodeと同じ）
            prompt_text = self._prepare_summary_prompt(search_results["state"])
            prompt = ChatPromptTemplate.from_template("{text}")

            # ストリーミング生成
            async for chunk in streaming_model.astream(prompt_text):
                if await request.is_disconnected():
                    break

                response = {
                    "type": "summary",
                    "content": chunk.content
                }
                yield f"data: {json.dumps(response, cls=DateTimeEncoder, ensure_ascii=False)}\n\n"

        except Exception as e:
            error_response = {
                "type": "error",
                "content": str(e)
            }
            yield f"data: {json.dumps(error_response, cls=DateTimeEncoder, ensure_ascii=False)}\n\n"
