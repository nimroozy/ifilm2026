"""Safe SQLAlchemy / Redis URL construction with password encoding."""

from __future__ import annotations

import os
from urllib.parse import quote, urlparse

from sqlalchemy.engine import make_url
from sqlalchemy.engine.url import URL


def encode_url_component(value: str) -> str:
    """Percent-encode a URL userinfo/path component (including ``@ : / # %``)."""
    return quote(value, safe="")


def build_postgres_sqlalchemy_url(
    *,
    user: str,
    password: str,
    host: str,
    database: str,
    port: int = 5432,
    driver: str = "postgresql+psycopg2",
) -> str:
    """Build a SQLAlchemy PostgreSQL URL with a correctly encoded password.

    Never concatenate ``user:password@host`` without encoding — characters such as
    ``@ : / # %`` in the password would otherwise break parsing.
    """
    if not user:
        raise ValueError("postgres user is required")
    if not host:
        raise ValueError("postgres host is required")
    if not database:
        raise ValueError("postgres database is required")
    url = URL.create(
        drivername=driver,
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=database,
    )
    rendered = url.render_as_string(hide_password=False)
    # Round-trip through make_url to prove special characters survive.
    parsed = make_url(rendered)
    if parsed.password != password:
        raise ValueError("constructed DATABASE_URL does not round-trip password")
    if parsed.username != user or parsed.host != host or parsed.database != database:
        raise ValueError("constructed DATABASE_URL failed component validation")
    return rendered


def build_redis_url(
    *,
    host: str,
    port: int = 6379,
    db: int = 0,
    password: str | None = None,
) -> str:
    """Build a redis:// URL; password is encoded when present."""
    if password:
        return f"redis://:{encode_url_component(password)}@{host}:{int(port)}/{int(db)}"
    return f"redis://{host}:{int(port)}/{int(db)}"


def validate_database_url(url: str) -> URL:
    """Parse and validate a DATABASE_URL; raises ValueError on failure."""
    if not url or not str(url).strip():
        raise ValueError("DATABASE_URL is empty")
    try:
        parsed = make_url(url)
    except Exception as exc:  # noqa: BLE001 — surface as ValueError for callers
        raise ValueError(f"DATABASE_URL is not parseable: {exc}") from exc
    if not parsed.drivername.startswith("postgresql") and not parsed.drivername.startswith(
        "sqlite"
    ):
        raise ValueError(f"unsupported DATABASE_URL driver: {parsed.drivername}")
    if parsed.drivername.startswith("postgresql"):
        if not parsed.username or not parsed.host or not parsed.database:
            raise ValueError("DATABASE_URL missing user, host, or database")
        # Detect common broken concatenation: password containing '@' split into host.
        # make_url already handles encoding; check raw string for unencoded userinfo '@'.
        scheme_sep = url.split("://", 1)
        if len(scheme_sep) == 2:
            rest = scheme_sep[1]
            if "@" in rest:
                userinfo, _, hostpart = rest.rpartition("@")
                if userinfo.count(":") >= 1:
                    _user, _, pwd = userinfo.partition(":")
                    if pwd and any(ch in pwd for ch in "@/#") and "%" not in pwd:
                        # Unencoded special chars in password region — reject.
                        raise ValueError(
                            "DATABASE_URL password appears unencoded (contains @, /, or #); "
                            "use build_postgres_sqlalchemy_url()"
                        )
    return parsed


def redact_database_url(url: str) -> str:
    """Return DATABASE_URL with password replaced for safe logging."""
    try:
        parsed = make_url(url)
        if parsed.password is None:
            return url
        return parsed.render_as_string(hide_password=True)
    except Exception:  # noqa: BLE001
        parts = urlparse(url)
        if parts.password:
            netloc = parts.netloc.replace(parts.password, "***")
            return parts._replace(netloc=netloc).geturl()
        return "<unparseable-database-url>"


def database_url_from_postgres_env(env: dict[str, str] | None = None) -> str | None:
    """Build DATABASE_URL from POSTGRES_* components when present.

    Production Compose injects POSTGRES_* only (never a pre-built DATABASE_URL)
    so passwords with ``@ : / # %`` stay safe. Returns None when components are
    incomplete. Never logs the password.
    """
    source = env if env is not None else os.environ
    user = (source.get("POSTGRES_USER") or "").strip()
    password = source.get("POSTGRES_PASSWORD")
    host = (source.get("POSTGRES_HOST") or "postgres").strip()
    database = (source.get("POSTGRES_DB") or "").strip()
    port_raw = (source.get("POSTGRES_PORT") or "5432").strip()
    if not user or password is None or password == "" or not database:
        return None
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"POSTGRES_PORT is invalid: {port_raw!r}") from exc
    url = build_postgres_sqlalchemy_url(
        user=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    validate_database_url(url)
    return url


def resolve_database_url(*, settings_database_url: str | None = None) -> str:
    """Resolve DATABASE_URL for Alembic / maintenance tools.

    Order:
    1. ``DATABASE_URL`` environment variable
    2. settings ``database_url`` (when provided)
    3. Construct from ``POSTGRES_*`` (production Compose contract)
    """
    explicit = (os.getenv("DATABASE_URL") or "").strip()
    if explicit:
        validate_database_url(explicit)
        return explicit
    configured = (settings_database_url or "").strip()
    if configured:
        validate_database_url(configured)
        return configured
    built = database_url_from_postgres_env()
    if built:
        return built
    raise RuntimeError(
        "DATABASE_URL must be set for Alembic, or provide POSTGRES_USER, "
        "POSTGRES_PASSWORD, POSTGRES_DB (and optionally POSTGRES_HOST/PORT)"
    )
