"""
Symmetric encryption for sensitive system settings (e.g. AI provider API keys).

The Fernet scheme (AES-128-CBC + HMAC-SHA256) provides both confidentiality
and integrity: a tampered ciphertext raises InvalidToken instead of returning
garbage.

Key derivation: SHA-256(JWT_SECRET) → base64url → 32-byte Fernet key.

WARNING: If JWT_SECRET is rotated, all encrypted values become undecryptable.
After a secret rotation, re-enter all sensitive settings via the Admin UI.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

# Keys whose values must be encrypted at rest and masked in API responses.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "ai_openai_api_key",
        "ai_anthropic_api_key",
        "ai_gemini_api_key",
        "zenodo_api_token",
        "internet_archive_access_key",
        "internet_archive_secret_key",
        "zotero_api_key",
        "trismegistos_api_key",
    }
)

_MASK = "••••••••"


def _make_fernet(secret: str) -> Fernet:
    """Derive a Fernet instance from *secret* using SHA-256."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_value(plaintext: str, secret: str) -> str:
    """Return Fernet-encrypted ciphertext, or '' if *plaintext* is empty."""
    if not plaintext:
        return ""
    return _make_fernet(secret).encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, secret: str) -> str:
    """Return the decrypted plaintext, or '' if *ciphertext* is empty.

    Raises InvalidToken (from cryptography) if the value has been tampered with
    or was encrypted with a different secret.
    """
    if not ciphertext:
        return ""
    try:
        return _make_fernet(secret).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return ""


def mask_value(value: str) -> str:
    """Return the display-safe mask if the value is non-empty, else ''."""
    return _MASK if value else ""
