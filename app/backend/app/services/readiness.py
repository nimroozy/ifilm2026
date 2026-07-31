"""Process readiness probes."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.core.config import Settings
from app.db import session as db_session


def check_database() -> dict[str, Any]:
    try:
        with db_session.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": "database_unavailable", "detail": str(exc.__class__.__name__)}


def check_redis(settings: Settings) -> dict[str, Any]:
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1)
        if client.ping():
            return {"ok": True}
        return {"ok": False, "error": "redis_ping_failed"}
    except Exception as exc:
        return {"ok": False, "error": "redis_unavailable", "detail": str(exc.__class__.__name__)}


def readiness_report(settings: Settings) -> dict[str, Any]:
    database = check_database()
    redis_status = check_redis(settings)
    ready = database.get("ok") is True and (
        redis_status.get("ok") is True or not settings.redis_required
    )
    return {
        "status": "ready" if ready else "not_ready",
        "database": database,
        "redis": redis_status,
        "redis_required": settings.redis_required,
    }
