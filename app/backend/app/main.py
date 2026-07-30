from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import models as _models  # noqa: F401
from app.api.router import api_router
from app.core.config import get_settings
from app.core.runtime import validate_runtime_settings
from app.services.readiness import readiness_report
from app.services.storage import media_root


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    validate_runtime_settings(settings)
    media_root()
    # Schema changes are applied only via Alembic migrations.
    # Demo/admin seed data is created only by the explicit seed command.
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    validate_runtime_settings(settings)

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    media_path = Path(settings.media_root).resolve()
    media_path.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(media_path)), name="media")

    @app.get("/health")
    def health():
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    @app.get("/ready")
    def ready():
        report = readiness_report(settings)
        code = 200 if report["status"] == "ready" else 503
        return JSONResponse(status_code=code, content=report)

    return app


app = create_app()
