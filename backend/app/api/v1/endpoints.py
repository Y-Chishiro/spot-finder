from fastapi import APIRouter, Depends, Request
from app.core.auth import get_api_key
from app.models.spot import SpotSearchRequest, SpotSearchResponse
from app.services.spot_service import SpotService
from fastapi.responses import StreamingResponse

router = APIRouter()
spot_service = SpotService()


@router.get("/health")
async def health_check(api_key: str = Depends(get_api_key)):
    """
    ヘルスチェックエンドポイント
    """
    return {"status": "healthy"}


@router.post("/search", response_model=SpotSearchResponse)
async def search_spots(
    request: SpotSearchRequest,
    api_key: str = Depends(get_api_key)
):
    """
    ユーザーの要望に基づいてスポットを検索します。
    """
    result = await spot_service.search_and_summarize(request.user_request)
    return result


@router.post("/stream_search")
async def stream_search_spots(
    request_data: SpotSearchRequest,
    request: Request,
    api_key: str = Depends(get_api_key)
):
    """ユーザのリクエストに対し、検索結果とLLMのサマリーをストリーミングで返します。"""

    async def event_generator():
        # 前処理：スポット情報の取得
        search_results = await spot_service.preprocess_search(request_data.user_request)

        # LLMサマリーのストリーミング生成
        async for chunk in spot_service.stream_llm_summary(search_results, request):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
