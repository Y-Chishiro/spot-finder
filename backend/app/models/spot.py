from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# Text Searchのクエリモデル
class TextSearchQuery(BaseModel):
    textQuery: str = Field(
        description="検索するテキスト文字列。例: '渋谷のラーメン'。",
        default=""
    )
    includedType: Optional[str] = Field(
        description="検索対象の単一のタイプ。例: 'restaurant'。",
        default=None
    )
    languageCode: str = Field(
        description="結果を返す言語コード。",
        default="ja"
    )
    pageSize: Optional[int] = Field(
        description="1ページに返す結果の件数（1～20）。",
        default=5,
        ge=1,
        le=5
    )

# 住所のコンポーネント
class AddressComponent(BaseModel):
    long_name: str
    short_name: str
    types: List[str]

# 営業時間の詳細
class PeriodDetail(BaseModel):
    date: Optional[str] = None
    day: int
    time: str

# 営業時間の期間
class OpeningPeriod(BaseModel):
    open: PeriodDetail
    close: Optional[PeriodDetail] = None

# 営業時間情報
class OpeningHours(BaseModel):
    open_now: bool
    periods: List[OpeningPeriod]
    weekday_text: List[str]

# 位置情報
class PlaceLocation(BaseModel):
    lat: float
    lng: float

# 地図表示の範囲
class PlaceViewport(BaseModel):
    northeast: PlaceLocation
    southwest: PlaceLocation

# ジオメトリ情報
class Geometry(BaseModel):
    location: PlaceLocation
    viewport: PlaceViewport

# 写真情報
class Photo(BaseModel):
    height: int
    html_attributions: List[str]
    photo_reference: str
    width: int

# レビュー情報
class Review(BaseModel):
    author_name: str
    author_url: Optional[str] = None
    language: str
    original_language: Optional[str] = None
    profile_photo_url: Optional[str] = None
    rating: float
    relative_time_description: str
    text: str
    time: datetime
    translated: bool

# ニュース記事情報
class NewsArticle(BaseModel):
    title: str = Field(..., alias="og:title")
    image: Optional[str] = Field(None, alias="og:image")
    type: Optional[str] = Field(None, alias="og:type")
    site_name: Optional[str] = Field(None, alias="og:site_name")
    description: Optional[str] = Field(None, alias="og:description")
    url: Optional[str] = Field(None, alias="og:url")
    pubdate: Optional[datetime] = Field(None, alias="pubdate")

# Place情報
class PlaceResult(BaseModel):
    place_id: str
    name: str
    formatted_address: str
    geometry: Geometry
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    reviews: Optional[List[Review]] = None
    photos: Optional[List[Photo]] = None
    opening_hours: Optional[OpeningHours] = None
    types: List[str]
    url: str
    website: Optional[str] = None

# ニュース情報を含むPlace情報
class PlaceWithNews(BaseModel):
    place: PlaceResult
    news_articles: List[NewsArticle] = Field(
        default_factory=list,
        description="その場所に関連するニュース記事のリスト"
    )
    relevance_score: Optional[float] = Field(
        default=None,
        description="ユーザーのニーズとの関連度スコア"
    )
    ai_summary: Optional[str] = Field(
        default=None,
        description="AIによる解説文"
    )

# 検索状態管理
class SpotSeekState(BaseModel):
    user_request: str = Field(
        ..., description="ユーザーからのスポット探しの要望"
    )
    query: TextSearchQuery = Field(
        default_factory=TextSearchQuery,
        description="Google Maps APIのTextSearchに投げるクエリ"
    )
    candidate_place_ids: List[str] = Field(
        default_factory=list,
        description="抽出した候補のPlace IDのリスト"
    )
    candidate_places: List[PlaceResult] = Field(
        default_factory=list,
        description="候補のPlace詳細情報のリスト"
    )
    enriched_places: List[PlaceWithNews] = Field(
        default_factory=list,
        description="ニュース情報などが付加された場所情報のリスト"
    )
    summary: str = Field(
        default="",
        description="AIによる総合的な推薦文"
    )

# APIリクエスト/レスポンス用のモデル
class SpotSearchRequest(BaseModel):
    user_request: str = Field(..., description="ユーザーからのスポット探しの要望")

class SpotSearchResponse(BaseModel):
    places: List[PlaceWithNews]
    summary: str
