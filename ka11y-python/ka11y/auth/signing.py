"""
ka11y/auth/signing.py
=====================
Authenticated encryption for the two auth cookies (AES-256-GCM).

    token = sign(payload)          # "v2.<base64url(nonce ‖ ciphertext ‖ tag)>"
    payload = unsign(token)        # None if the token was tampered with,
                                   # forged, or made with another secret

The names ``sign``/``unsign`` are kept from the earlier HMAC-only scheme so
callers did not change; the semantics are now *sealed*: nothing in the cookie
is readable without ``KA11Y_SESSION_SECRET`` and any bit flip is rejected.
Legacy HMAC tokens (``<payload>.<hex>``) are refused, so a deploy of this
version signs everybody out once.

Key handling
------------
``KA11Y_SESSION_SECRET`` is any long random string. A 256-bit AES key is
derived from it with HKDF-SHA256 (fixed info string, no salt) so the
operator never has to hand us raw key bytes, and rotating the secret rotates
the key. The derivation is cached per secret value.

Nonce
-----
96-bit random nonce per token from ``os.urandom``; GCM's collision bound
(2^32 messages per key) is far above the number of logins a pilot sees, and
the session secret is expected to rotate long before that anyway.
"""

from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ka11y.auth.config import settings

_VERSION = "v2"
_NONCE_BYTES = 12
_KEY_INFO = b"ka11y-auth-cookie-aes256gcm-v2"
# Bound to the ciphertext so a token cannot be replayed under another version
# label if one is ever introduced.
_AAD = _VERSION.encode("ascii")


@lru_cache(maxsize=4)
def _derive_key(secret: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_KEY_INFO,
    ).derive(secret.encode("utf-8"))


def _key() -> bytes:
    secret = settings().session_secret
    if not secret:
        raise RuntimeError("KA11Y_SESSION_SECRET is not set")
    if len(secret) < 32:
        raise RuntimeError("KA11Y_SESSION_SECRET must be at least 32 characters")
    return _derive_key(secret)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: str) -> str:
    """Seal ``payload`` (any str) into an opaque, URL-safe cookie value."""
    nonce = os.urandom(_NONCE_BYTES)
    sealed = AESGCM(_key()).encrypt(nonce, payload.encode("utf-8"), _AAD)
    return f"{_VERSION}.{_b64e(nonce + sealed)}"


def unsign(token: Optional[str]) -> Optional[str]:
    """Open a token made by :func:`sign`; ``None`` for anything else."""
    if not token or "." not in token:
        return None
    version, _, body = token.partition(".")
    if version != _VERSION or not body or "." in body:
        return None
    try:
        raw = _b64d(body)
    except (ValueError, TypeError):
        return None
    if len(raw) <= _NONCE_BYTES + 16:  # nonce + GCM tag, at least
        return None
    nonce, sealed = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    try:
        return AESGCM(_key()).decrypt(nonce, sealed, _AAD).decode("utf-8")
    except (InvalidTag, UnicodeDecodeError):
        return None


def sign_json(data: Dict[str, Any]) -> str:
    return sign(json.dumps(data, separators=(",", ":"), sort_keys=True))


def unsign_json(token: Optional[str]) -> Optional[Dict[str, Any]]:
    payload = unsign(token)
    if payload is None:
        return None
    try:
        parsed = json.loads(payload)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None
