from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentAdmin, DbSession
from app.core.security import create_access_token, verify_password
from app.models.admin import AdminUser
from app.schemas.auth import AdminLoginRequest, AdminOut
from app.schemas.common import TokenResponse

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])

GENERIC_FAILURE = "Invalid credentials"


@router.post("/login", response_model=TokenResponse)
def admin_login(payload: AdminLoginRequest, db: DbSession):
    admin = db.query(AdminUser).filter(AdminUser.username == payload.username).one_or_none()
    if not admin or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_FAILURE)
    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_FAILURE)
    token = create_access_token(str(admin.id), claims={"typ": "admin", "username": admin.username})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=AdminOut)
def admin_me(admin: CurrentAdmin):
    role_name = admin.role.name if admin.role else None
    permissions = admin.role.permissions if admin.role else []
    return AdminOut(
        id=admin.id,
        username=admin.username,
        email=admin.email,
        full_name=admin.full_name,
        is_active=admin.is_active,
        role_name=role_name,
        permissions=permissions or [],
    )
