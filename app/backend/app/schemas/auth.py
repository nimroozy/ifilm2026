from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_device: bool = False


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
