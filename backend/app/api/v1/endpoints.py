from fastapi import APIRouter, Depends
from app.core.auth import get_api_key
from app.models.spot import SpotSearchRequest, SpotSearchResponse
from app.services.spot_service import SpotService

router = APIRouter()
spot_service = SpotService()

@router.post("/search", response_model=SpotSearchResponse)
async def search_spots(
    request: SpotSearchRequest,
    api_key: str = Depends(get_api_key)
):
    """
    ユーザーの要望に基づいてスポットを検索します。
    """
    # result = await spot_service.search_spots(request.user_request)
    # return SpotSearchResponse(
    #     places=result["places"],
    #     summary=result["summary"]
    # )
    result = await spot_service.search_and_summarize(request.user_request)
    return result

@router.get("/health")
async def health_check(api_key: str = Depends(get_api_key)):
    """
    ヘルスチェックエンドポイント
    """
    return {"status": "healthy"}
