"""Tests for the auth service layer (DB-backed)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import service
from app.database import Base
from app.enums import UserRole


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'svc.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, future=True)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def test_register_defaults_to_user_role(db):
    u = service.register_user(db, "New@Example.com ", "password123")
    assert u.role == UserRole.user.value
    assert u.email == "new@example.com"  # normalized


def test_duplicate_email_raises(db):
    service.register_user(db, "dup@example.com", "password123")
    with pytest.raises(service.EmailTakenError):
        service.register_user(db, "dup@example.com", "password123")


def test_authenticate(db):
    service.register_user(db, "log@example.com", "password123")
    assert service.authenticate(db, "log@example.com", "password123") is not None
    assert service.authenticate(db, "log@example.com", "wrong") is None
    assert service.authenticate(db, "missing@example.com", "password123") is None


def test_seed_admin_idempotent_and_promote(db):
    service.seed_admin(db)
    service.seed_admin(db)  # second call is a no-op
    admins = [u for u in db.query(service.User).all() if u.role == UserRole.admin.value]
    assert len(admins) == 1

    service.register_user(db, "future@example.com", "password123")
    promoted = service.promote_to_admin(db, "future@example.com")
    assert promoted.role == UserRole.admin.value
    with pytest.raises(service.UserNotFoundError):
        service.promote_to_admin(db, "nobody@example.com")
