from typing import List, Optional

from pydantic import BaseModel

from app.schemas.common import ORMModel


class UploadCreate(BaseModel):
    filename: str
    content_type: str = "movie"
    content_id: Optional[int] = None
    size_bytes: int = 0


class UploadOut(ORMModel):
    id: int
    filename: str
    content_type: str
    content_id: Optional[int]
    size_bytes: int
    stored_path: Optional[str]
    status: str
    progress: int
    error: Optional[str]


class EncodingOut(ORMModel):
    id: int
    title: str
    source_file: str
    content_type: str
    content_id: Optional[int]
    progress: int
    stage: str
    worker: str
    qualities: List[str]
    status: str
    output_hls_path: Optional[str]
    error: Optional[str]
    eta_seconds: Optional[int]


class StreamManifest(BaseModel):
    content_type: str
    content_id: int
    episode_id: Optional[int] = None
    title: str
    qualities: List[str]
    playlist_url: str
    cdn_node: Optional[str] = None
    skip_intro_seconds: int = 0
