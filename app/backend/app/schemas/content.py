
from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class MovieBase(BaseModel):
    title: str
    original_title: str = ""
    year: int = 0
    duration: int = 0
    rating: float = 0.0
    age_rating: str = "PG"
    genres: list[str] = Field(default_factory=list)
    country: str = ""
    language: str = ""
    director: str = ""
    cast: list[str] = Field(default_factory=list)
    description: str = ""
    poster: str = ""
    backdrop: str = ""
    audio: list[str] = Field(default_factory=list)
    subtitles: list[str] = Field(default_factory=list)
    qualities: list[str] = Field(default_factory=list)
    dubbed: list[str] = Field(default_factory=list)
    featured: bool = False
    published: bool = True


class MovieCreate(MovieBase):
    pass


class MovieUpdate(BaseModel):
    title: str | None = None
    original_title: str | None = None
    year: int | None = None
    duration: int | None = None
    rating: float | None = None
    age_rating: str | None = None
    genres: list[str] | None = None
    country: str | None = None
    language: str | None = None
    director: str | None = None
    cast: list[str] | None = None
    description: str | None = None
    poster: str | None = None
    backdrop: str | None = None
    audio: list[str] | None = None
    subtitles: list[str] | None = None
    qualities: list[str] | None = None
    dubbed: list[str] | None = None
    featured: bool | None = None
    published: bool | None = None
    hls_path: str | None = None


class MovieOut(MovieBase, ORMModel):
    id: int
    views: int = 0
    type: str = "movie"
    hls_path: str | None = None


class SeriesBase(BaseModel):
    title: str
    original_title: str = ""
    year: int = 0
    rating: float = 0.0
    age_rating: str = "PG"
    genres: list[str] = Field(default_factory=list)
    country: str = ""
    language: str = ""
    seasons: int = 1
    episode_count: int = 0
    status: str = "Ongoing"
    description: str = ""
    poster: str = ""
    backdrop: str = ""
    audio: list[str] = Field(default_factory=list)
    subtitles: list[str] = Field(default_factory=list)
    dubbed: list[str] = Field(default_factory=list)
    new_episode: bool = False
    published: bool = True


class SeriesCreate(SeriesBase):
    pass


class SeriesUpdate(BaseModel):
    title: str | None = None
    original_title: str | None = None
    year: int | None = None
    rating: float | None = None
    age_rating: str | None = None
    genres: list[str] | None = None
    country: str | None = None
    language: str | None = None
    seasons: int | None = None
    episode_count: int | None = None
    status: str | None = None
    description: str | None = None
    poster: str | None = None
    backdrop: str | None = None
    audio: list[str] | None = None
    subtitles: list[str] | None = None
    dubbed: list[str] | None = None
    new_episode: bool | None = None
    published: bool | None = None


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
    hls_path: str | None = None
    published: bool = True
