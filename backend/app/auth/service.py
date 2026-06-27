"""Auth service: account creation, authentication, admin seeding/promotion."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..enums import UserRole
from ..models import User
from .security import hash_password, verify_password

__all__ = [
    "User",
    "EmailTakenError",
    "UserNotFoundError",
    "register_user",
    "authenticate",
    "get_user_by_id",
    "seed_admin",
    "promote_to_admin",
]


class EmailTakenError(Exception):
    """Raised when registering an email that already exists."""


class UserNotFoundError(Exception):
    """Raised when promoting an email that has no account."""


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def register_user(db: Session, email: str, password: str, role: str = UserRole.user.value) -> User:
    email = _norm(email)
    if db.scalar(select(User).where(User.email == email)):
        raise EmailTakenError(email)
    user = User(email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == _norm(email)))
    if user and verify_password(password, user.password_hash):
        return user
    return None


def get_user_by_id(db: Session, uid: str) -> User | None:
    if not uid:
        return None
    return db.get(User, uid)


def seed_admin(db: Session) -> None:
    if db.scalar(select(User).where(User.role == UserRole.admin.value)):
        return
    try:
        register_user(db, settings.admin_email, settings.admin_password, role=UserRole.admin.value)
    except EmailTakenError:
        promote_to_admin(db, settings.admin_email)
    if settings.admin_password == "admin12345":
        print(
            f"⚠️  Seeded default admin {settings.admin_email!r} with the DEFAULT password. "
            "Set ADMIN_PASSWORD before any real deployment."
        )


def promote_to_admin(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == _norm(email)))
    if not user:
        raise UserNotFoundError(email)
    user.role = UserRole.admin.value
    db.commit()
    db.refresh(user)
    return user
