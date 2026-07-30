from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.bootstrap import bootstrap_data
from app.core.config import get_settings
from app.db.base import Base
from app.db import session as db_session
from app.services.storage import media_root
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    media_root()
    Base.metadata.create_all(bind=db_session.engine)
    db = db_session.SessionLocal()
    try:
        bootstrap_data(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
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
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
