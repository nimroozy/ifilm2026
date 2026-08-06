from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel
from app.services.languages import normalize_language_list
from app.utils.slug import normalize_slug


def _trim(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


AvailabilitySource = Literal[
    "media_probe",
    "package_manifest",
    "admin_metadata",
    "tmdb_metadata",
    "unknown",
]


class AudioAvailabilityOut(BaseModel):
    original_language: str | None = None
    languages: list[str] = Field(default_factory=list)
    dubbed_languages: list[str] = Field(default_factory=list)
    track_count: int | None = None
    source: AvailabilitySource = "unknown"
    selectable_in_player: bool = False


class SubtitleAvailabilityOut(BaseModel):
    languages: list[str] = Field(default_factory=list)
    track_count: int | None = None
    source: AvailabilitySource = "unknown"
    selectable_in_player: bool = False


def _normalize_lang_field(value: Any) -> Any:
    if value is None:
        return value
    return normalize_language_list(value)


class GenreBase(BaseModel):
    name: str
    slug: str | None = None
    description: str = ""

    @field_validator("name", "description", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return _trim(value)

    @field_validator("name")
    @classmethod
    def name_required(cls, value: str) -> str:
        if not value:
            raise ValueError("name must not be empty")
        return value


class GenreCreate(GenreBase):
    pass


class GenreUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None

    @field_validator("name", "slug", "description", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return _trim(value)


class GenreOut(ORMModel):
    id: int
    name: str
    slug: str
    description: str
    movie_count: int = 0
    series_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CatalogFieldsMixin(BaseModel):
    title: str
    original_title: str = ""
    slug: str | None = None
    description: str = ""
    short_description: str = ""
    release_year: int | None = None
    age_rating: str = ""
    language: str = ""
    country: str = ""
    imdb_id: str | None = None
    imdb_rating: float | None = None
    poster_url: str = ""
    backdrop_url: str = ""
    trailer_url: str = ""
    status: str = "draft"
    is_featured: bool = False
    is_trending: bool = False
    genre_ids: list[int] = Field(default_factory=list)

    @field_validator(
        "title",
        "original_title",
        "slug",
        "description",
        "short_description",
        "age_rating",
        "language",
        "country",
        "imdb_id",
        "poster_url",
        "backdrop_url",
        "trailer_url",
        mode="before",
    )
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return _trim(value)

    @field_validator("title")
    @classmethod
    def title_required(cls, value: str) -> str:
        if not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("release_year")
    @classmethod
    def validate_year(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 1888 or value > 2100:
            raise ValueError("release_year must be between 1888 and 2100")
        return value

    @field_validator("imdb_rating")
    @classmethod
    def validate_rating(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if value < 0 or value > 10:
            raise ValueError("imdb_rating must be between 0 and 10")
        return value

    @field_validator("poster_url", "backdrop_url", "trailer_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value:
            return value
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        # Creates always start as draft; workflow owns all transitions.
        if value not in ("draft",):
            raise ValueError("status must be draft on create; use publishing workflow endpoints")
        return "draft"

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        normalized = normalize_slug(value)
        if not normalized:
            raise ValueError("slug is invalid")
        return normalized

    @field_validator("imdb_id")
    @classmethod
    def validate_imdb_id(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return value


class MovieCreate(CatalogFieldsMixin):
    release_date: date | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    director: str = ""
    producer: str = ""
    writer: str = ""
    studio: str = ""
    cast: list[str] = Field(default_factory=list)
    audio: list[str] = Field(default_factory=list)
    subtitles: list[str] = Field(default_factory=list)
    qualities: list[str] = Field(default_factory=list)
    dubbed: list[str] = Field(default_factory=list)
    tmdb_id: int | None = None

    @field_validator("audio", "subtitles", "dubbed", mode="before")
    @classmethod
    def normalize_language_fields(cls, value: Any) -> Any:
        return _normalize_lang_field(value)


class MovieUpdate(BaseModel):
    title: str | None = None
    original_title: str | None = None
    slug: str | None = None
    description: str | None = None
    short_description: str | None = None
    release_year: int | None = None
    release_date: date | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    age_rating: str | None = None
    language: str | None = None
    country: str | None = None
    imdb_id: str | None = None
    imdb_rating: float | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    trailer_url: str | None = None
    is_featured: bool | None = None
    is_trending: bool | None = None
    genre_ids: list[int] | None = None
    director: str | None = None
    producer: str | None = None
    writer: str | None = None
    studio: str | None = None
    cast: list[str] | None = None
    audio: list[str] | None = None
    subtitles: list[str] | None = None
    qualities: list[str] | None = None
    dubbed: list[str] | None = None
    hls_path: str | None = None
    tmdb_id: int | None = None

    @field_validator("audio", "subtitles", "dubbed", mode="before")
    @classmethod
    def normalize_language_fields(cls, value: Any) -> Any:
        if value is None:
            return value
        return _normalize_lang_field(value)

    @field_validator(
        "title",
        "original_title",
        "slug",
        "description",
        "short_description",
        "age_rating",
        "language",
        "country",
        "imdb_id",
        "poster_url",
        "backdrop_url",
        "trailer_url",
        "director",
        "producer",
        "writer",
        "studio",
        mode="before",
    )
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return _trim(value)

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("release_year")
    @classmethod
    def validate_year(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 1888 or value > 2100:
            raise ValueError("release_year must be between 1888 and 2100")
        return value

    @field_validator("imdb_rating")
    @classmethod
    def validate_rating(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if value < 0 or value > 10:
            raise ValueError("imdb_rating must be between 0 and 10")
        return value

    @field_validator("poster_url", "backdrop_url", "trailer_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return value

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        normalized = normalize_slug(value)
        if not normalized:
            raise ValueError("slug is invalid")
        return normalized


class MovieOut(ORMModel):
    id: int
    title: str
    original_title: str = ""
    slug: str
    description: str = ""
    short_description: str = ""
    release_year: int | None = None
    release_date: date | None = None
    duration_minutes: int | None = None
    age_rating: str = ""
    language: str = ""
    country: str = ""
    imdb_id: str | None = None
    imdb_rating: float | None = None
    tmdb_id: int | None = None
    metadata_source: str = ""
    demo_owned: bool = False
    poster_url: str = ""
    backdrop_url: str = ""
    logo_url: str = ""
    trailer_url: str = ""
    spoken_languages: list[Any] = Field(default_factory=list)
    trailer_provider: str = ""
    trailer_key: str = ""
    trailer_title: str = ""
    trailer_official: bool = False
    trailer_language: str = ""
    trailer_published_at: datetime | None = None
    has_demo_clip: bool = False
    status: str
    is_featured: bool = False
    is_trending: bool = False
    published_at: datetime | None = None
    scheduled_publish_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    genres: list[GenreOut] = Field(default_factory=list)
    director: str = ""
    cast: list[str] = Field(default_factory=list)
    audio: list[str] = Field(default_factory=list)
    subtitles: list[str] = Field(default_factory=list)
    qualities: list[str] = Field(default_factory=list)
    dubbed: list[str] = Field(default_factory=list)
    audio_availability: AudioAvailabilityOut = Field(default_factory=AudioAvailabilityOut)
    subtitle_availability: SubtitleAvailabilityOut = Field(default_factory=SubtitleAvailabilityOut)
    views: int = 0
    type: str = "movie"
    hls_path: str | None = None
    playable: bool = False
    has_playable_package: bool = False
    has_external_media: bool = False
    producer: str = ""
    writer: str = ""
    studio: str = ""

    # Compatibility aliases for existing frontend mappers
    year: int | None = None
    duration: int | None = None
    rating: float | None = None
    poster: str = ""
    backdrop: str = ""
    featured: bool = False


class SeriesCreate(CatalogFieldsMixin):
    end_year: int | None = None
    airing_status: str = "Ongoing"
    audio: list[str] = Field(default_factory=list)
    subtitles: list[str] = Field(default_factory=list)
    dubbed: list[str] = Field(default_factory=list)
    new_episode: bool = False

    @field_validator("audio", "subtitles", "dubbed", mode="before")
    @classmethod
    def normalize_language_fields(cls, value: Any) -> Any:
        return _normalize_lang_field(value)

    @field_validator("end_year")
    @classmethod
    def validate_end_year(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 1888 or value > 2100:
            raise ValueError("end_year must be between 1888 and 2100")
        return value


class SeriesUpdate(MovieUpdate):
    end_year: int | None = None
    airing_status: str | None = None
    new_episode: bool | None = None


class SeriesOut(ORMModel):
    id: int
    title: str
    original_title: str = ""
    slug: str
    description: str = ""
    short_description: str = ""
    release_year: int | None = None
    end_year: int | None = None
    age_rating: str = ""
    language: str = ""
    country: str = ""
    imdb_id: str | None = None
    imdb_rating: float | None = None
    tmdb_id: int | None = None
    metadata_source: str = ""
    demo_owned: bool = False
    poster_url: str = ""
    backdrop_url: str = ""
    logo_url: str = ""
    trailer_url: str = ""
    spoken_languages: list[Any] = Field(default_factory=list)
    trailer_provider: str = ""
    trailer_key: str = ""
    trailer_title: str = ""
    trailer_official: bool = False
    trailer_language: str = ""
    trailer_published_at: datetime | None = None
    has_demo_clip: bool = False
    status: str
    airing_status: str = "Ongoing"
    is_featured: bool = False
    is_trending: bool = False
    published_at: datetime | None = None
    scheduled_publish_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    genres: list[GenreOut] = Field(default_factory=list)
    season_count: int = 0
    episode_count: int = 0
    audio: list[str] = Field(default_factory=list)
    subtitles: list[str] = Field(default_factory=list)
    dubbed: list[str] = Field(default_factory=list)
    audio_availability: AudioAvailabilityOut = Field(default_factory=AudioAvailabilityOut)
    subtitle_availability: SubtitleAvailabilityOut = Field(default_factory=SubtitleAvailabilityOut)
    new_episode: bool = False
    views: int = 0
    type: str = "series"

    year: int | None = None
    seasons: int = 0
    episodes: int = 0
    rating: float | None = None
    poster: str = ""
    backdrop: str = ""
    featured: bool = False


class SeasonCreate(BaseModel):
    season_number: int = Field(ge=0, le=500)
    title: str = ""
    description: str = ""
    poster_url: str = ""
    release_year: int | None = None
    status: str = "draft"

    @field_validator("title", "description", "poster_url", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return _trim(value)

    @field_validator("poster_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value:
            return value
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ("draft",):
            raise ValueError("status must be draft on create; use publishing workflow endpoints")
        return "draft"

    @field_validator("release_year")
    @classmethod
    def validate_year(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 1888 or value > 2100:
            raise ValueError("release_year must be between 1888 and 2100")
        return value


class SeasonUpdate(BaseModel):
    season_number: int | None = Field(default=None, ge=0, le=500)
    title: str | None = None
    description: str | None = None
    poster_url: str | None = None
    release_year: int | None = None

    @field_validator("title", "description", "poster_url", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return _trim(value)

    @field_validator("poster_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return value


class SeasonOut(ORMModel):
    id: int
    series_id: int
    season_number: int
    title: str = ""
    description: str = ""
    poster_url: str = ""
    release_year: int | None = None
    status: str
    published_at: datetime | None = None
    scheduled_publish_at: datetime | None = None
    episode_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EpisodeCreate(BaseModel):
    episode_number: int = Field(ge=0, le=10000)
    title: str
    description: str = ""
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    release_date: date | None = None
    thumbnail_url: str = ""
    status: str = "draft"

    @field_validator("title", "description", "thumbnail_url", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return _trim(value)

    @field_validator("title")
    @classmethod
    def title_required(cls, value: str) -> str:
        if not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("thumbnail_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value:
            return value
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ("draft",):
            raise ValueError("status must be draft on create; use publishing workflow endpoints")
        return "draft"


class EpisodeUpdate(BaseModel):
    episode_number: int | None = Field(default=None, ge=0, le=10000)
    title: str | None = None
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    release_date: date | None = None
    thumbnail_url: str | None = None

    @field_validator("title", "description", "thumbnail_url", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return _trim(value)

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("thumbnail_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return value


class EpisodeOut(ORMModel):
    id: int
    season_id: int
    series_id: int
    episode_number: int
    tmdb_id: int | None = None
    metadata_source: str = ""
    demo_owned: bool = False
    has_demo_clip: bool = False
    title: str
    description: str = ""
    duration_minutes: int | None = None
    release_date: date | None = None
    thumbnail_url: str = ""
    status: str
    published_at: datetime | None = None
    scheduled_publish_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    hls_path: str | None = None
    playable: bool = False
    has_playable_package: bool = False
    has_external_media: bool = False
    audio_availability: AudioAvailabilityOut = Field(default_factory=AudioAvailabilityOut)
    subtitle_availability: SubtitleAvailabilityOut = Field(default_factory=SubtitleAvailabilityOut)

    # Compatibility
    season: int | None = None
    episode: int | None = None
    duration: int | None = None
    thumbnail: str = ""


class DashboardStats(BaseModel):
    total_movies: int
    published_movies: int
    draft_movies: int
    total_series: int
    published_series: int
    total_seasons: int
    total_episodes: int
    total_genres: int


class PublishAction(BaseModel):
    detail: str = "ok"
    status: str


# Ensure model rebuild for forward refs if needed
GenreOut.model_rebuild()
MovieOut.model_rebuild()
SeriesOut.model_rebuild()
