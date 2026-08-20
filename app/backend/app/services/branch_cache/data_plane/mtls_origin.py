"""Strict mTLS HTTPS OriginFetcher (Phase 8 staging-candidate / loopback tests).

Disabled by default. Never inherits proxy env. Never follows redirects.
Private keys are read from mounted paths only — never logged or returned.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import ssl
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID

from app.services.branch_cache.data_plane.errors import (
    CODE_ORIGIN,
    CODE_OVERSIZE,
    CODE_TIMEOUT,
    DataPlaneError,
)
from app.services.branch_cache.data_plane.keys import content_type_for, normalize_relative_path
from app.services.branch_cache.data_plane.origin import OriginObject
from app.services.branch_cache.data_plane.origin_allowlist import (
    FixedOriginEndpoint,
    build_object_url,
    parse_fixed_origin_url,
    resolve_and_assert_safe,
)

logger = logging.getLogger("app.branch_cache.mtls_origin")


class MtLsOriginConfigError(ValueError):
    def __init__(self, message: str, *, code: str = "mtls_config") -> None:
        super().__init__(message)
        self.code = code


def _fingerprint_sha256(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex()


def _load_cert(path: Path) -> x509.Certificate:
    data = path.read_bytes()
    return x509.load_pem_x509_certificate(data)


def validate_mounted_cert_material(
    *,
    client_cert_path: Path,
    client_key_path: Path,
    ca_bundle_path: Path,
    now: datetime | None = None,
    require_client_auth_eku: bool = True,
) -> dict[str, Any]:
    """Validate cert files exist with safe perms and basic X.509 constraints.

    Returns public metadata only (fingerprints, notaries) — never key material.
    """
    now = now or datetime.now(tz=UTC)
    for label, path in (
        ("client_cert", client_cert_path),
        ("client_key", client_key_path),
        ("ca_bundle", ca_bundle_path),
    ):
        if not path.is_file() or path.is_symlink():
            raise MtLsOriginConfigError(f"{label} missing or symlink", code="cert_path")
        try:
            mode = path.stat().st_mode & 0o777
        except OSError as exc:
            raise MtLsOriginConfigError(f"{label} unreadable", code="cert_path") from exc
        if label == "client_key" and mode & 0o077:
            raise MtLsOriginConfigError(
                "client key permissions too open (expected <= 0600)", code="key_perms"
            )

    client = _load_cert(client_cert_path)
    if client.not_valid_before_utc > now:
        raise MtLsOriginConfigError("client certificate not yet valid", code="cert_not_yet_valid")
    if client.not_valid_after_utc < now:
        raise MtLsOriginConfigError("client certificate expired", code="cert_expired")

    if require_client_auth_eku:
        try:
            eku_ext = client.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
            eku_value = eku_ext.value
            assert isinstance(eku_value, x509.ExtendedKeyUsage)
            if ExtendedKeyUsageOID.CLIENT_AUTH not in eku_value:
                raise MtLsOriginConfigError(
                    "client certificate missing clientAuth EKU", code="cert_eku"
                )
        except x509.ExtensionNotFound as exc:
            raise MtLsOriginConfigError(
                "client certificate missing EKU extension", code="cert_eku"
            ) from exc

    key_text = client_key_path.read_text(encoding="utf-8")
    if "PRIVATE KEY" not in key_text:
        raise MtLsOriginConfigError("client key file does not look like a private key", code="key")
    # Never return key material.
    pub = client.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    return {
        "client_fingerprint_sha256": _fingerprint_sha256(client),
        "client_not_after": client.not_valid_after_utc.isoformat(),
        "client_subject": client.subject.rfc4514_string(),
        "ca_bundle_sha256": hashlib.sha256(ca_bundle_path.read_bytes()).hexdigest(),
        "public_key_pem_sha256": hashlib.sha256(pub).hexdigest(),
    }


class MtLsHttpsOriginFetcher:
    """Sync OriginFetcher over HTTPS with mandatory mTLS.

    Construction requires an explicit enable flag. TLS verification cannot be
    disabled. Loopback targets require ``allow_loopback_for_tests`` and a
    non-prod-like environment marker.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        client_cert_path: str | Path,
        client_key_path: str | Path,
        ca_bundle_path: str | Path,
        enable_mtls_staging_candidate: bool,
        allow_loopback_for_tests: bool = False,
        app_env: str = "development",
        connect_timeout_seconds: float = 2.0,
        read_timeout_seconds: float = 10.0,
        total_timeout_seconds: float = 15.0,
        max_body_bytes: int = 64 * 1024 * 1024,
        revoked_client_fingerprints: frozenset[str] | None = None,
        http_client: httpx.Client | None = None,
        skip_dns_check: bool = False,
    ) -> None:
        if not enable_mtls_staging_candidate:
            raise MtLsOriginConfigError(
                "ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE must be true",
                code="flag_off",
            )
        env = (app_env or "").strip().lower()
        if env in {"production", "prod"}:
            raise MtLsOriginConfigError(
                "mTLS staging-candidate fetcher forbidden in production",
                code="prod_forbidden",
            )
        if allow_loopback_for_tests and env not in {"test", "development", "dev", "lab"}:
            raise MtLsOriginConfigError(
                "loopback mTLS test mode only allowed in test/development/lab",
                code="loopback_env",
            )

        self.endpoint = parse_fixed_origin_url(
            endpoint_url, allow_loopback=allow_loopback_for_tests
        )
        self.allow_loopback = bool(allow_loopback_for_tests)
        self.client_cert_path = Path(client_cert_path)
        self.client_key_path = Path(client_key_path)
        self.ca_bundle_path = Path(ca_bundle_path)
        self.connect_timeout_seconds = float(connect_timeout_seconds)
        self.read_timeout_seconds = float(read_timeout_seconds)
        self.total_timeout_seconds = float(total_timeout_seconds)
        self.max_body_bytes = int(max_body_bytes)
        self.revoked_client_fingerprints = revoked_client_fingerprints or frozenset()
        self._skip_dns_check = bool(skip_dns_check)
        self._meta = validate_mounted_cert_material(
            client_cert_path=self.client_cert_path,
            client_key_path=self.client_key_path,
            ca_bundle_path=self.ca_bundle_path,
        )
        fp = self._meta["client_fingerprint_sha256"]
        if fp in self.revoked_client_fingerprints:
            raise MtLsOriginConfigError("client certificate revoked", code="cert_revoked")

        self._owns_client = http_client is None
        self._client = http_client or self._build_client()

    def _build_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        ctx.load_verify_locations(cafile=str(self.ca_bundle_path))
        ctx.load_cert_chain(
            certfile=str(self.client_cert_path),
            keyfile=str(self.client_key_path),
        )
        # Fail closed: no plaintext, no optional verify.
        return ctx

    def _build_client(self) -> httpx.Client:
        timeout = httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.read_timeout_seconds,
            pool=self.connect_timeout_seconds,
        )
        return httpx.Client(
            verify=self._build_ssl_context(),
            follow_redirects=False,
            trust_env=False,  # no HTTP(S)_PROXY inheritance
            timeout=timeout,
            headers={"User-Agent": "iFilm-BranchCache-MtLs/8.0"},
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> MtLsHttpsOriginFetcher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def public_metadata(self) -> dict[str, Any]:
        return {
            "endpoint_host": self.endpoint.host,
            "endpoint_port": self.endpoint.port,
            "allow_loopback": self.allow_loopback,
            **self._meta,
        }

    def _object_url(self, *, asset_id: str, package_id: str, relative_path: str) -> str:
        if not self._skip_dns_check:
            resolve_and_assert_safe(self.endpoint.host, allow_loopback=self.allow_loopback)
        return build_object_url(
            self.endpoint,
            asset_id=asset_id,
            package_id=package_id,
            relative_path=relative_path,
        )

    def exists(self, *, asset_id: str, package_id: str, relative_path: str) -> bool:
        try:
            url = self._object_url(
                asset_id=asset_id, package_id=package_id, relative_path=relative_path
            )
            resp = self._client.head(url)
            if resp.status_code == 405:
                resp = self._client.get(url, headers={"Range": "bytes=0-0"})
            return resp.status_code in {200, 206}
        except DataPlaneError:
            return False
        except httpx.HTTPError:
            return False

    def fetch(self, *, asset_id: str, package_id: str, relative_path: str) -> OriginObject:
        rel = normalize_relative_path(relative_path)
        url = self._object_url(asset_id=asset_id, package_id=package_id, relative_path=rel)
        # Log only host + object identity — never full URL with query (none expected).
        logger.info(
            "mtls_origin_fetch host=%s asset=%s package=%s path=%s",
            self.endpoint.host,
            asset_id,
            package_id,
            rel,
        )
        try:
            with self._client.stream("GET", url) as resp:
                if resp.is_redirect or resp.status_code in {301, 302, 303, 307, 308}:
                    raise DataPlaneError("origin redirects forbidden", code=CODE_ORIGIN)
                if resp.status_code == 404:
                    raise DataPlaneError("origin object missing", code=CODE_ORIGIN)
                if resp.status_code >= 400:
                    raise DataPlaneError("origin unavailable", code=CODE_ORIGIN)
                cl = resp.headers.get("content-length")
                if cl is not None:
                    try:
                        if int(cl) > self.max_body_bytes:
                            raise DataPlaneError("object exceeds size limit", code=CODE_OVERSIZE)
                    except ValueError as exc:
                        raise DataPlaneError("invalid content-length", code=CODE_ORIGIN) from exc
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > self.max_body_bytes:
                        raise DataPlaneError("object exceeds size limit", code=CODE_OVERSIZE)
                    chunks.append(chunk)
                data = b"".join(chunks)
        except httpx.TimeoutException as exc:
            raise DataPlaneError("origin timeout", code=CODE_TIMEOUT) from exc
        except httpx.HTTPError as exc:
            raise DataPlaneError("origin unavailable", code=CODE_ORIGIN) from exc

        digest = hashlib.sha256(data).hexdigest()
        ctype = resp.headers.get("content-type") or content_type_for(rel)
        etag = resp.headers.get("etag") or f'W/"{digest[:16]}"'
        return OriginObject(
            key=f"{asset_id}/{package_id}/{rel}",
            data=data,
            size_bytes=len(data),
            content_type=ctype.split(";")[0].strip(),
            checksum_sha256=digest,
            etag=etag,
        )


def assert_endpoint_not_literal_private(endpoint: FixedOriginEndpoint) -> None:
    """Extra guard for staging manifests (non-loopback)."""
    try:
        ip = ipaddress.ip_address(endpoint.host)
    except ValueError:
        return
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        raise MtLsOriginConfigError("staging origin must not be a private IP literal", code="ssrf")
