from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # アプリケーション設定
    APP_NAME: str = "Spot Finder"
    API_V1_STR: str = "/api/v1"

    # API認証
    API_KEY: str

    # Google Maps API
    GOOGLE_MAPS_API_KEY: str

    # Google Custom Search
    CUSTOM_SEARCH_API_KEY: str
    CUSTOM_SEARCH_CX: str

    # Gemini API
    GOOGLE_API_KEY: str

    # Google Cloud Project
    GOOGLE_CLOUD_PROJECT: str

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

# APIエンドポイント
TEXT_SEARCH_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
DETAILS_ENDPOINT = "https://maps.googleapis.com/maps/api/place/details/json"
CUSTOM_SEARCH_ENDPOINT = "https://www.googleapis.com/customsearch/v1"