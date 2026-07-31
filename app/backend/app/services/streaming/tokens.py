"""Opaque playback token generation and hashing."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from base64 import urlsafe_b64encode

from app.core.config import Settings, get_settings

# URL-safe base64 of 32 bytes → 43 chars without padding.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{40,64}$")


def generate_playback_token() -> str:
    raw = secrets.token_bytes(32)
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def is_well_formed_token(token: str) -> bool:
    if not token or len(token) > 64:
        return False
    return _TOKEN_RE.fullmatch(token) is not None


def hash_playback_token(token: str, settings: Settings | None = None) -> str:
    """HMAC-SHA256 hex digest when secret configured; otherwise SHA-256 of token."""
    cfg = settings or get_settings()
    secret = (cfg.playback_token_secret or "").encode("utf-8")
    raw = token.encode("utf-8")
    if secret:
        return hmac.new(secret, raw, hashlib.sha256).hexdigest()
    return hashlib.sha256(raw).hexdigest()


def hashes_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
