"""Safe audit logging for playback sessions (never log raw tokens or paths)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.streaming.audit")

_FORBIDDEN_KEYS = frozenset(
    {
        "token",
        "raw_token",
        "playback_token",
        "token_hash",
        "authorization",
        "path",
        "storage_path",
        "master_playlist_path",
        "playlist_path",
        "work_path",
        "filesystem_path",
        "absolute_path",
    }
)


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = key.lower()
        if lowered in _FORBIDDEN_KEYS or "token" in lowered or "secret" in lowered:
            continue
        if isinstance(value, dict):
            clean[key] = _sanitize(value)
        else:
            clean[key] = value
    return clean


def record_session_event(event: str, **fields: Any) -> None:
    logger.info("streaming_audit event=%s details=%s", event, _sanitize(fields))
