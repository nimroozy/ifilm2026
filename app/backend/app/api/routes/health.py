from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.services.readiness import readiness_report

router = APIRouter(tags=["health"])


@router.get("/health")
def api_health():
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@router.get("/health/live")
def api_health_live():
    return {"status": "live"}


@router.get("/health/ready")
def api_health_ready():
    settings = get_settings()
    report = readiness_report(settings)
    code = 200 if report["status"] == "ready" else 503
    return JSONResponse(status_code=code, content=report)
