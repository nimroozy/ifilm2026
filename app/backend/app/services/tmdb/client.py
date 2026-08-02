"""Small TMDB API client with host allowlisting and in-process TTL cache."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings

TMDB_API_BASE_URL = "https://api.themoviedb.org/3"
TMDB_API_HOST = "api.themoviedb.org"


class TMDBClientError(RuntimeError):
    """Raised for TMDB client failures with credentials redacted."""


@dataclass
class _CacheEntry:
    expires_at: float
    value: dict[str, Any]


class TMDBClient:
    def __init__(self, settings: Settings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = http_client
        self._cache: dict[tuple[str, tuple[tuple[str, Any], ...]], _CacheEntry] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.settings.tmdb_enabled and self.settings.tmdb_api_read_token)

    def _headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "authorization": f"Bearer {self.settings.tmdb_api_read_token}",
        }

    def _redact(self, text: str) -> str:
        token = self.settings.tmdb_api_read_token
        if token:
            text = text.replace(token, "[REDACTED]")
        return text

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        url = TMDB_API_BASE_URL + path
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != TMDB_API_HOST:
            raise TMDBClientError("Rejected non-TMDB API host")
        return url

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        if not self.enabled:
            raise TMDBClientError("TMDB is disabled or TMDB_API_READ_TOKEN is missing")
        params = {k: v for k, v in params.items() if v is not None and v != ""}
        cache_key = (path, tuple(sorted(params.items())))
        now = time.time()
        ttl = int(self.settings.tmdb_cache_ttl_seconds or 0)
        cached = self._cache.get(cache_key)
        if ttl > 0 and cached is not None and cached.expires_at > now:
            return cached.value

        close_client = False
        client = self._client
        if client is None:
            client = httpx.Client(timeout=float(self.settings.tmdb_request_timeout_seconds))
            close_client = True
        try:
            response = client.get(self._url(path), params=params, headers=self._headers())
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise TMDBClientError("TMDB response was not a JSON object")
        except Exception as exc:  # noqa: BLE001
            raise TMDBClientError(self._redact(f"TMDB request failed: {exc}")) from exc
        finally:
            if close_client:
                client.close()

        if ttl > 0:
            self._cache[cache_key] = _CacheEntry(expires_at=now + ttl, value=payload)
        return payload

    def search_movie(self, query: str, *, page: int = 1, language: str | None = None) -> dict[str, Any]:
        return self._get(
            "/search/movie",
            query=query,
            page=page,
            language=language or self.settings.tmdb_language,
            include_adult=False,
        )

    def search_tv(self, query: str, *, page: int = 1, language: str | None = None) -> dict[str, Any]:
        return self._get(
            "/search/tv",
            query=query,
            page=page,
            language=language or self.settings.tmdb_language,
            include_adult=False,
        )

    def movie_details(self, tmdb_id: int, *, language: str | None = None) -> dict[str, Any]:
        return self._get(
            f"/movie/{int(tmdb_id)}",
            language=language or self.settings.tmdb_language,
            append_to_response="external_ids,translations,images",
            include_image_language=f"{self.settings.tmdb_language.split('-')[0]},null",
        )

    def tv_details(self, tmdb_id: int, *, language: str | None = None) -> dict[str, Any]:
        return self._get(
            f"/tv/{int(tmdb_id)}",
            language=language or self.settings.tmdb_language,
            append_to_response="external_ids,translations,images",
            include_image_language=f"{self.settings.tmdb_language.split('-')[0]},null",
        )

    def season_details(self, tmdb_id: int, season_number: int, *, language: str | None = None) -> dict[str, Any]:
        return self._get(
            f"/tv/{int(tmdb_id)}/season/{int(season_number)}",
            language=language or self.settings.tmdb_language,
        )

    def configuration(self) -> dict[str, Any]:
        return self._get("/configuration")

    def movie_videos(self, tmdb_id: int, *, language: str | None = None) -> dict[str, Any]:
        return self._get(f"/movie/{int(tmdb_id)}/videos", language=language or self.settings.tmdb_language)

    def tv_videos(self, tmdb_id: int, *, language: str | None = None) -> dict[str, Any]:
        return self._get(f"/tv/{int(tmdb_id)}/videos", language=language or self.settings.tmdb_language)
