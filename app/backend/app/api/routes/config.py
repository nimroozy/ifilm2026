from fastapi import APIRouter

router = APIRouter(tags=["config"])


@router.get("/config")
def get_runtime_config():
    # Frontend expects API_BASE_URL; "/" means same-origin via Vite proxy.
    return {"API_BASE_URL": "/"}
