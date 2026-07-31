from fastapi import HTTPException, status

from app.core.config import Settings, get_settings


def require_feature(flag_name: str, settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    enabled = bool(getattr(cfg, flag_name, False))
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feature disabled",
        )
