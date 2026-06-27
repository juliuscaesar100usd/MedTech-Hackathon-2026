"""FastAPI auth dependencies: current-user resolution + admin gate."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..api.deps import get_db
from ..enums import UserRole
from ..models import User
from .security import verify_token
from .service import get_user_by_id


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    payload = verify_token(authorization[7:].strip())
    if not payload:
        return None
    uid = payload.get("sub")
    if not uid:
        return None
    return get_user_by_id(db, uid)


def require_admin(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация.")
    if user.role != UserRole.admin.value:
        raise HTTPException(status_code=403, detail="Требуются права администратора.")
    return user
