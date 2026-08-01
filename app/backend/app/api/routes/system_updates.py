from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.schemas.system_updates import (
    BackupOut,
    ConfirmPasswordIn,
    InstallUpdateIn,
    PreflightOut,
    RollbackIn,
    SystemVersionOut,
    UpdateCheckOut,
    UpdateHistoryOut,
    UpdateJobOut,
)
from app.services import system_updates as svc
from app.services.update_agent_client import UpdateAgentError

router = APIRouter(prefix="/admin/system", tags=["admin-system-updates"])


def _http_from_exc(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        code = str(exc)
        if code == "reauthentication_failed":
            return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Re-authentication required")
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Update job not found")
    if isinstance(exc, ValueError):
        detail = {
            "confirmation_required": "Confirmation required",
            "database_restore_confirmation_required": "Database restore confirmation required",
        }.get(str(exc), str(exc))
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if isinstance(exc, RuntimeError):
        detail = {
            "concurrent_update": "Another update or rollback is already running",
            "no_update_available": "No update available",
            "target_mismatch": "Requested target version is not the latest checked release",
        }.get(str(exc), str(exc))
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if isinstance(exc, UpdateAgentError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Update agent unavailable")
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Update operation failed")


@router.get("/version", response_model=SystemVersionOut)
def get_version(
    _: Annotated[AdminUser, Depends(require_permissions("system_updates.read"))],
) -> dict[str, Any]:
    return svc.get_version_info()


@router.post("/updates/check", response_model=UpdateCheckOut)
def check_updates(
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("system_updates.read"))],
) -> dict[str, Any]:
    try:
        return svc.check_for_updates(db, admin)
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(exc) from exc


@router.post("/updates/preflight", response_model=PreflightOut)
def preflight(
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("system_updates.manage"))],
) -> dict[str, Any]:
    try:
        return svc.run_preflight(db, admin)
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(exc) from exc


@router.post("/updates/backup", response_model=BackupOut)
def backup(
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("system_updates.manage"))],
    payload: ConfirmPasswordIn,
) -> dict[str, Any]:
    try:
        svc.require_recent_password(admin, payload.password)
        return svc.create_backup(db, admin)
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(exc) from exc


@router.post("/updates/install", response_model=UpdateJobOut, status_code=status.HTTP_202_ACCEPTED)
def install_update(
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("system_updates.manage"))],
    payload: InstallUpdateIn,
) -> dict[str, Any]:
    try:
        return svc.start_install(
            db,
            admin,
            password=payload.password,
            confirm=payload.confirm,
            target_version=payload.target_version,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(exc) from exc


@router.get("/updates/history", response_model=UpdateHistoryOut)
def history(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("system_updates.read"))],
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return svc.list_history(db, limit=limit)


@router.get("/updates/{job_id}", response_model=UpdateJobOut)
def get_update_job(
    job_id: str,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("system_updates.read"))],
) -> dict[str, Any]:
    try:
        return svc.get_job(db, job_id, admin)
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(exc) from exc


@router.post("/updates/{job_id}/rollback", response_model=UpdateJobOut)
def rollback_update(
    job_id: str,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("system_updates.manage"))],
    payload: RollbackIn,
) -> dict[str, Any]:
    try:
        return svc.start_rollback(
            db,
            admin,
            password=payload.password,
            confirm=payload.confirm,
            job_id=job_id,
            confirm_database_restore=payload.confirm_database_restore,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(exc) from exc
