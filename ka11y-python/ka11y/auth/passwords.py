"""
ka11y/auth/passwords.py
=======================
Password hashing for the e-mail + password sign-in (the alternative to OIDC).

Uses scrypt from the standard library (OpenSSL-backed, no extra dependency)
with a self-describing hash string so parameters can be raised later without
invalidating existing rows::

    scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>

``needs_rehash`` reports rows written with weaker parameters so a successful
login can upgrade them transparently.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGO = "scrypt"
_N = 2**14  # CPU/memory cost — ~20 ms and 16 MiB per hash (OWASP minimum)
_R = 8
_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def password_policy_error(password: str) -> str | None:
    """None when the password is acceptable, else an error code."""
    if len(password) < MIN_PASSWORD_LENGTH or len(password) > MAX_PASSWORD_LENGTH:
        return "weak_password"
    if password.strip() != password:
        return "weak_password"
    return None


def _maxmem(n: int, r: int) -> int:
    """OpenSSL caps scrypt at 32 MiB by default; state the real need (128·n·r
    bytes) plus headroom so raising _N later cannot silently start failing."""
    return 128 * n * r * 2 + 1024 * 1024


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_KEY_BYTES, maxmem=_maxmem(_N, _R)
    )
    return "$".join((_ALGO, str(_N), str(_R), str(_P), _b64(salt), _b64(key)))


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, n, r, p, salt, key = stored.split("$")
        if algo != _ALGO:
            return False
        expected = _unb64(key)
        n_i, r_i, p_i = int(n), int(r), int(p)
        if n_i > 2**20 or r_i > 64 or p_i > 16:  # refuse absurd stored params (DoS guard)
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=_unb64(salt), n=n_i, r=r_i, p=p_i, dklen=len(expected), maxmem=_maxmem(n_i, r_i)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, n, r, p, _salt, _key = stored.split("$")
    except ValueError:
        return True
    return algo != _ALGO or (int(n), int(r), int(p)) != (_N, _R, _P)
