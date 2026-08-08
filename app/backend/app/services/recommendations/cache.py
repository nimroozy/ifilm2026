"""Short-lived in-process recommendation cache.

Invalidation triggers (documented for ops/QA):
- watch progress create/update/complete/delete/clear
- continue-watching dismiss
- watchlist add/remove/clear
- catalog publish/unpublish/archive (global catalog feature bump)

Process-local by design for V1 — no Redis, no persisted preference rows.
Derived profiles are rebuilt after TTL or invalidation.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from app.services.recommendations.weights import CACHE_TTL_SECONDS

_lock = threading.RLock()
_user_entries: dict[str, tuple[float, Any]] = {}
_catalog_feature_epoch = 0


def _now() -> float:
    return time.monotonic()


def catalog_feature_epoch() -> int:
    return _catalog_feature_epoch


def bump_catalog_feature_epoch() -> None:
    """Call when published catalog membership meaningfully changes."""
    global _catalog_feature_epoch
    with _lock:
        _catalog_feature_epoch += 1
        # Drop all caches — catalog membership changed.
        _user_entries.clear()


def invalidate_user_recommendation_cache(subscriber_id: int | None = None) -> None:
    """Drop cached recommendations for one user, or all users when id is None."""
    with _lock:
        if subscriber_id is None:
            _user_entries.clear()
            return
        prefix = f"u:{int(subscriber_id)}:"
        for key in list(_user_entries):
            if key.startswith(prefix):
                del _user_entries[key]


def cache_get(key: str) -> Any | None:
    with _lock:
        row = _user_entries.get(key)
        if row is None:
            return None
        expires_at, value = row
        if _now() >= expires_at:
            del _user_entries[key]
            return None
        return value


def cache_set(key: str, value: Any, *, ttl_seconds: float | None = None) -> None:
    ttl = CACHE_TTL_SECONDS if ttl_seconds is None else max(1.0, float(ttl_seconds))
    with _lock:
        _user_entries[key] = (_now() + ttl, value)
        # Soft bound to avoid unbounded growth in long-lived workers.
        if len(_user_entries) > 2000:
            cutoff = _now()
            stale = [k for k, (exp, _) in _user_entries.items() if exp <= cutoff]
            for k in stale[:500]:
                _user_entries.pop(k, None)
