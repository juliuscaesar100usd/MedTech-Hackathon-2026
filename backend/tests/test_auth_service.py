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


def test_seed_admin_promotes_preexisting_account(db):
    from app.config import settings
    from app.enums import UserRole
    service.register_user(db, settings.admin_email, "password123")  # plain user first
    service.seed_admin(db)  # must NOT raise
    admins = [u for u in db.query(service.User).all() if u.role == UserRole.admin.value]
    assert len(admins) == 1
    assert admins[0].email == settings.admin_email.strip().lower()


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


def test_make_admin_cli_promotes(tmp_path, monkeypatch):
    """Drive the make_admin CLI's main() against an isolated temp SQLite DB."""
    # Build a temp engine + session factory — avoids reloading app.config whose
    # @lru_cache on get_settings() would ignore the monkeypatched DATABASE_URL.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app import models  # noqa: F401  — registers ORM mappers

    db_url = f"sqlite:///{tmp_path / 'cli.db'}"
    engine = create_engine(
        db_url, connect_args={"check_same_thread": False}, future=True
    )
    Base.metadata.create_all(bind=engine)
    TempSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    # Seed a regular user in the temp DB.
    s = TempSession()
    try:
        service.register_user(s, "cli@example.com", "password123")
    finally:
        s.close()

    # Import the CLI and redirect its DB handle to our temp session factory.
    from scripts import make_admin
    monkeypatch.setattr(make_admin, "SessionLocal", TempSession)
    monkeypatch.setattr(make_admin, "init_db", lambda: None)

    assert make_admin.main(["cli@example.com"]) == 0        # promoted → 0
    assert make_admin.main(["missing@example.com"]) == 1    # not found → 1
    assert make_admin.main([]) == 2                         # no args → 2 (usage)
