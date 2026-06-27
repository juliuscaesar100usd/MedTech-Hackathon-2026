# Account Auth + Admin Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full account system (register/login/roles) and gate the entire admin surface to `role="admin"` while leaving user-facing features public.

**Architecture:** Backend grows an `app/auth/` package (stdlib pbkdf2 password hashing + HMAC-signed tokens — no new deps), a `/api/auth` router, and a one-line `require_admin` dependency on the existing admin router. A default admin is seeded on startup; `scripts/make_admin.py` promotes others. Frontend gains an `AuthContext`, login/register pages, an `Authorization: Bearer` header injector in the API client, a conditional "Admin" nav item, and a `RequireAdmin` route guard.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (SQLite via `create_all`, Alembic-free) · pydantic v2 / pydantic-settings · React 18 + react-router-dom + Vite/TypeScript · pytest + FastAPI TestClient.

## Global Constraints

- **No new dependencies** (backend or frontend). Auth crypto uses stdlib `hashlib` / `hmac` / `secrets` / `base64` / `json` / `time` only.
- **No DB migration.** Tables are created by `Base.metadata.create_all` inside `init_db()`; adding the `User` model is sufficient.
- **Self-registration is hard-wired to `role="user"`.** Role is never read from request input. Admin exists only via seed or CLI.
- **`password_hash` never appears in any API response** (response schemas exclude it).
- **User-facing routes stay public** — do not add auth to `services`, `partners`, `search`, `assistant`, `price-history`.
- Run all backend commands from `~/MedTech-Hackathon-2026/backend` with the venv active (`. .venv/bin/activate`). Run frontend commands from `~/MedTech-Hackathon-2026/frontend`.
- Existing model conventions: 36-char UUID string PKs via `_uuid`, UTC timestamps via `_now`, `Mapped[...]` / `mapped_column`.
- Work happens on branch `feature/auth-admin-gating`.

---

### Task 1: Data layer — `UserRole` enum, `User` model, config knobs

**Files:**
- Modify: `backend/app/enums.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_auth.py` (new — first test only)

**Interfaces:**
- Produces: `UserRole` enum (`UserRole.user.value == "user"`, `UserRole.admin.value == "admin"`); `User` model with `id, email, password_hash, role, created_at`; settings fields `auth_secret`, `auth_token_ttl_seconds`, `admin_email`, `admin_password`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/MedTech-Hackathon-2026/backend && . .venv/bin/activate && pytest tests/test_auth.py -q`
Expected: FAIL — `ImportError: cannot import name 'UserRole'` (or `User`).

- [ ] **Step 3a: Add the `UserRole` enum**

Append to `backend/app/enums.py`:

```python
class UserRole(str, Enum):
    user = "user"
    admin = "admin"
```

- [ ] **Step 3b: Add the `User` model**

In `backend/app/models.py`, add `UserRole` to the existing `from .enums import (...)` block, then append this model at the end of the file:

```python
# --------------------------------------------------------------------------- #
# Auth — application accounts (admin-gating + future user features)
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=UserRole.user.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

- [ ] **Step 3c: Add the auth config knobs**

In `backend/app/config.py`, add inside the `Settings` class (e.g. after the `# --- API ---` block):

```python
    # --- Auth ---
    # Secret for HMAC-signing session tokens. MUST be overridden in production
    # (set AUTH_SECRET). The default is intentionally insecure.
    auth_secret: str = "dev-insecure-change-me"
    auth_token_ttl_seconds: int = 86400  # 24h
    # Seeded default admin (created on startup if no admin exists).
    admin_email: str = "admin@medarchive"
    admin_password: str = "admin12345"  # override via ADMIN_PASSWORD
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/enums.py backend/app/models.py backend/app/config.py backend/tests/test_auth.py
git commit -m "feat(auth): add User model, UserRole enum, auth config knobs"
```

---

### Task 2: Security primitives — `app/auth/security.py`

