"""Password hashing (pbkdf2) and HMAC-signed session tokens — stdlib only.

A token is ``b64url(json_payload).b64url(hmac_sha256(secret, payload_b64))`` —
a minimal JWT-equivalent. Verification is constant-time and checks expiry.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from ..config import settings

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must be non-empty")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        iters = int(iters_s)
        if iters < 1:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, iters)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dk, expected)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload_b64: str) -> str:
    sig = hmac.new(
        settings.auth_secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64e(sig)


def make_token(user_id: str, role: str, ttl: int | None = None, now: int | None = None) -> str:
    now = int(time.time()) if now is None else now
    ttl = settings.auth_token_ttl_seconds if ttl is None else ttl
    payload = {"sub": user_id, "role": role, "exp": now + ttl}
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_token(token: str, now: int | None = None) -> dict | None:
    now = int(time.time()) if now is None else now
    try:
        payload_b64, sig = token.split(".")
        expected_sig = _sign(payload_b64)
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(expected_sig, sig):
        return None
    try:
        payload = json.loads(_b64d(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or "exp" not in payload:
        return None
    try:
        if now >= int(payload["exp"]):
            return None
    except (TypeError, ValueError):
        return None
    return payload
