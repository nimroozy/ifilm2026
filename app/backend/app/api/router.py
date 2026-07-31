from fastapi import APIRouter

from app.api.routes import (
    admin_auth,
    admin_catalog,
    auth,
    cdn,
    config,
    encoding,
    genres,
    health,
    media_processing,
    media_upload,
    movies,
    search,
    seasons,
    series,
    stream,
    upload,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(config.router)
api_router.include_router(auth.router)
api_router.include_router(admin_auth.router)
api_router.include_router(movies.router)
api_router.include_router(series.router)
api_router.include_router(seasons.router)
api_router.include_router(genres.router)
api_router.include_router(admin_catalog.router)
api_router.include_router(search.router)
api_router.include_router(upload.router)
api_router.include_router(media_upload.router)
api_router.include_router(media_processing.router)
api_router.include_router(encoding.router)
api_router.include_router(cdn.router)
api_router.include_router(stream.router)
