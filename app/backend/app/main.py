from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import models as _models  # noqa: F401
from app.api.router import api_router
from app.api.routes import artwork as artwork_routes
from app.core.config import get_settings
from app.core.logging_filters import RequestLoggingMiddleware, install_token_redaction_logging
from app.core.runtime import validate_runtime_settings
from app.services.readiness import readiness_report
from app.services.storage import ensure_artwork_layout, media_root


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    validate_runtime_settings(settings)
    media_root()
    ensure_artwork_layout()
    install_token_redaction_logging()
    # Schema changes are applied only via Alembic migrations.
    # Demo/admin seed data is created only by the explicit seed command.
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    validate_runtime_settings(settings)
    install_token_redaction_logging()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(api_router, prefix=settings.api_prefix)
    # Artwork only — never mount MEDIA_ROOT. Packages/originals are not public.
    app.include_router(artwork_routes.router)

    @app.get("/health")
    def health():
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    @app.get("/ready")
    def ready():
        report = readiness_report(settings)
        code = 200 if report["status"] == "ready" else 503
        return JSONResponse(status_code=code, content=report)

    # Explicitly reject legacy anonymous /media MEDIA_ROOT exposure.
    @app.get("/media")
    @app.get("/media/{path:path}")
    def legacy_media_removed(path: str = ""):
        return JSONResponse(
            status_code=404,
            content={
                "detail": (
                    "Public /media MEDIA_ROOT mount removed. "
                    "HLS packages are delivered only via protected /api/stream/{token}/… routes. "
                    "Artwork (if any) is served from /artwork under ARTWORK_ROOT."
                )
            },
        )

    # Ensure artwork root exists for optional local posters.
    Path(settings.artwork_root).mkdir(parents=True, exist_ok=True)

    return app


app = create_app()
