"""Encrypt/decrypt integration credentials at rest (Fernet)."""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class IntegrationSecretsError(Exception):
    """Safe failure when encryption key is missing or invalid."""


def fernet_from_master_key(master_key: str) -> Fernet:
    raw = (master_key or "").strip()
    if not raw:
        raise IntegrationSecretsError("integration_secrets_key_missing")
    try:
        return Fernet(raw.encode("utf-8") if isinstance(raw, str) else raw)
    except (ValueError, TypeError) as exc:
        raise IntegrationSecretsError("integration_secrets_key_invalid") from exc


def encrypt_secret(*, plaintext: str, master_key: str) -> bytes:
    if not (plaintext or "").strip():
        raise IntegrationSecretsError("integration_secret_empty")
    fernet = fernet_from_master_key(master_key)
    return fernet.encrypt(plaintext.strip().encode("utf-8"))


def decrypt_secret(*, ciphertext: bytes | None, master_key: str) -> str:
    if not ciphertext:
        return ""
    fernet = fernet_from_master_key(master_key)
    try:
        return fernet.decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        logger.warning("integration_secret_decrypt_failed")
        raise IntegrationSecretsError("integration_secret_decrypt_failed") from exc
