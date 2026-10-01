"""
Symmetric encryption for sensitive values (OAuth tokens, OAuth state).

Fernet keys are derived deterministically from SECRET_KEY so no additional
env var is required.  Fernet provides AES-128-CBC + HMAC-SHA256 with
a timestamp, making ciphertexts tamper-evident and unique per encryption call.

Each use gets its own key (domain separation), so a ciphertext produced for
one purpose can never be replayed as another.
"""
import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

# Context prefix for OAuth state values. Token encryption uses no prefix so
# that tokens stored before domain separation was introduced still decrypt.
_OAUTH_STATE_CONTEXT = b"prism:oauth-state:"


def _fernet(context: bytes = b"") -> Fernet:
    """Derive a stable 32-byte Fernet key from SECRET_KEY and a context."""
    key_bytes = hashlib.sha256(context + settings.SECRET_KEY.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_token(plain: str) -> str:
    """Encrypt a plaintext token; returns a URL-safe base64 string."""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a token previously encrypted with encrypt_token."""
    return _fernet().decrypt(encrypted.encode()).decode()


def seal_oauth_state(payload: dict[str, Any]) -> str:
    """Encrypt and authenticate an OAuth state payload (URL-safe output)."""
    data = json.dumps(payload, separators=(",", ":")).encode()
    return _fernet(_OAUTH_STATE_CONTEXT).encrypt(data).decode()


def open_oauth_state(sealed: str, *, max_age_seconds: int) -> dict[str, Any]:
    """
    Decrypt an OAuth state produced by seal_oauth_state.

    Raises ValueError if the state was tampered with, was not issued by this
    server, or is older than max_age_seconds.
    """
    try:
        data = _fernet(_OAUTH_STATE_CONTEXT).decrypt(
            sealed.encode(), ttl=max_age_seconds
        )
        payload = json.loads(data)
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise ValueError("Invalid or expired OAuth state") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid OAuth state payload")
    return payload
