"""Symmetric encryption for secrets stored at rest (e.g. WhatsApp access tokens).

Uses Fernet (AES-128-CBC + HMAC-SHA256) keyed by ``WHATSAPP_TOKEN_ENCRYPTION_KEY``.
Generate a key with:

    python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

The key never leaves the server config; ciphertext is what lands in the database, so
a DB dump alone does not expose tenant access tokens.
"""
from __future__ import annotations

from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    key = settings.whatsapp_token_encryption_key
    if not key:
        raise RuntimeError(
            "WHATSAPP_TOKEN_ENCRYPTION_KEY is not configured; cannot encrypt secrets."
        )
    return Fernet(key.encode())


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage. Returns urlsafe-base64 ciphertext."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a secret produced by :func:`encrypt_secret`."""
    return _fernet().decrypt(ciphertext.encode()).decode()
