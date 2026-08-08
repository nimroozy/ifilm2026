"""Aggregated homepage catalog endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import CurrentSubscriber, DbSession, OptionalSubscriber
from app.schemas.home import CatalogHomeOut, MeHomeOut
from app.services.home_catalog import build_catalog_home, build_me_home

router = APIRouter(tags=["home"])


@router.get("/catalog/home", response_model=CatalogHomeOut)
def catalog_home(
    db: DbSession,
    locale: str | None = Query(None, description="UI locale: en|fa|ps"),
) -> CatalogHomeOut:
    """Bounded public homepage shelves (card payloads). Safe for anonymous caching."""
    return CatalogHomeOut.model_validate(build_catalog_home(db, locale=locale))


@router.get("/me/home", response_model=MeHomeOut)
def me_home(
    db: DbSession,
    user: CurrentSubscriber,
    locale: str | None = Query(None, description="UI locale: en|fa|ps"),
) -> MeHomeOut:
    """Authenticated homepage: catalog shelves + CW/watchlist/recommendations."""
    return MeHomeOut.model_validate(build_me_home(db, user, locale=locale))


@router.get("/home", response_model=CatalogHomeOut | MeHomeOut)
def home_dispatch(
    db: DbSession,
    user: OptionalSubscriber,
    locale: str | None = Query(None, description="UI locale: en|fa|ps"),
) -> CatalogHomeOut | MeHomeOut:
    """Convenience: personalized when authenticated, otherwise public catalog home."""
    if user is None:
        return CatalogHomeOut.model_validate(build_catalog_home(db, locale=locale))
    return MeHomeOut.model_validate(build_me_home(db, user, locale=locale))
