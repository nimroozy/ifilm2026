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


def require_hls_encoding(settings: Settings | None = None) -> None:
    """Require media processing and HLS encoding flags.

    Probe remains gated only by ENABLE_MEDIA_PROCESSING.
    Encode/HLS admin actions require both flags.
    """
    cfg = settings or get_settings()
    if not bool(cfg.enable_media_processing):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feature disabled",
        )
    if not bool(cfg.enable_hls_encoding):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HLS encoding is disabled",
        )
