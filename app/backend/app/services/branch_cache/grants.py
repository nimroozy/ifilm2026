"""Asymmetric short-lived edge playback grant primitives (Phase 3).

Private signing keys come only from secret configuration and must never enter
DB rows, APIs, logs, or commits. Verification uses public keys / JWKS only.

Algorithm is pinned to ES256 (ECDSA P-256). HS*/none and alg confusion are rejected.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from jose import JWTError, jwt

from app.core.config import Settings, get_settings
from app.services.branch_cache.validation import (
    BranchCacheValidationError,
    validate_key_id,
    validate_node_id,
)

logger = logging.getLogger(__name__)

EDGE_GRANT_TYP = "edge_grant"
EDGE_GRANT_ALG = "ES256"
# Hard ceiling regardless of config (seconds).
MAX_EDGE_GRANT_TTL_SECONDS = 300
DEFAULT_EDGE_GRANT_TTL_SECONDS = 120
# Reject tokens issued too far in the future (clock abuse).
MAX_IAT_SKEW_SECONDS = 60
# Reject nbf too far ahead.
MAX_NBF_SKEW_SECONDS = 30

# Process-local jti replay cache (bounded). Edge nodes should enforce independently.
_REPLAY_LOCK = threading.Lock()
_REPLAY_JTIS: dict[str, float] = {}
_REPLAY_MAX = 4096


class EdgeGrantError(Exception):
    def __init__(self, message: str, *, code: str = "edge_grant_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EdgeGrantClaims:
    jti: str
    iss: str
    aud: str
    kid: str
    node_id: str
    site_id: str
    package_id: str
    session_id: str
    path_prefix: str
    iat: int
    nbf: int
    exp: int
    typ: str = EDGE_GRANT_TYP

    def as_dict(self) -> dict[str, Any]:
        return {
            "typ": self.typ,
            "jti": self.jti,
            "iss": self.iss,
            "aud": self.aud,
            "nid": self.node_id,
            "sid": self.site_id,
            "pkg": self.package_id,
            "sess": self.session_id,
            "path_prefix": self.path_prefix,
            "iat": self.iat,
            "nbf": self.nbf,
            "exp": self.exp,
        }


def edge_grant_issue_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool(cfg.enable_branch_cache_control_plane and cfg.enable_edge_grant_issue)


def _clamp_ttl(seconds: int) -> int:
    ttl = int(seconds)
    if ttl < 15:
        raise EdgeGrantError("edge grant TTL must be at least 15 seconds", code="ttl_too_short")
    if ttl > MAX_EDGE_GRANT_TTL_SECONDS:
        raise EdgeGrantError(
            f"edge grant TTL must not exceed {MAX_EDGE_GRANT_TTL_SECONDS}s",
            code="ttl_too_long",
        )
    return ttl


def _require_signing_material(settings: Settings) -> tuple[str, str, str]:
    private_pem = (settings.edge_grant_private_key_pem or "").strip()
    public_pem = (settings.edge_grant_public_key_pem or "").strip()
    kid = validate_key_id((settings.edge_grant_key_id or "eg1").strip())
    if not private_pem:
        raise EdgeGrantError(
            "EDGE_GRANT_PRIVATE_KEY_PEM is required to issue grants",
            code="missing_private_key",
        )
    if not public_pem:
        raise EdgeGrantError(
            "EDGE_GRANT_PUBLIC_KEY_PEM is required to issue grants",
            code="missing_public_key",
        )
    if "PRIVATE KEY" not in private_pem:
        raise EdgeGrantError("EDGE_GRANT_PRIVATE_KEY_PEM is malformed", code="bad_private_key")
    if "PUBLIC KEY" not in public_pem and "CERTIFICATE" not in public_pem:
        raise EdgeGrantError("EDGE_GRANT_PUBLIC_KEY_PEM is malformed", code="bad_public_key")
    return private_pem, public_pem, kid


def public_jwks(settings: Settings | None = None) -> dict[str, Any]:
    """Return JWKS-style public verification material (no private key)."""
    cfg = settings or get_settings()
    if not cfg.enable_branch_cache_control_plane:
        return {"keys": []}
    public_pem = (cfg.edge_grant_public_key_pem or "").strip()
    if not public_pem:
        return {"keys": []}
    kid = (cfg.edge_grant_key_id or "eg1").strip()
    # Emit PEM-backed key descriptor; consumers load PEM for ES256 verify.
    # Avoid embedding private material. thumbprint is of public PEM only.
    thumb = hashlib.sha256(public_pem.encode("utf-8")).hexdigest()[:16]
    return {
        "keys": [
            {
                "kty": "EC",
                "alg": EDGE_GRANT_ALG,
                "use": "sig",
                "kid": kid,
                "crv": "P-256",
                "x5t#S256": thumb,
                "public_key_pem": public_pem,
            }
        ]
    }


def issue_edge_grant(
    *,
    node_id: str,
    site_id: str,
    package_id: str,
    session_id: str,
    path_prefix: str,
    settings: Settings | None = None,
    ttl_seconds: int | None = None,
    now: datetime | None = None,
) -> tuple[str, EdgeGrantClaims]:
    """Sign a short-lived edge playback grant. Returns (token, claims).

    Never logs the token or private key.
    """
    cfg = settings or get_settings()
    if not edge_grant_issue_enabled(cfg):
        raise EdgeGrantError("edge grant issue is disabled", code="disabled")

    nid = validate_node_id(node_id)
    pkg = (package_id or "").strip()
    sess = (session_id or "").strip()
    prefix = (path_prefix or "").strip()
    site = (site_id or "").strip().lower()
    if not pkg or len(pkg) > 64:
        raise EdgeGrantError("package_id is required", code="invalid_package")
    if not sess or len(sess) > 64:
        raise EdgeGrantError("session_id is required", code="invalid_session")
    if not prefix.startswith("/") or ".." in prefix or "?" in prefix or "#" in prefix:
        raise EdgeGrantError(
            "path_prefix must be an absolute path without query/fragment", code="invalid_path"
        )
    if len(prefix) > 256:
        raise EdgeGrantError("path_prefix too long", code="invalid_path")
    if not site:
        raise EdgeGrantError("site_id is required", code="invalid_site")

    private_pem, _public_pem, kid = _require_signing_material(cfg)
    ttl = _clamp_ttl(ttl_seconds if ttl_seconds is not None else int(cfg.edge_grant_ttl_seconds))
    clock = now or datetime.now(UTC)
    iat = int(clock.timestamp())
    nbf = iat
    exp = iat + ttl
    jti = secrets.token_urlsafe(16)
    claims = EdgeGrantClaims(
        jti=jti,
        iss=(cfg.edge_grant_issuer or "ifilm-central").strip(),
        aud=(cfg.edge_grant_audience or "ifilm-branch-cache").strip(),
        kid=kid,
        node_id=nid,
        site_id=site,
        package_id=pkg,
        session_id=sess,
        path_prefix=prefix,
        iat=iat,
        nbf=nbf,
        exp=exp,
    )
    token = jwt.encode(
        claims.as_dict(),
        private_pem,
        algorithm=EDGE_GRANT_ALG,
        headers={"alg": EDGE_GRANT_ALG, "kid": kid, "typ": "JWT"},
    )
    return token, claims


def _remember_jti(jti: str, exp: int) -> None:
    now = time.time()
    with _REPLAY_LOCK:
        # Evict expired
        expired = [k for k, until in _REPLAY_JTIS.items() if until <= now]
        for k in expired:
            _REPLAY_JTIS.pop(k, None)
        if jti in _REPLAY_JTIS:
            raise EdgeGrantError("edge grant replay detected", code="replay")
        if len(_REPLAY_JTIS) >= _REPLAY_MAX:
            # Drop oldest
            oldest = sorted(_REPLAY_JTIS.items(), key=lambda kv: kv[1])[:256]
            for k, _ in oldest:
                _REPLAY_JTIS.pop(k, None)
        _REPLAY_JTIS[jti] = float(exp)


def clear_replay_cache_for_tests() -> None:
    with _REPLAY_LOCK:
        _REPLAY_JTIS.clear()


def verify_edge_grant(
    token: str,
    *,
    expected_node_id: str,
    expected_package_id: str | None = None,
    expected_path: str | None = None,
    settings: Settings | None = None,
    public_key_pem: str | None = None,
    enforce_replay: bool = True,
    now: datetime | None = None,
) -> EdgeGrantClaims:
    """Verify an edge grant using public key only. Rejects alg confusion."""
    cfg = settings or get_settings()
    raw = (token or "").strip()
    if not raw or len(raw) > 8192:
        raise EdgeGrantError("invalid edge grant", code="invalid_token")

    # Reject alg confusion before decode: inspect unprotected header.
    try:
        header = jwt.get_unverified_header(raw)
    except JWTError as exc:
        raise EdgeGrantError("invalid edge grant header", code="invalid_header") from exc
    alg = header.get("alg")
    if alg != EDGE_GRANT_ALG:
        raise EdgeGrantError("unsupported or confused algorithm", code="alg_confusion")
    kid = header.get("kid")
    expected_kid = (cfg.edge_grant_key_id or "eg1").strip()
    if kid and kid != expected_kid:
        # Allow rotation: if kid matches an alternate published key later; Phase 3 single kid.
        raise EdgeGrantError("untrusted key id", code="untrusted_kid")

    pem = (public_key_pem or cfg.edge_grant_public_key_pem or "").strip()
    if not pem:
        raise EdgeGrantError("no public verification key configured", code="missing_public_key")

    try:
        payload = jwt.decode(
            raw,
            pem,
            algorithms=[EDGE_GRANT_ALG],
            audience=(cfg.edge_grant_audience or "ifilm-branch-cache").strip(),
            issuer=(cfg.edge_grant_issuer or "ifilm-central").strip(),
            options={
                "require_aud": True,
                "require_iss": True,
                "require_exp": True,
                "require_iat": True,
            },
        )
    except JWTError as exc:
        # Never include token material in message.
        raise EdgeGrantError(
            "edge grant signature or claims invalid", code="verify_failed"
        ) from exc

    if payload.get("typ") != EDGE_GRANT_TYP:
        raise EdgeGrantError("invalid grant type", code="bad_typ")

    clock = now or datetime.now(UTC)
    now_ts = int(clock.timestamp())
    iat = int(payload["iat"])
    exp = int(payload["exp"])
    nbf = int(payload.get("nbf") or iat)
    if iat > now_ts + MAX_IAT_SKEW_SECONDS:
        raise EdgeGrantError("grant issued too far in the future", code="clock_abuse")
    if nbf > now_ts + MAX_NBF_SKEW_SECONDS:
        raise EdgeGrantError("grant not yet valid", code="nbf")
    if now_ts < nbf:
        raise EdgeGrantError("grant not yet valid", code="nbf")
    if now_ts >= exp:
        raise EdgeGrantError("grant expired", code="expired")
    if exp - iat > MAX_EDGE_GRANT_TTL_SECONDS + 5:
        raise EdgeGrantError("grant TTL exceeds policy", code="ttl_too_long")

    nid = validate_node_id(str(payload.get("nid") or ""))
    if nid != validate_node_id(expected_node_id):
        raise EdgeGrantError("grant node binding mismatch", code="node_mismatch")

    pkg = str(payload.get("pkg") or "")
    if expected_package_id is not None and pkg != expected_package_id:
        raise EdgeGrantError("grant package binding mismatch", code="package_mismatch")

    path_prefix = str(payload.get("path_prefix") or "")
    if expected_path is not None:
        path = expected_path if expected_path.startswith("/") else f"/{expected_path}"
        if not path.startswith(path_prefix):
            raise EdgeGrantError("grant path binding mismatch", code="path_mismatch")

    jti = str(payload.get("jti") or "")
    if not jti:
        raise EdgeGrantError("missing jti", code="missing_jti")
    if enforce_replay:
        _remember_jti(jti, exp)

    return EdgeGrantClaims(
        jti=jti,
        iss=str(payload["iss"]),
        aud=str(payload["aud"]),
        kid=str(kid or expected_kid),
        node_id=nid,
        site_id=str(payload.get("sid") or ""),
        package_id=pkg,
        session_id=str(payload.get("sess") or ""),
        path_prefix=path_prefix,
        iat=iat,
        nbf=nbf,
        exp=exp,
    )


def redact_secrets_from_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with known secret fields removed/redacted."""
    blocked = {
        "edge_grant_private_key_pem",
        "private_key",
        "private_key_pem",
        "heartbeat_token",
        "enrollment_token",
        "token",
        "grant",
        "raw_token",
    }
    out: dict[str, Any] = {}
    for k, v in data.items():
        lk = str(k).lower()
        if lk in blocked or "private" in lk and "key" in lk:
            out[k] = "[redacted]"
        elif isinstance(v, dict):
            out[k] = redact_secrets_from_mapping(v)
        else:
            out[k] = v
    return out


# Re-export validation error for callers that misuse node ids in grants.
__all__ = [
    "EDGE_GRANT_ALG",
    "EDGE_GRANT_TYP",
    "MAX_EDGE_GRANT_TTL_SECONDS",
    "BranchCacheValidationError",
    "EdgeGrantClaims",
    "EdgeGrantError",
    "clear_replay_cache_for_tests",
    "edge_grant_issue_enabled",
    "issue_edge_grant",
    "public_jwks",
    "redact_secrets_from_mapping",
    "verify_edge_grant",
]