**Files:**
- Create: `backend/app/auth/__init__.py` (empty)
- Create: `backend/app/auth/security.py`
- Test: `backend/tests/test_auth_security.py` (new)

**Interfaces:**
- Consumes: `settings.auth_secret`, `settings.auth_token_ttl_seconds`.
- Produces: `hash_password(password: str) -> str`; `verify_password(password: str, stored: str) -> bool`; `make_token(user_id: str, role: str, ttl: int | None = None, now: int | None = None) -> str`; `verify_token(token: str, now: int | None = None) -> dict | None` (payload has `sub`, `role`, `exp`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_security.py`:

```python
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
    assert security.verify_token(tok, now=1011) is None  # exp == 1010


def test_token_tampered_is_rejected():
    tok = security.make_token("uid-123", "user", now=1000)
    payload_b64, _sig = tok.split(".")
    forged = f"{payload_b64}.{'A' * 43}"
    assert security.verify_token(forged, now=1001) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_security.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/auth/__init__.py` (empty file).

Create `backend/app/auth/security.py`:

```python
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
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, iters)
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
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(_sign(payload_b64), sig):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth_security.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/__init__.py backend/app/auth/security.py backend/tests/test_auth_security.py
git commit -m "feat(auth): stdlib password hashing + HMAC signed tokens"
```

---

### Task 3: Auth service + schemas — `app/auth/service.py`, `app/schemas.py`

**Files:**
- Create: `backend/app/auth/service.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_auth_service.py` (new)

**Interfaces:**
- Consumes: `hash_password`, `verify_password` (Task 2); `User`, `UserRole`; `settings.admin_email`, `settings.admin_password`.
- Produces: `register_user(db, email, password, role=UserRole.user.value) -> User`; `authenticate(db, email, password) -> User | None`; `get_user_by_id(db, uid) -> User | None`; `seed_admin(db) -> None`; `promote_to_admin(db, email) -> User`; exceptions `EmailTakenError`, `UserNotFoundError`. Schemas `RegisterRequest`, `LoginRequest`, `UserOut`, `TokenResponse`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.service'`.

- [ ] **Step 3a: Write the service**

Create `backend/app/auth/service.py`:

```python
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
    register_user(db, settings.admin_email, settings.admin_password, role=UserRole.admin.value)
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
```

- [ ] **Step 3b: Add the auth schemas**

In `backend/app/schemas.py`, add `field_validator` to the pydantic import line (`from pydantic import BaseModel, ConfigDict, Field, field_validator`) and append at the end of the file:

```python
# --------------------------- Auth ------------------------------------------- #
class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=256)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _looks_like_email(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("invalid email")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(ORMModel):
    id: str
    email: str
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    token: str
    user: UserOut
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth_service.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/service.py backend/app/schemas.py backend/tests/test_auth_service.py
git commit -m "feat(auth): auth service (register/login/seed/promote) + schemas"
```

---

### Task 4: Auth dependencies + router + mount — `app/auth/deps.py`, `app/api/auth.py`, `app/main.py`

**Files:**
- Create: `backend/app/auth/deps.py`
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth.py` (append endpoint tests + fixtures)

**Interfaces:**
- Consumes: `verify_token` (Task 2); `get_user_by_id`, `authenticate`, `register_user`, `EmailTakenError` (Task 3); `make_token` (Task 2); schemas `RegisterRequest`, `LoginRequest`, `TokenResponse`, `UserOut` (Task 3); `get_db` from `app.api.deps`.
- Produces: `get_current_user(...) -> User | None`; `require_admin(...) -> User`; router mounted at `/api/auth` with `POST /register`, `POST /login`, `GET /me`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_auth.py` (keep the Task-1 test; add fixtures + these):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth.py -q`
Expected: FAIL — 404 on `/api/auth/register` (router not mounted) / import errors.

- [ ] **Step 3a: Write the dependencies**

Create `backend/app/auth/deps.py`:

```python
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
    return get_user_by_id(db, payload.get("sub"))


