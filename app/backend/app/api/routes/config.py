from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["config"])


@router.get("/config")
def get_runtime_config():
    settings = get_settings()
    # Frontend expects API_BASE_URL; "/" means same-origin via Vite proxy.
    return {
        "API_BASE_URL": "/",
        "ENABLE_WATCH_HISTORY": settings.enable_watch_history,
        "WATCH_PROGRESS_MIN_SECONDS": settings.watch_progress_min_seconds,
        "WATCH_PROGRESS_COMPLETE_PERCENT": settings.watch_progress_complete_percent,
        "WATCH_PROGRESS_SAVE_INTERVAL_SECONDS": settings.watch_progress_save_interval_seconds,
        "WATCH_PROGRESS_RESUME_MARGIN_SECONDS": settings.watch_progress_resume_margin_seconds,
    }
