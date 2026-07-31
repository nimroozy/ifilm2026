"""Startup and environment safety checks."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings

UNSAFE_JWT_SECRETS = {
    "",
    "change-me-in-production",
    "secret",
    "test-secret",
    "jwt-secret",
}

UNSAFE_ADMIN_PASSWORDS = {
    "",
    "admin123",
    "password",
    "admin",
    "123456",
}

UNSAFE_RADIUS_SECRETS = {
    "",
    "testing123",
    "secret",
    "radius",
}

DEFAULT_DATABASE_MARKERS = (
    "ifilm:ifilm@",
    "postgres:postgres@",
    "user:password@",
    "root:root@",
)


class RuntimeConfigurationError(RuntimeError):
    """Raised when process settings are unsafe for the current environment."""


def is_prod_like(app_env: str) -> bool:
    return app_env in {"production", "staging", "prod"}


def is_dev_like(app_env: str) -> bool:
    return app_env in {"development", "dev", "test"}


def fixture_auth_allowed(settings: Settings) -> bool:
    """Fixture subscriber identity is allowed in development/test, or staging with explicit opt-in.

    Production/prod must never allow fixture auth.
    """
    env = (settings.app_env or "").strip().lower()
    if env in {"production", "prod"}:
        return False
    if is_dev_like(env):
        return True
    if env == "staging" and settings.staging_allow_fixture_auth:
        return True
    return False


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: list[str]


UNSAFE_PLAYBACK_SECRETS = {
    "",
    "change-me-in-production",
    "secret",
    "playback-secret",
    "test-secret",
}


def collect_runtime_errors(settings: Settings) -> list[str]:
    errors: list[str] = []

    if settings.radius_mode == "mock" and not fixture_auth_allowed(settings):
        errors.append(
            "RADIUS_MODE=mock is only allowed in development/test, or staging with "
            "STAGING_ALLOW_FIXTURE_AUTH=true"
        )

    if settings.subscriber_identity_mode == "fixture" and not fixture_auth_allowed(settings):
        errors.append(
            "SUBSCRIBER_IDENTITY_MODE=fixture is only allowed in development/test, or staging "
            "with STAGING_ALLOW_FIXTURE_AUTH=true (never in production)"
        )

    if settings.staging_allow_fixture_auth and settings.app_env in {"production", "prod"}:
        errors.append("STAGING_ALLOW_FIXTURE_AUTH must not be enabled when APP_ENV is production")

    if settings.subscriber_identity_mode == "fixture" and not settings.radius_mock_users:
        errors.append("SUBSCRIBER_IDENTITY_MODE=fixture requires RADIUS_MOCK_USERS")

    radius_identity_active = settings.subscriber_identity_mode == "radius" or (
        settings.enable_radius_login and settings.radius_mode == "live"
    )

    # Live Radius entitlement mapping is disabled by default. Production/staging
    # must not enable Radius identity without staging-verified attribute mapping.
    # Staging fixture auth is a separate path and does not enable live Radius.
    if radius_identity_active and not settings.radius_entitlement_mapping_enabled:
        if is_prod_like(settings.app_env):
            errors.append(
                "Live Radius identity is enabled but RADIUS_ENTITLEMENT_MAPPING_ENABLED is false; "
                "Access-Accept alone must never grant entitlement — keep SUBSCRIBER_IDENTITY_MODE="
                "disabled until staging verifies Radius attribute-to-entitlement mapping"
            )

    if settings.radius_entitlement_mapping_enabled:
        missing_attrs = [
            name
            for name, value in (
                ("RADIUS_ATTR_PACKAGE", settings.radius_attr_package),
                ("RADIUS_ATTR_EXPIRATION", settings.radius_attr_expiration),
            )
            if not (value or "").strip()
        ]
        if missing_attrs:
            errors.append(
                "RADIUS_ENTITLEMENT_MAPPING_ENABLED requires configured attributes: "
                + ", ".join(missing_attrs)
            )
        if is_prod_like(settings.app_env) and not settings.radius_enabled:
            errors.append(
                "RADIUS_ENTITLEMENT_MAPPING_ENABLED in staging/production requires RADIUS_ENABLED=true"
            )

    if is_prod_like(settings.app_env):
        if settings.jwt_secret in UNSAFE_JWT_SECRETS or len(settings.jwt_secret) < 32:
            errors.append("JWT_SECRET is missing, too short, or uses an unsafe default")
        if not settings.database_url:
            errors.append("DATABASE_URL is required")
        elif any(marker in settings.database_url for marker in DEFAULT_DATABASE_MARKERS):
            errors.append("DATABASE_URL uses default/example credentials")
        if settings.radius_secret in UNSAFE_RADIUS_SECRETS:
            # Only require a strong secret when Radius transport or mapping is actually used.
            if settings.radius_enabled or radius_identity_active or settings.radius_entitlement_mapping_enabled:
                errors.append("RADIUS_SECRET is missing or uses an unsafe default")
        if (
            settings.admin_bootstrap_password is not None
            and settings.admin_bootstrap_password in UNSAFE_ADMIN_PASSWORDS
        ):
            errors.append("ADMIN_BOOTSTRAP_PASSWORD uses an unsafe default")
        if settings.debug:
            errors.append("DEBUG must be false in staging/production")
        if settings.enable_local_streaming:
            if (
                settings.playback_token_secret in UNSAFE_PLAYBACK_SECRETS
                or len(settings.playback_token_secret) < 32
            ):
                errors.append(
                    "PLAYBACK_TOKEN_SECRET is missing, too short, or uses an unsafe default"
                )

    if is_dev_like(settings.app_env):
        if not settings.jwt_secret:
            errors.append("JWT_SECRET must be set explicitly")
        if not settings.database_url:
            errors.append("DATABASE_URL must be set explicitly")

    if settings.enable_local_streaming:
        if (
            settings.playback_token_secret in UNSAFE_PLAYBACK_SECRETS
            or len(settings.playback_token_secret) < 32
        ):
            errors.append(
                "PLAYBACK_TOKEN_SECRET must be set (min 32 chars) when ENABLE_LOCAL_STREAMING=true"
            )
        if int(settings.playback_token_ttl_seconds) < 60:
            errors.append("PLAYBACK_TOKEN_TTL_SECONDS must be at least 60")

    if settings.enable_radius_login and settings.radius_mode == "mock":
        if not settings.radius_mock_users:
            errors.append("RADIUS_MODE=mock requires RADIUS_MOCK_USERS fixture configuration")

    return errors


def validate_runtime_settings(settings: Settings) -> None:
    errors = collect_runtime_errors(settings)
    if errors:
        # Never include secret values in the error text.
        raise RuntimeConfigurationError("; ".join(errors))


def require_admin_bootstrap_password(settings: Settings) -> str:
    password = settings.admin_bootstrap_password
    if password is None or password.strip() == "":
        raise RuntimeConfigurationError(
            "ADMIN_BOOTSTRAP_PASSWORD must be set explicitly for the seed command"
        )
    if password in UNSAFE_ADMIN_PASSWORDS:
        raise RuntimeConfigurationError(
            "ADMIN_BOOTSTRAP_PASSWORD must not use a known unsafe default value"
        )
    if len(password) < 12:
        raise RuntimeConfigurationError("ADMIN_BOOTSTRAP_PASSWORD must be at least 12 characters")
    return password
