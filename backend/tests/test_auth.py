"""Tests for account auth + admin gating."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.enums import UserRole
from app.main import app
from app.models import User


def test_user_model_defaults_role_to_user(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_users.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, future=True)
    db = Session()
    try:
        u = User(email="a@b.com", password_hash="x")
        db.add(u)
        db.commit()
        db.refresh(u)
        assert u.role == UserRole.user.value
        assert u.id and len(u.id) == 36
        assert u.created_at is not None
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)

    def _override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        c._Session = Session  # stash for tests that need a raw session
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def test_register_returns_user_role_without_hash(client):
    r = client.post("/api/auth/register", json={"email": "u@x.com", "password": "password123"})
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["role"] == "user"
    assert "password_hash" not in body["user"]
    assert body["token"]


def test_register_duplicate_is_409(client):
    client.post("/api/auth/register", json={"email": "d@x.com", "password": "password123"})
    r = client.post("/api/auth/register", json={"email": "d@x.com", "password": "password123"})
    assert r.status_code == 409


def test_register_short_password_is_422(client):
    r = client.post("/api/auth/register", json={"email": "s@x.com", "password": "short"})
    assert r.status_code == 422


def test_login_good_and_bad(client):
    client.post("/api/auth/register", json={"email": "l@x.com", "password": "password123"})
    ok = client.post("/api/auth/login", json={"email": "l@x.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["token"]
    bad = client.post("/api/auth/login", json={"email": "l@x.com", "password": "nope"})
    assert bad.status_code == 401


def test_me_requires_token(client):
    reg = client.post("/api/auth/register", json={"email": "m@x.com", "password": "password123"})
    token = reg.json()["token"]
    assert client.get("/api/auth/me").status_code == 401
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "m@x.com"
