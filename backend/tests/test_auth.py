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
