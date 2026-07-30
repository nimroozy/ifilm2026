from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class MovieBase(BaseModel):
    title: str
    original_title: str = ""
    year: int = 0
    duration: int = 0
    rating: float = 0.0
    age_rating: str = "PG"
    genres: List[str] = Field(default_factory=list)
    country: str = ""
    language: str = ""
    director: str = ""
    cast: List[str] = Field(default_factory=list)
    description: str = ""
    poster: str = ""
    backdrop: str = ""
    audio: List[str] = Field(default_factory=list)
    subtitles: List[str] = Field(default_factory=list)
    qualities: List[str] = Field(default_factory=list)
    dubbed: List[str] = Field(default_factory=list)
    featured: bool = False
    published: bool = True


class MovieCreate(MovieBase):
    pass


class MovieUpdate(BaseModel):
    title: Optional[str] = None
    original_title: Optional[str] = None
    year: Optional[int] = None
    duration: Optional[int] = None
    rating: Optional[float] = None
    age_rating: Optional[str] = None
    genres: Optional[List[str]] = None
    country: Optional[str] = None
    language: Optional[str] = None
    director: Optional[str] = None
    cast: Optional[List[str]] = None
    description: Optional[str] = None
    poster: Optional[str] = None
    backdrop: Optional[str] = None
    audio: Optional[List[str]] = None
    subtitles: Optional[List[str]] = None
    qualities: Optional[List[str]] = None
    dubbed: Optional[List[str]] = None
    featured: Optional[bool] = None
    published: Optional[bool] = None
    hls_path: Optional[str] = None


class MovieOut(MovieBase, ORMModel):
    id: int
    views: int = 0
    type: str = "movie"
    hls_path: Optional[str] = None


class SeriesBase(BaseModel):
    title: str
    original_title: str = ""
    year: int = 0
    rating: float = 0.0
    age_rating: str = "PG"
    genres: List[str] = Field(default_factory=list)
    country: str = ""
    language: str = ""
    seasons: int = 1
    episode_count: int = 0
    status: str = "Ongoing"
    description: str = ""
    poster: str = ""
    backdrop: str = ""
    audio: List[str] = Field(default_factory=list)
    subtitles: List[str] = Field(default_factory=list)
    dubbed: List[str] = Field(default_factory=list)
    new_episode: bool = False
    published: bool = True


class SeriesCreate(SeriesBase):
    pass


class SeriesUpdate(BaseModel):
    title: Optional[str] = None
    original_title: Optional[str] = None
    year: Optional[int] = None
    rating: Optional[float] = None
    age_rating: Optional[str] = None
    genres: Optional[List[str]] = None
    country: Optional[str] = None
    language: Optional[str] = None
    seasons: Optional[int] = None
    episode_count: Optional[int] = None
    status: Optional[str] = None
    description: Optional[str] = None
    poster: Optional[str] = None
    backdrop: Optional[str] = None
    audio: Optional[List[str]] = None
    subtitles: Optional[List[str]] = None
    dubbed: Optional[List[str]] = None
    new_episode: Optional[bool] = None
    published: Optional[bool] = None


class SeriesOut(SeriesBase, ORMModel):
    id: int
    views: int = 0
    type: str = "series"
    episodes: int = 0

    @classmethod
    def from_orm_series(cls, obj):
        data = {
            "id": obj.id,
            "title": obj.title,
            "original_title": obj.original_title,
            "year": obj.year,
            "rating": obj.rating,
            "age_rating": obj.age_rating,
            "genres": obj.genres or [],
            "country": obj.country,
            "language": obj.language,
            "seasons": obj.seasons,
            "episode_count": obj.episode_count,
            "episodes": obj.episode_count,
            "status": obj.status,
            "description": obj.description,
            "poster": obj.poster,
            "backdrop": obj.backdrop,
            "audio": obj.audio or [],
            "subtitles": obj.subtitles or [],
            "dubbed": obj.dubbed or [],
            "new_episode": obj.new_episode,
            "published": obj.published,
            "views": obj.views,
            "type": "series",
        }
        return cls.model_validate(data)


class EpisodeCreate(BaseModel):
    season: int = 1
    episode: int = 1
    title: str
    duration: int = 0
    description: str = ""
    thumbnail: str = ""
    published: bool = True


class EpisodeOut(ORMModel):
    id: int
    series_id: int
    season: int
    episode: int
    title: str
    duration: int
    description: str
    thumbnail: str
    hls_path: Optional[str] = None
    published: bool = True
