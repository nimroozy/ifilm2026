"""Admin and public collection API routes (Collections V1)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.schemas.collections import (
    CollectionCreate,
    CollectionItemAdd,
    CollectionItemOut,
    CollectionOut,
    CollectionPublicOut,
    CollectionReorder,
    CollectionStatusAction,
    CollectionUpdate,
)
from app.schemas.common import Envelope, Message, paginated
from app.services import collections as collections_service

router = APIRouter(tags=["collections"])


class PickerResult(BaseModel):
    movies: list[Any]
    series: list[Any]
    page: int = 1
    page_size: int = 20


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


@router.get("/catalog/collections", response_model=Envelope[CollectionPublicOut])
def list_public_collections(
    db: DbSession,
    collection_type: str | None = None,
    featured: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
) -> Envelope[CollectionPublicOut]:
    rows, total = collections_service.list_public_collections(
        db,
        collection_type=collection_type,
        featured_only=bool(featured),
        page=page,
        page_size=page_size,
        include_items=False,
        min_visible_items=1,
    )
    payloads = [
        collections_service.collection_public_out(row, db, include_items=False) for row in rows
    ]
    # Attach counts without loading full item payloads (index-friendly).
    for row, payload in zip(rows, payloads, strict=True):
        payload.item_count = collections_service.visible_item_count(db, row.id)
    return paginated(payloads, total=total, page=page, page_size=page_size)


@router.get("/catalog/collections/featured/home", response_model=Envelope[CollectionPublicOut])
def list_featured_home_collections(
    db: DbSession,
    page_size: int = Query(6, ge=1, le=12),
    min_items: int = Query(
        collections_service.HOMEPAGE_MIN_VISIBLE_ITEMS, ge=1, le=20
    ),
) -> Envelope[CollectionPublicOut]:
    """Featured collections for homepage shelves (non-empty, ordered)."""
    rows, total = collections_service.list_public_collections(
        db,
        featured_only=True,
        page=1,
        page_size=page_size,
        include_items=True,
        min_visible_items=min_items,
    )
    payloads = [
        collections_service.collection_public_out(row, db, include_items=True) for row in rows
    ]
    return paginated(payloads, total=total, page=1, page_size=page_size)


@router.get("/catalog/collections/{slug}", response_model=CollectionPublicOut)
def get_public_collection(slug: str, db: DbSession) -> CollectionPublicOut:
    collection = collections_service.get_public_collection_by_slug(db, slug)
    return collections_service.collection_public_out(collection, db, include_items=True)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@router.get("/admin/collections", response_model=Envelope[CollectionOut])
def admin_list_collections(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("collections.read"))],
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    collection_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Envelope[CollectionOut]:
    rows, total = collections_service.list_admin_collections(
        db,
        q=q,
        status_filter=status_filter,
        collection_type=collection_type,
        page=page,
        page_size=page_size,
    )
    return paginated(
        [collections_service.collection_admin_out(r, db, include_items=False) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/admin/collections",
    response_model=CollectionOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_collection(
    payload: CollectionCreate,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("collections.manage"))],
) -> CollectionOut:
    collection = collections_service.create_collection(db, payload, admin_id=admin.id)
    return collections_service.collection_admin_out(collection, db)


@router.get("/admin/collections/picker", response_model=PickerResult)
def admin_collection_picker(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("collections.read"))],
    q: str | None = None,
    content_type: str | None = None,
    published_only: bool = False,
    year: int | None = None,
    genre: str | None = None,
    language: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
) -> PickerResult:
    result = collections_service.search_picker_content(
        db,
        q=q,
        content_type=content_type,
        published_only=published_only,
        year=year,
        genre=genre,
        language=language,
        page=page,
        page_size=page_size,
    )
    return PickerResult(**result)


@router.get("/admin/collections/{collection_id}", response_model=CollectionOut)
def admin_get_collection(
    collection_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("collections.read"))],
) -> CollectionOut:
    collection = collections_service.get_collection(db, collection_id)
    return collections_service.collection_admin_out(collection, db)


@router.patch("/admin/collections/{collection_id}", response_model=CollectionOut)
def admin_update_collection(
    collection_id: int,
    payload: CollectionUpdate,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("collections.manage"))],
) -> CollectionOut:
    collection = collections_service.get_collection(db, collection_id)
    collection = collections_service.update_collection(
        db, collection, payload, admin_id=admin.id
    )
    return collections_service.collection_admin_out(collection, db)


@router.delete("/admin/collections/{collection_id}", response_model=Message)
def admin_delete_collection(
    collection_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("collections.manage"))],
) -> Message:
    collection = collections_service.get_collection(db, collection_id)
    collections_service.soft_delete_collection(db, collection, admin_id=admin.id)
    return Message(detail="Collection deleted")


@router.post("/admin/collections/{collection_id}/publish", response_model=CollectionOut)
def admin_publish_collection(
    collection_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("collections.manage"))],
    payload: CollectionStatusAction | None = None,
) -> CollectionOut:
    collection = collections_service.get_collection(db, collection_id)
    collection = collections_service.publish_collection(
        db,
        collection,
        admin_id=admin.id,
        expected_updated_at=payload.expected_updated_at if payload else None,
    )
    return collections_service.collection_admin_out(collection, db)


@router.post("/admin/collections/{collection_id}/unpublish", response_model=CollectionOut)
def admin_unpublish_collection(
    collection_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("collections.manage"))],
    payload: CollectionStatusAction | None = None,
) -> CollectionOut:
    collection = collections_service.get_collection(db, collection_id)
    collection = collections_service.unpublish_collection(
        db,
        collection,
        admin_id=admin.id,
        expected_updated_at=payload.expected_updated_at if payload else None,
    )
    return collections_service.collection_admin_out(collection, db)


@router.post("/admin/collections/{collection_id}/archive", response_model=CollectionOut)
def admin_archive_collection(
    collection_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("collections.manage"))],
    payload: CollectionStatusAction | None = None,
) -> CollectionOut:
    collection = collections_service.get_collection(db, collection_id)
    collection = collections_service.archive_collection(
        db,
        collection,
        admin_id=admin.id,
        expected_updated_at=payload.expected_updated_at if payload else None,
    )
    return collections_service.collection_admin_out(collection, db)


@router.get("/admin/collections/{collection_id}/preview", response_model=CollectionPublicOut)
def admin_preview_collection(
    collection_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("collections.read"))],
) -> CollectionPublicOut:
    """Preview the public-visible result without requiring published status."""
    collection = collections_service.get_collection(db, collection_id)
    return collections_service.collection_public_out(collection, db, include_items=True)


@router.post(
    "/admin/collections/{collection_id}/items",
    response_model=CollectionItemOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_add_item(
    collection_id: int,
    payload: CollectionItemAdd,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("collections.manage"))],
) -> CollectionItemOut:
    collection = collections_service.get_collection(db, collection_id)
    item = collections_service.add_item(db, collection, payload, admin_id=admin.id)
    # Reload with relationships
    collection = collections_service.get_collection(db, collection_id)
    refreshed = next(i for i in collection.items if i.id == item.id)
    out = collections_service.item_out(refreshed, db, public_only=False)
    assert out is not None
    return out


@router.delete(
    "/admin/collections/{collection_id}/items/{item_id}",
    response_model=Message,
)
def admin_remove_item(
    collection_id: int,
    item_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("collections.manage"))],
) -> Message:
    collection = collections_service.get_collection(db, collection_id)
    collections_service.remove_item(db, collection, item_id, admin_id=admin.id)
    return Message(detail="Item removed")


@router.put("/admin/collections/{collection_id}/items/reorder", response_model=CollectionOut)
def admin_reorder_items(
    collection_id: int,
    payload: CollectionReorder,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("collections.manage"))],
) -> CollectionOut:
    collection = collections_service.get_collection(db, collection_id)
    collection = collections_service.reorder_items(
        db, collection, payload, admin_id=admin.id
    )
    return collections_service.collection_admin_out(collection, db)
