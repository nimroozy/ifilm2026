
from pydantic import BaseModel

from app.schemas.common import ORMModel


class UploadCreate(BaseModel):
    filename: str
    content_type: str = "movie"
    content_id: int | None = None
    size_bytes: int = 0


class UploadOut(ORMModel):
    id: int
    filename: str
    content_type: str
    content_id: int | None
    size_bytes: int
    stored_path: str | None
    status: str
    progress: int
    error: str | None


class EncodingOut(ORMModel):
    id: int
    title: str
    source_file: str
    content_type: str
    content_id: int | None
    progress: int
    stage: str
    worker: str
    qualities: list[str]
    status: str
    output_hls_path: str | None
    error: str | None
    eta_seconds: int | None


class StreamManifest(BaseModel):
    content_type: str
    content_id: int
    episode_id: int | None = None
    title: str
    qualities: list[str]
    playlist_url: str
    cdn_node: str | None = None
    skip_intro_seconds: int = 0
