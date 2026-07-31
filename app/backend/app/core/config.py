from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "iFilm API"
    app_env: str = "development"
    debug: bool = False
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # No production-safe default. Local/dev must set explicitly.
    database_url: str = ""

    # Empty by default; must be provided via environment.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    admin_bootstrap_username: str = "admin"
    # Required only for the explicit seed command; never defaults to a known password.
    admin_bootstrap_password: str | None = None
    admin_bootstrap_email: str = "admin@ifilm.local"

    media_root: str = "./media"
    # Dedicated artwork tree — never under packages/originals. Served only at /artwork.
    artwork_root: str = "./artwork"
    # Legacy placeholder HLS base URL (unused by Phase 7 protected streaming).
    hls_public_base_url: str = "http://127.0.0.1:8000/api/stream"
    upload_max_bytes: int = 50 * 1024 * 1024 * 1024
    upload_allowed_content_types: list[str] = Field(
        default_factory=lambda: [
            "video/mp4",
            "video/x-matroska",
            "video/webm",
            "video/quicktime",
            "video/x-msvideo",
            "image/jpeg",
            "image/png",
            "image/webp",
            "text/vtt",
            "application/x-subrip",
            "text/plain",
            "application/octet-stream",
        ]
    )
    # When true, completing an upload whose SHA256 matches another completed
    # media asset is rejected (409). Failed/cancelled assets are ignored.
    upload_reject_duplicate_checksum: bool = True

    redis_url: str = "redis://localhost:6379/0"
    worker_queue_name: str = "ifilm"
    redis_required: bool = False

    # Feature flags — advanced capabilities default OFF.
    enable_uploads: bool = False
    enable_encoding: bool = False
    enable_cdn_sync: bool = False
    enable_radius_login: bool = False
    enable_media_processing: bool = False
    enable_hls_encoding: bool = False
    enable_local_streaming: bool = False

    # Opaque playback token HMAC secret (required when streaming enabled).
    playback_token_secret: str = ""
    playback_token_ttl_seconds: int = 3600
    playback_access_touch_seconds: int = 30

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    media_processing_worker_id: str = ""
    media_processing_poll_seconds: float = 2.0
    media_processing_heartbeat_seconds: float = 10.0
    media_processing_stale_after_seconds: int = 120
    media_processing_max_attempts: int = 3
    media_processing_retry_base_seconds: int = 30
    media_processing_probe_timeout_seconds: int = 120
    media_processing_encode_timeout_seconds: int = 3600
    media_processing_log_max_bytes: int = 65536
    hls_segment_duration_seconds: int = 6
    hls_max_height: int = 1080
    hls_x264_preset: str = "veryfast"

    cdn_http_timeout_seconds: int = 10

    radius_enabled: bool = False
    radius_mode: str = "live"  # mock | live — mock only allowed in development/test
    radius_server: str = "127.0.0.1"
    radius_port: int = 1812
    radius_secret: str = ""
    radius_nas_identifier: str = "ifilm"
    radius_timeout_seconds: int = 3
    # Explicit mock fixture users only. JSON list of objects:
    # [{"username":"...","password":"...","package":"...","branch":"...","expiration":"..."}]
    radius_mock_users: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("upload_allowed_content_types", mode="before")
    @classmethod
    def split_content_types(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("radius_mock_users", mode="before")
    @classmethod
    def parse_mock_users(cls, value: Any) -> Any:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            import json

            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError("RADIUS_MOCK_USERS must be a JSON list")
            return parsed
        return value

    @model_validator(mode="after")
    def normalize_env(self) -> Settings:
        self.app_env = (self.app_env or "development").strip().lower()
        self.radius_mode = (self.radius_mode or "live").strip().lower()
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
