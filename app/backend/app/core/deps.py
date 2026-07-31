"""Permission dependency helpers.

Legacy coarse keys from the foundation seed remain supported with a narrow map:

| Required permission | Satisfied by any of |
| --- | --- |
| `movies.read` | `movies.read`, `movies.manage`, `movies` |
| `movies.manage` | `movies.manage`, `movies` |
| `series.read` | `series.read`, `series.manage`, `series` |
| `series.manage` | `series.manage`, `series` |
| `genres.read` | `genres.read`, `genres.manage`, `genres` |
| `genres.manage` | `genres.manage`, `genres` |
| `upload.read` | `upload.read`, `upload.manage`, `upload` |
| `upload.manage` | `upload.manage`, `upload` |
| `processing.read` | `processing.read`, `processing.manage`, `processing` |
| `processing.manage` | `processing.manage`, `processing` |
| `streaming.read` | `streaming.read`, `streaming.manage`, `streaming` |
| `streaming.manage` | `streaming.manage`, `streaming` |
| `catalog.read` | `catalog.read` (exact; movies.read / series.read do not grant workflow reads) |
| `catalog.edit` | `catalog.edit` |
| `catalog.review` | `catalog.review` |
| `catalog.approve` | `catalog.approve` |
| `catalog.publish` | `catalog.publish` |
| `catalog.archive` | `catalog.archive` |

Important: `movies` / `series` do **not** grant genre management or unrelated
catalog mutations. `movies.read` alone cannot mutate movies. Coarse `upload`
grants media upload manage/read but not catalog or encoding domains.
`movies.manage` / `series.manage` do **not** satisfy publishing workflow
permissions (`catalog.review` / `approve` / `publish` / `archive`).
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, safe_decode_token
from app.db.session import get_db
from app.models.admin import AdminUser
from app.models.user import Subscriber

bearer = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]

# Exact legacy alias map — do not broaden across resource domains.
PERMISSION_ALIASES: dict[str, frozenset[str]] = {
    "movies.read": frozenset({"movies.read", "movies.manage", "movies"}),
    "movies.manage": frozenset({"movies.manage", "movies"}),
    "series.read": frozenset({"series.read", "series.manage", "series"}),
    "series.manage": frozenset({"series.manage", "series"}),
    "genres.read": frozenset({"genres.read", "genres.manage", "genres"}),
    "genres.manage": frozenset({"genres.manage", "genres"}),
    "upload.read": frozenset({"upload.read", "upload.manage", "upload"}),
    "upload.manage": frozenset({"upload.manage", "upload"}),
    "processing.read": frozenset({"processing.read", "processing.manage", "processing"}),
    "processing.manage": frozenset({"processing.manage", "processing"}),
    "streaming.read": frozenset({"streaming.read", "streaming.manage", "streaming"}),
    "streaming.manage": frozenset({"streaming.manage", "streaming"}),
}


def _token_payload(credentials: HTTPAuthorizationCredentials | None) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return safe_decode_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc


def get_current_admin(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> AdminUser:
    payload = _token_payload(credentials)
    if payload.get("typ") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required")
    admin = db.get(AdminUser, int(payload["sub"]))
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    return admin


def admin_permissions(admin: AdminUser) -> set[str]:
    role = admin.role
    if role is None:
        return set()
    return set(role.permissions or [])


def require_permissions(*required: str) -> Callable[..., AdminUser]:
    """Require each listed permission (legacy aliases via PERMISSION_ALIASES)."""

    def _dependency(admin: Annotated[AdminUser, Depends(get_current_admin)]) -> AdminUser:
        perms = admin_permissions(admin)
        for need in required:
            allowed = PERMISSION_ALIASES.get(need, frozenset({need}))
            if perms.isdisjoint(allowed):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions",
                )
        return admin

    return _dependency


def get_current_subscriber(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> Subscriber:
    payload = _token_payload(credentials)
    if payload.get("typ") != "subscriber":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Subscriber token required"
        )
    user = db.get(Subscriber, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Subscriber not found")
    # Disabled accounts cannot use any subscriber API.
    if (user.status or "").lower() == "disabled":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Subscriber not found")
    return user


def get_active_subscriber(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> Subscriber:
    user = get_current_subscriber(db, credentials)
    if (user.status or "").lower() != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscriber account inactive")
    return user


def get_optional_subscriber(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> Subscriber | None:
    if credentials is None:
        return None
    try:
        return get_current_subscriber(db, credentials)
    except HTTPException:
        return None


CurrentAdmin = Annotated[AdminUser, Depends(get_current_admin)]
CurrentSubscriber = Annotated[Subscriber, Depends(get_current_subscriber)]
ActiveSubscriber = Annotated[Subscriber, Depends(get_active_subscriber)]
OptionalSubscriber = Annotated[Subscriber | None, Depends(get_optional_subscriber)]
