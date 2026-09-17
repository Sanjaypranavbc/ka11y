"""
ka11y/auth/signing.py
=====================
HMAC-SHA256 signing for the two auth cookies. Standard library only.

    token = sign(payload)          # "<payload>.<hex signature>"
    payload = unsign(token)        # None if the signature does not verify

The payload is opaque to this module; callers keep it URL-safe (no dots).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any, Dict, Optional

from ka11y.auth.config import settings


def _key() -> bytes:
    secret = settings().session_secret
    if not secret:
        raise RuntimeError("KA11Y_SESSION_SECRET is not set")
    return secret.encode("utf-8")


def sign(payload: str) -> str:
    sig = hmac.new(_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def unsign(token: Optional[str]) -> Optional[str]:
    if not token or "." not in token:
        return None
    payload, _, sig = token.rpartition(".")
    expected = hmac.new(_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    return payload


def sign_json(data: Dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return sign(base64.urlsafe_b64encode(raw).decode("ascii").rstrip("="))


def unsign_json(token: Optional[str]) -> Optional[Dict[str, Any]]:
    payload = unsign(token)
    if payload is None:
        return None
    try:
        padded = payload + "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:  # noqa: BLE001
        return None
