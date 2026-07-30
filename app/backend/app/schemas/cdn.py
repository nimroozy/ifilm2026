from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.common import ORMModel


class CDNNodeOut(ORMModel):
    id: int
    name: str
    location: str
    status: str
    ip: str
    base_url: str
    storage_capacity: int
    storage_used: int
    network_usage: int
    current_viewers: int
    cached_titles: int
    last_sync: Optional[datetime]
    health_score: int
    cache_hit_rate: float
    branch: str


class BranchOut(ORMModel):
    id: int
    name: str
    code: str
    cdn: str
    ip_ranges: str
    active_users: int
    concurrent_viewers: int
    streaming_traffic: str
    cdn_status: str


class CDNSyncRequest(BaseModel):
    node_id: Optional[int] = None
    content_type: str = "movie"
    content_id: int
    hls_path: str


class CDNSyncOut(ORMModel):
    id: int
    node_id: int
    content_type: str
    content_id: int
    hls_path: str
    status: str
    detail: Optional[str]
