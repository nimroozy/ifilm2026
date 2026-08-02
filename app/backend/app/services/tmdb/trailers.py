"""Trailer metadata selection. Never downloads or rehosts trailers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TrailerMetadata:
    provider: str
    key: str
    title: str
    official: bool
    language: str
    published_at: datetime | None
    embed_url: str


def youtube_embed_url(key: str) -> str:
    return f"https://www.youtube-nocookie.com/embed/{key}"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def select_trailer(videos_payload: dict[str, Any], *, language: str = "en-US") -> TrailerMetadata | None:
    results = videos_payload.get("results") if isinstance(videos_payload, dict) else None
    if not isinstance(results, list):
        return None
    language_prefix = (language or "").split("-", 1)[0].lower()

    candidates: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        if (item.get("site") or "").lower() != "youtube":
            continue
        if (item.get("type") or "").lower() != "trailer":
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        candidates.append(item)
    if not candidates:
        return None

    def score(item: dict[str, Any]) -> tuple[int, int, int, str]:
        iso = str(item.get("iso_639_1") or "").lower()
        official = 1 if bool(item.get("official")) else 0
        lang = 1 if language_prefix and iso == language_prefix else 0
        published = str(item.get("published_at") or "")
        return official, lang, 1 if published else 0, published

    best = sorted(candidates, key=score, reverse=True)[0]
    key = str(best.get("key") or "").strip()
    provider = "YouTube"
    return TrailerMetadata(
        provider=provider,
        key=key,
        title=str(best.get("name") or "Trailer"),
        official=bool(best.get("official")),
        language=str(best.get("iso_639_1") or ""),
        published_at=_parse_datetime(best.get("published_at")),
        embed_url=youtube_embed_url(key),
    )
