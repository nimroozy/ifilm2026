"""Admin Portal integration settings."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.schemas.portal_integration import (
    PortalConnectionTestOut,
    PortalIntegrationOut,
    PortalIntegrationUpdateIn,
)
from app.services.admin import portal_integration as svc

router = APIRouter(prefix="/admin/integrations", tags=["admin-integrations"])


@router.get("/portal", response_model=PortalIntegrationOut)
def get_portal_integration(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("settings"))],
) -> dict:
    return svc.get_portal_settings(db)


@router.put("/portal", response_model=PortalIntegrationOut)
def update_portal_integration(
    payload: PortalIntegrationUpdateIn,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("settings"))],
) -> dict:
    try:
        return svc.update_portal_settings(
            db,
            admin,
            payload=payload.model_dump(exclude_unset=True),
        )
    except svc.PortalSettingsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/portal/test", response_model=PortalConnectionTestOut)
def test_portal_integration(
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("settings"))],
) -> dict:
    try:
        return svc.test_portal_connection(db, admin)
    except svc.PortalSettingsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
