from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["config"])


@router.get("/config")
def get_runtime_config():
    settings = get_settings()
    # Frontend expects API_BASE_URL; "/" means same-origin via Vite proxy.
    return {"API_BASE_URL": "/"}
