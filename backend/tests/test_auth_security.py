"""Unit tests for stdlib password hashing + signed tokens."""
from __future__ import annotations

from app.auth import security


def test_hash_roundtrip_and_rejects_wrong():
    h = security.hash_password("hunter2pw")
    assert h.startswith("pbkdf2_sha256$")
    assert security.verify_password("hunter2pw", h) is True
    assert security.verify_password("wrong", h) is False


def test_verify_password_handles_garbage():
    assert security.verify_password("x", "not-a-valid-hash") is False
    assert security.verify_password("x", "") is False


def test_token_roundtrip():
    tok = security.make_token("uid-123", "admin", now=1000)
    payload = security.verify_token(tok, now=1001)
    assert payload is not None
    assert payload["sub"] == "uid-123"
    assert payload["role"] == "admin"


def test_token_expired_is_rejected():
    tok = security.make_token("uid-123", "user", ttl=10, now=1000)
    assert security.verify_token(tok, now=1011) is None   # past exp
    assert security.verify_token(tok, now=1010) is None   # at exact exp boundary
    assert security.verify_token(tok, now=1009) is not None  # one second before


def test_token_malformed_non_ascii_returns_none():
    assert security.verify_token("été.fakesig", now=1001) is None
    assert security.verify_token("\xff\xfe.X", now=1001) is None


def test_verify_password_corrupt_iterations_returns_false():
    assert security.verify_password("x", "pbkdf2_sha256$0$abcd$ef01") is False


def test_token_tampered_is_rejected():
    tok = security.make_token("uid-123", "user", now=1000)
    payload_b64, _sig = tok.split(".")
    forged = f"{payload_b64}.{'A' * 43}"
    assert security.verify_token(forged, now=1001) is None