def require_admin(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if user.role != UserRole.admin.value:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user
```

- [ ] **Step 3b: Write the router**

Create `backend/app/api/auth.py`:

```python
"""Auth router: register / login / me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..auth.security import make_token
from ..auth.service import EmailTakenError, authenticate, register_user
from ..models import User
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from .deps import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = register_user(db, body.email, body.password)
    except EmailTakenError:
        raise HTTPException(status_code=409, detail="Email already registered.")
    return TokenResponse(token=make_token(user.id, user.role), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return TokenResponse(token=make_token(user.id, user.role), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user
```

- [ ] **Step 3c: Mount the router**

In `backend/app/main.py`, add `auth,` to the `from .api import (...)` tuple (keep alphabetical: it goes first), then add the include line next to the others:

```python
app.include_router(auth.router, prefix=_prefix, tags=["auth"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth.py -q`
Expected: PASS (all register/login/me tests pass).

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/deps.py backend/app/api/auth.py backend/app/main.py backend/tests/test_auth.py
git commit -m "feat(auth): /api/auth register/login/me + current-user dependency"
```

---

### Task 5: Gate the admin surface + seed admin on startup

**Files:**
- Modify: `backend/app/api/admin.py` (router definition)
- Modify: `backend/app/main.py` (lifespan seeding)
- Test: `backend/tests/test_auth.py` (append gate tests)

**Interfaces:**
- Consumes: `require_admin` (Task 4); `seed_admin` (Task 3); `make_token` (Task 2).
- Produces: all `/api/admin/*` return 401 (no token) / 403 (non-admin) / 200 (admin). A default admin row exists after startup.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_auth.py`:

```python
def _token_for(client, role):
    """Register a user, force its role in the DB, return a fresh token for it."""
    from app.auth.security import make_token
    from app.models import User as U
    email = f"{role}@gate.com"
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    s = client._Session()
    try:
        u = s.query(U).filter(U.email == email).one()
        u.role = role
        s.commit()
        return make_token(u.id, u.role)
    finally:
        s.close()


def test_admin_dashboard_requires_admin(client):
    # no token -> 401
    assert client.get("/api/admin/dashboard").status_code == 401
    # user token -> 403
    user_tok = _token_for(client, "user")
    assert client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {user_tok}"}).status_code == 403
    # admin token -> 200
    admin_tok = _token_for(client, "admin")
    assert client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {admin_tok}"}).status_code == 200


def test_public_endpoint_stays_open(client):
    # A user-facing endpoint must still work with no auth at all.
    assert client.get("/api/services").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth.py -k gate -q` and `pytest tests/test_auth.py -k public -q`
Expected: FAIL — admin dashboard returns 200 without a token (gate not yet applied).

- [ ] **Step 3a: Gate the admin router**

In `backend/app/api/admin.py`: add the import `from ..auth.deps import require_admin` (next to `from .deps import ...`), and change the router definition line:

```python
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
```

(`Depends` is already imported in `admin.py`.)

- [ ] **Step 3b: Seed the admin on startup**

In `backend/app/main.py`, replace the `lifespan` function body so it seeds after `init_db()`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    init_db()
    from .auth.service import seed_admin
    from .database import SessionLocal

    db = SessionLocal()
    try:
        seed_admin(db)
    finally:
        db.close()
    yield
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth.py -q`
Expected: PASS (gate + public tests pass).

- [ ] **Step 5: Run the FULL backend suite (regression gate)**

Run: `pytest -q`
Expected: PASS. If any pre-existing admin-endpoint test now fails with 401/403, it was calling an admin route without auth — fix it by adding an admin token header (use the `_token_for` helper pattern), since gating those routes is the intended behavior. Do not weaken the gate.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/admin.py backend/app/main.py backend/tests/test_auth.py
git commit -m "feat(auth): gate /api/admin/* to admins + seed default admin on startup"
```

---

### Task 6: `make_admin` CLI + `.env.example`

**Files:**
- Create: `backend/scripts/make_admin.py`
- Modify: `.env.example`
- Test: `backend/tests/test_auth_service.py` (append a CLI test)

**Interfaces:**
- Consumes: `promote_to_admin`, `UserNotFoundError`, `register_user` (Task 3); `init_db`, `SessionLocal`.
- Produces: `python -m scripts.make_admin <email>` promotes an account; `main(argv) -> int` returns 0 success / 1 not-found / 2 usage.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_auth_service.py`:

```python
def test_make_admin_cli_promotes(tmp_path, monkeypatch):
    # Point the app at a temp SQLite DB, then drive the CLI's main().
    db_url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    # Rebuild engine/session bound to the temp DB.
    import importlib
    import app.database as database
    importlib.reload(database)

    database.init_db()
    s = database.SessionLocal()
    try:
        service.register_user(s, "cli@example.com", "password123")
    finally:
        s.close()

    from scripts import make_admin
    importlib.reload(make_admin)
    assert make_admin.main(["cli@example.com"]) == 0
    assert make_admin.main(["missing@example.com"]) == 1
    assert make_admin.main([]) == 2
```

> Note: this test reloads `app.database` against a temp DB. If `app.config.settings` has already cached `database_url`, the reload picks up the env var because `Settings()` re-reads the environment. Keep this test last in the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_service.py -k make_admin -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.make_admin'`.

- [ ] **Step 3a: Write the CLI**

Create `backend/scripts/make_admin.py`:

```python
"""CLI: promote a registered account to admin.

    python -m scripts.make_admin user@example.com
"""
from __future__ import annotations

import sys

from app.auth.service import UserNotFoundError, promote_to_admin
from app.database import SessionLocal, init_db


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m scripts.make_admin <email>")
        return 2
    email = argv[0]
    init_db()
    db = SessionLocal()
    try:
        user = promote_to_admin(db, email)
    except UserNotFoundError:
        print(f"No account with email {email!r}. Register it first, then promote.")
        return 1
    finally:
        db.close()
    print(f"✓ {user.email} is now an admin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3b: Document the env vars**

Append to `.env.example`:

```bash
# --- Auth ---
# Secret used to HMAC-sign session tokens. CHANGE THIS in any real deployment.
AUTH_SECRET=dev-insecure-change-me
# Session token lifetime (seconds). Default 86400 = 24h.
AUTH_TOKEN_TTL_SECONDS=86400
# Default admin, seeded on first startup if no admin exists.
ADMIN_EMAIL=admin@medarchive
ADMIN_PASSWORD=admin12345
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/make_admin.py .env.example backend/tests/test_auth_service.py
git commit -m "feat(auth): make_admin promote CLI + document auth env vars"
```

---

### Task 7: Frontend API client — token store, header injection, 401 handling, auth endpoints

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Produces: `setAuthToken(token: string | null)`, `getAuthToken(): string | null`, types `AuthUser`/`TokenResponse`, and `api.register`, `api.login`, `api.me`. Every request carries `Authorization: Bearer <token>` when a token is set; any `401` clears the token and dispatches a `medarchive:unauthorized` window event.

- [ ] **Step 1: Add the token store** (just below `export const API_BASE ...`)

```ts
// --- Auth token: persisted in localStorage, injected on every request ---
const TOKEN_KEY = 'medarchive_token';
let authToken: string | null = localStorage.getItem(TOKEN_KEY);

export function setAuthToken(token: string | null): void {
  authToken = token;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getAuthToken(): string | null {
  return authToken;
}
```

- [ ] **Step 2: Inject the header + handle 401** — in `request()`, replace the header/body block and add 401 handling.

Replace:

```ts
  const init: RequestInit = { method };
  if (body !== undefined) {
    if (isForm) {
      init.body = body as FormData;
    } else {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
  }
```

with:

```ts
  const init: RequestInit = { method };
  const headers: Record<string, string> = {};
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  if (body !== undefined) {
    if (isForm) {
      init.body = body as FormData;
    } else {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
  }
  init.headers = headers;
```

Then, immediately after `const parsed = await parseBody(res);`, add:

```ts
  if (res.status === 401) {
    setAuthToken(null);
    window.dispatchEvent(new CustomEvent('medarchive:unauthorized'));
  }
```

- [ ] **Step 3: Add auth types** (near the other interfaces, e.g. after `SearchResult`)

```ts
export interface AuthUser {
  id: string;
  email: string;
  role: 'user' | 'admin';
  created_at: string;
}

export interface TokenResponse {
  token: string;
  user: AuthUser;
}
```

- [ ] **Step 4: Add auth endpoint helpers** — inside the `api` object, after the `// --- Public ---` group add:

```ts
  // --- Auth ---
  register(email: string, password: string): Promise<TokenResponse> {
    return request<TokenResponse>('/auth/register', { method: 'POST', body: { email, password } });
  },

  login(email: string, password: string): Promise<TokenResponse> {
    return request<TokenResponse>('/auth/login', { method: 'POST', body: { email, password } });
  },

  me(): Promise<AuthUser> {
    return request<AuthUser>('/auth/me');
  },
```

- [ ] **Step 5: Type-check (the frontend gate)**

Run: `cd ~/MedTech-Hackathon-2026/frontend && npm run build`
Expected: build succeeds (no TS errors).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(auth): web API client — bearer token, 401 handling, auth endpoints"
```

---

### Task 8: Frontend `AuthContext` + provider mount

**Files:**
- Create: `frontend/src/auth/AuthContext.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `api.login/register/me`, `getAuthToken/setAuthToken`, `AuthUser` (Task 7).
- Produces: `<AuthProvider>` and `useAuth(): { user, loading, login, register, logout }`.

- [ ] **Step 1: Write the context**

Create `frontend/src/auth/AuthContext.tsx`:

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, getAuthToken, setAuthToken, type AuthUser } from '../lib/api';

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (email: string, password: string) => Promise<AuthUser>;
  logout: () => void;
}

const USER_KEY = 'medarchive_user';
const AuthContext = createContext<AuthState | null>(null);

function loadStoredUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => (getAuthToken() ? loadStoredUser() : null));
  const [loading, setLoading] = useState<boolean>(!!getAuthToken());

  function persist(u: AuthUser | null) {
    setUser(u);
    if (u) localStorage.setItem(USER_KEY, JSON.stringify(u));
    else localStorage.removeItem(USER_KEY);
  }

  useEffect(() => {
    const onUnauth = () => persist(null);
    window.addEventListener('medarchive:unauthorized', onUnauth);
    if (getAuthToken()) {
      api
        .me()
        .then(persist)
        .catch(() => {
          setAuthToken(null);
          persist(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
    return () => window.removeEventListener('medarchive:unauthorized', onUnauth);
  }, []);

  async function login(email: string, password: string) {
    const { token, user: u } = await api.login(email, password);
    setAuthToken(token);
    persist(u);
    return u;
  }

  async function register(email: string, password: string) {
    const { token, user: u } = await api.register(email, password);
    setAuthToken(token);
    persist(u);
    return u;
  }

  function logout() {
    setAuthToken(null);
    persist(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
```

- [ ] **Step 2: Mount the provider** — in `frontend/src/App.tsx`, import it and wrap the tree:

Add import at the top:

```tsx
import { AuthProvider } from './auth/AuthContext';
```

Wrap the existing `<ToastProvider>...</ToastProvider>` so `AuthProvider` is the outermost element returned by `App`:

```tsx
  return (
    <AuthProvider>
      <ToastProvider>
        {/* ...existing BrowserRouter/Routes unchanged for now... */}
      </ToastProvider>
    </AuthProvider>
  );
```

- [ ] **Step 3: Type-check**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/auth/AuthContext.tsx frontend/src/App.tsx
git commit -m "feat(auth): web AuthProvider/useAuth + mount at app root"
```

---

### Task 9: Login + Register pages, styles, and routes

**Files:**
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/RegisterPage.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.tsx` (add `/login`, `/register` routes)

**Interfaces:**
- Consumes: `useAuth()` (Task 8); `ApiError` from `../lib/api`.
- Produces: routed pages at `/login` and `/register`.

- [ ] **Step 1: Write the Login page**

Create `frontend/src/pages/LoginPage.tsx`:

```tsx
import { useState, type FormEvent } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../lib/api';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const dest = (location.state as { from?: string } | null)?.from ?? '/';

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const user = await login(email, password);
      navigate(user.role === 'admin' ? '/admin' : dest, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={onSubmit}>
        <h1 className="auth-title">Sign in</h1>
        <label className="auth-label">
          Email
          <input className="auth-input" type="email" value={email}
                 onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="auth-label">
          Password
          <input className="auth-input" type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="auth-error">{error}</p>}
        <button className="auth-btn" type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="auth-alt">
          No account? <Link to="/register">Register</Link>
        </p>
      </form>
    </div>
  );
}
```

- [ ] **Step 2: Write the Register page**

Create `frontend/src/pages/RegisterPage.tsx`:

```tsx
import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../lib/api';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    setBusy(true);
    try {
      await register(email, password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Registration failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={onSubmit}>
        <h1 className="auth-title">Create account</h1>
        <label className="auth-label">
          Email
          <input className="auth-input" type="email" value={email}
                 onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="auth-label">
          Password
          <input className="auth-input" type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)} required minLength={8} />
        </label>
        {error && <p className="auth-error">{error}</p>}
        <button className="auth-btn" type="submit" disabled={busy}>
          {busy ? 'Creating…' : 'Create account'}
        </button>
        <p className="auth-alt">
          Have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Add styles** — append to `frontend/src/styles.css`:

```css
/* --- Auth pages --- */
.auth-wrap { display: flex; justify-content: center; padding: 64px 16px; }
.auth-card {
  display: flex; flex-direction: column; gap: 14px;
  width: 100%; max-width: 360px;
  padding: 28px; border-radius: 14px;
  background: #fff; border: 1px solid #e6e9ee;
  box-shadow: 0 8px 30px rgba(16, 24, 40, 0.06);
}
.auth-title { margin: 0 0 6px; font-size: 22px; }
.auth-label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: #475467; }
.auth-input {
  padding: 10px 12px; border-radius: 8px;
  border: 1px solid #d0d5dd; font-size: 15px;
}
.auth-input:focus { outline: none; border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12); }
.auth-btn {
  margin-top: 4px; padding: 11px 14px; border: none; border-radius: 8px;
  background: #2563eb; color: #fff; font-size: 15px; font-weight: 600; cursor: pointer;
}
.auth-btn:disabled { opacity: 0.6; cursor: default; }
.auth-error { margin: 0; color: #b42318; font-size: 13px; }
.auth-alt { margin: 4px 0 0; font-size: 13px; color: #475467; }
```

- [ ] **Step 4: Add the routes** — in `frontend/src/App.tsx`, import the pages and add two routes inside the `<Route element={<Layout />}>` block (e.g. right after the `partners/:id` route):

```tsx
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
```

```tsx
            <Route path="login" element={<LoginPage />} />
            <Route path="register" element={<RegisterPage />} />
```

- [ ] **Step 5: Type-check**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx frontend/src/pages/RegisterPage.tsx frontend/src/styles.css frontend/src/App.tsx
git commit -m "feat(auth): login + register pages, styles, routes"
```

---

### Task 10: Conditional Admin nav + identity/logout + `RequireAdmin` guard

**Files:**
- Create: `frontend/src/components/RequireAdmin.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/App.tsx` (wrap `/admin` in the guard)
- Modify: `frontend/src/styles.css` (nav identity bits)

**Interfaces:**
- Consumes: `useAuth()` (Task 8).
- Produces: `<RequireAdmin>` wrapper; Layout that hides "Admin" for non-admins and shows identity/Login/Logout.

- [ ] **Step 1: Write the guard**

Create `frontend/src/components/RequireAdmin.tsx`:

```tsx
import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="auth-wrap">Загрузка…</div>;
  if (!user || user.role !== 'admin') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}
```

- [ ] **Step 2: Rewrite the Layout** — replace the contents of `frontend/src/components/Layout.tsx` with:

```tsx
import { NavLink, Link, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const baseNav = [
  { to: '/', label: 'Search', end: true },
  { to: '/assistant', label: 'Assistant' },
  { to: '/services', label: 'Services' },
  { to: '/partners', label: 'Partners' },
];

export function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const items = user?.role === 'admin' ? [...baseNav, { to: '/admin', label: 'Admin' }] : baseNav;

  function onLogout() {
    logout();
    navigate('/', { replace: true });
  }

  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="brand">
          <span className="logo">M</span>
          <span className="brand-name">
            Med<b>Archive</b>
          </span>
        </Link>
        <div className="nav-links">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={(item as { end?: boolean }).end}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </div>
        <div className="nav-auth">
          {user ? (
            <>
              <span className="nav-user" title={user.email}>{user.email}</span>
              <button type="button" className="nav-logout" onClick={onLogout}>Logout</button>
            </>
          ) : (
            <NavLink to="/login" className="nav-link">Login</NavLink>
          )}
        </div>
      </div>
    </nav>
  );
}

export function Layout() {
  return (
    <div className="app-shell">
      <NavBar />
      <Outlet />
    </div>
  );
}
```

- [ ] **Step 3: Wrap the admin route** — in `frontend/src/App.tsx`, import the guard and wrap the admin element:

```tsx
import { RequireAdmin } from './components/RequireAdmin';
```

Change the admin route element from `element={<AdminLayout />}` to:

```tsx
            <Route path="admin" element={<RequireAdmin><AdminLayout /></RequireAdmin>}>
```

- [ ] **Step 4: Add nav styles** — append to `frontend/src/styles.css`:

```css
/* --- Nav auth controls --- */
.nav-auth { display: flex; align-items: center; gap: 12px; margin-left: auto; }
.nav-user { font-size: 13px; color: #475467; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nav-logout {
  border: 1px solid #d0d5dd; background: #fff; border-radius: 8px;
  padding: 6px 12px; font-size: 13px; cursor: pointer; color: #344054;
}
.nav-logout:hover { background: #f9fafb; }
```

- [ ] **Step 5: Type-check**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/RequireAdmin.tsx frontend/src/components/Layout.tsx frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat(auth): admin-only nav + identity/logout + RequireAdmin route guard"
```

---

### Task 11: End-to-end acceptance verification + README + final checks

**Files:**
- Modify: `README.md` (auth section)

- [ ] **Step 1: Backend suite green**

Run: `cd ~/MedTech-Hackathon-2026/backend && . .venv/bin/activate && pytest -q`
Expected: PASS (including all `test_auth*`).

- [ ] **Step 2: Reseed/refresh the demo DB so the admin exists**

The seed runs on app startup, but if the DB predates this feature, force it:
Run: `python -c "from app.database import SessionLocal, init_db; from app.auth.service import seed_admin; init_db(); db=SessionLocal(); seed_admin(db); db.close()"`
Expected: prints the default-password warning (admin seeded).

- [ ] **Step 3: Start both servers**

Backend: `uvicorn app.main:app --host 127.0.0.1 --port 8000` (background)
Frontend: `cd ~/MedTech-Hackathon-2026/frontend && npm run dev` (background)

- [ ] **Step 4: Verify the acceptance criteria with curl**

```bash
# 1. public endpoints work with no auth
curl -s -o /dev/null -w "services(public): %{http_code}\n" http://localhost:8000/api/services
# 2. admin dashboard blocked without token
curl -s -o /dev/null -w "dashboard(no auth): %{http_code}\n" http://localhost:8000/api/admin/dashboard      # expect 401
# 3. admin login + access
TOK=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@medarchive","password":"admin12345"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w "dashboard(admin): %{http_code}\n" -H "Authorization: Bearer $TOK" http://localhost:8000/api/admin/dashboard  # expect 200
# 4. a fresh user is role=user and blocked from admin
UTOK=$(curl -s -X POST http://localhost:8000/api/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"demo.user@x.com","password":"password123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w "dashboard(user): %{http_code}\n" -H "Authorization: Bearer $UTOK" http://localhost:8000/api/admin/dashboard  # expect 403
```
Expected: `200`, `401`, `200`, `403` respectively.

- [ ] **Step 5: Manual UI walk-through** (open http://localhost:5173)

Confirm:
- Anonymous: Search / Assistant / Services / Partners work; no "Admin" nav item; visiting `/admin` redirects to `/login`.
- Register a new account → lands logged in as a user; still no "Admin" nav.
- Logout, then login as `admin@medarchive` / `admin12345` → "Admin" nav appears; the admin section loads.
- `python -m scripts.make_admin demo.user@x.com` → re-login as that user → now has admin access.

- [ ] **Step 6: Stop the servers**

```bash
pkill -f "uvicorn app.main:app"; pkill -f "npm run dev"; pkill -f "node.*vite"
```

- [ ] **Step 7: Document auth in the README** — add a short section to `README.md`:

```markdown
## 🔐 Auth (accounts + admin gating)

User-facing features (search, assistant, services, partners) are **public**. The
admin back office is **admin-only**.

- Register/login at `/login` and `/register` (web) or `POST /api/auth/register`,
  `POST /api/auth/login`. New accounts are always role `user`.
- A default admin is seeded on first startup: **`admin@medarchive` / `admin12345`**
  (override with `ADMIN_PASSWORD`; set a real `AUTH_SECRET` for any deployment).
- Promote an existing account: `python -m scripts.make_admin <email>`.
- All `/api/admin/*` endpoints require an admin bearer token (`401` without a token,
  `403` for non-admins).
```

- [ ] **Step 8: Commit**

```bash
git add README.md
git commit -m "docs(auth): document accounts + admin gating in README"
```

---

## Self-Review

**Spec coverage:**
- §4.1 model → Task 1 ✓ · §4.2 security → Task 2 ✓ · §4.3 service → Task 3 ✓ · §4.4 deps → Task 4 ✓ · §4.5 router → Task 4 ✓ · §4.6 admin gate → Task 5 ✓ · §4.7 seed + CLI → Tasks 5, 6 ✓ · §4.8 config → Task 1 ✓ · §5 frontend → Tasks 7–10 ✓ · §6 data flow → Tasks 7–8, 10 ✓ · §7 security props → Tasks 2, 3, 5 ✓ · §8 tests → Tasks 1–6 + 11 ✓ · §10 acceptance criteria → Task 11 ✓.
- Email validation (`422`) → Task 3 (`field_validator`) + Task 4 (test) ✓.

**Placeholder scan:** No TBD/TODO; every code step shows full code; every test step shows the assertion.

**Type consistency:** `make_token(user_id, role, ...)` defined in Task 2 and called identically in Tasks 3 (via router), 4, 5. `require_admin`/`get_current_user` defined in Task 4 and consumed in Task 5. `setAuthToken/getAuthToken/AuthUser/TokenResponse` defined in Task 7 and consumed in Task 8. `useAuth()` shape (`user, loading, login, register, logout`) defined in Task 8 and consumed in Tasks 9, 10.
