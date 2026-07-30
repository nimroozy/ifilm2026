from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


class PageMeta(BaseModel):
    page: int = 1
    page_size: int = 20
    total: int = 0
    pages: int = 0


class Envelope(BaseModel, Generic[T]):
    data: list[T] | T
    meta: PageMeta | None = None


class Page(BaseModel, Generic[T]):
    """Legacy page shape kept for transitional clients."""

    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20


def paginated(items: list[T], *, total: int, page: int, page_size: int) -> Envelope[T]:
    pages = ceil(total / page_size) if page_size else 0
    return Envelope(
        data=items,
        meta=PageMeta(page=page, page_size=page_size, total=total, pages=pages),
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CatalogQuery(BaseModel):
    q: str | None = None
    genre: str | None = None
    year: int | None = None
    language: str | None = None
    featured: bool | None = None
    trending: bool | None = None
    status: str | None = None
    sort: str = "newest"
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
