from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_device: bool = False
    device_id: str | None = Field(default=None, max_length=64)
    device_name: str = ""
    device_type: str = "desktop"
    browser: str = ""


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminOut(ORMModel):
    id: int
    username: str
    email: str
    full_name: str
    is_active: bool
    role_name: str | None = None
    permissions: list[str] = Field(default_factory=list)


class SubscriberOut(ORMModel):
    id: int
    username: str
    name: str
    branch: str
    status: str
    package: str
    expiration: str
    service_status: str = "unknown"
    max_devices: int = 3
    identity_provider: str = "local"
    external_subject: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None


class EntitlementOut(BaseModel):
    allowed: bool
    account_status: str
    service_status: str
    package_name: str
    branch_code: str
    valid_from: str | None = None
    valid_until: str | None = None
    denial_code: str | None = None
    safe_reason: str | None = None
    max_devices: int
    source: str
    checked_at: str | None = None
    from_cache: bool = False


class DeviceOut(ORMModel):
    id: int
    client_device_id: str
    name: str
    device_type: str
    browser: str
    ip: str
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    current: bool = False


class SubscriberTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
