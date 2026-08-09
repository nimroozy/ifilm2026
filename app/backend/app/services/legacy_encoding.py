"""Hard gate for the legacy UploadJob / EncodingJob / ARQ path.

Production and staging must use media-processing encode_hls only.
See docs/media/PIPELINE.md.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.core.config import Settings, get_settings

# Environments where the legacy EncodingJob path is never allowed, even if
# ENABLE_ENCODING is accidentally set true.
_HARD_BLOCK_ENVS = frozenset({"production", "prod", "staging"})


def legacy_encoding_block_reason(settings: Settings | None = None) -> str | None:
    """Return a human reason if legacy encoding must not run, else None."""
    cfg = settings or get_settings()
    env = (cfg.app_env or "").strip().lower()
    if env in _HARD_BLOCK_ENVS:
        return (
            "Legacy EncodingJob path is disabled in "
            f"{env}; use media-processing encode_hls (see docs/media/PIPELINE.md)"
        )
    if not bool(cfg.enable_encoding):
        return "Feature disabled"
    return None


def require_legacy_encoding_allowed(settings: Settings | None = None) -> None:
    """Raise HTTP 503 when legacy encoding APIs must not run."""
    reason = legacy_encoding_block_reason(settings)
    if reason is None:
        return
    if reason == "Feature disabled":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feature disabled",
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=reason,
    )


def legacy_encoding_allowed(settings: Settings | None = None) -> bool:
    return legacy_encoding_block_reason(settings) is None
