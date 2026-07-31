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

    if settings.radius_mode == "mock" and not is_dev_like(settings.app_env):
        errors.append("RADIUS_MODE=mock is only allowed when APP_ENV is development or test")

    if settings.subscriber_identity_mode == "fixture" and not is_dev_like(settings.app_env):
        errors.append(
            "SUBSCRIBER_IDENTITY_MODE=fixture is only allowed when APP_ENV is development or test"
        )

    if settings.subscriber_identity_mode == "fixture" and not settings.radius_mock_users:
        errors.append("SUBSCRIBER_IDENTITY_MODE=fixture requires RADIUS_MOCK_USERS")

    if is_prod_like(settings.app_env):
        if settings.jwt_secret in UNSAFE_JWT_SECRETS or len(settings.jwt_secret) < 32:
            errors.append("JWT_SECRET is missing, too short, or uses an unsafe default")
        if not settings.database_url:
            errors.append("DATABASE_URL is required")
        elif any(marker in settings.database_url for marker in DEFAULT_DATABASE_MARKERS):
            errors.append("DATABASE_URL uses default/example credentials")
        if settings.radius_secret in UNSAFE_RADIUS_SECRETS:
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
