from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "iFilm API"
    app_env: str = "development"
    debug: bool = True
    api_prefix: str = "/api"
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])

    database_url: str = "postgresql+psycopg2://ifilm:ifilm@localhost:5432/ifilm"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    admin_bootstrap_username: str = "admin"
    admin_bootstrap_password: str = "admin123"
    admin_bootstrap_email: str = "admin@ifilm.local"

    media_root: str = "./media"
    hls_public_base_url: str = "http://127.0.0.1:8000/media/hls"
    upload_max_bytes: int = 50 * 1024 * 1024 * 1024

    redis_url: str = "redis://localhost:6379/0"
    worker_queue_name: str = "ifilm"

    cdn_sync_enabled: bool = True
    cdn_http_timeout_seconds: int = 10

    radius_enabled: bool = False
    radius_mode: str = "mock"  # mock | live
    radius_server: str = "127.0.0.1"
    radius_port: int = 1812
    radius_secret: str = "testing123"
    radius_nas_identifier: str = "ifilm"
    radius_timeout_seconds: int = 3

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors(cls, value):
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
