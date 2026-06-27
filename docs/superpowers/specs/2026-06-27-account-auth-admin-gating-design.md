# Spec: Account-based auth with admin-gated dashboard

**Date:** 2026-06-27
**Status:** Approved design → ready for implementation plan
**Repo:** MedTech-Hackathon-2026 (MedArchive)

## 1. Goal

Add a full account system (register / login / roles) and use it to gate the admin
surface. User-facing features stay **public**; the admin section is **admin-only**.

Self-registration **always** creates `role="user"`. Admin accounts exist only via a
seeded default or an explicit CLI promotion — privilege escalation through the API is
impossible by construction.

## 2. Scope

### In scope
- `User` model + role, password hashing, signed session tokens.
- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`.
- Server-side gate: all `/api/admin/*` endpoints require `role="admin"`.
- Seeded default admin + `scripts/make_admin.py` promotion CLI.
- Frontend: auth context, login/register pages, identity+logout in the header,
  conditional "Admin" nav, `/admin/*` route guard.
- `tests/test_auth.py`.

### Out of scope (YAGNI)
- Password reset / email verification / refresh tokens / OAuth.
- Gating any user-facing route (search, assistant, services, partners stay public).
- Per-resource permissions beyond the two roles.
- Rate limiting on auth endpoints (note as a future hardening item).

### Accepted consequence
Because user features are public, a plain `role="user"` account unlocks nothing
beyond anonymous access. Accounts meaningfully matter only for admins. This is the
direct result of the "user features public, admin gated" decision and is intended.

## 3. Decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Auth weight | Full accounts: register + login + roles |
| Public access | User features public; **only** admin section gated |
| Admin bootstrap | **Both**: seed a default admin **and** ship a promote CLI |
| Crypto deps | **None** — stdlib `hashlib` / `hmac` / `secrets` / `base64` / `json` |
| DB migration | None — `init_db()` `create_all` creates the `users` table idempotently |

## 4. Backend design

### 4.1 Model (`app/models.py`, `app/enums.py`)
- `UserRole` enum in `enums.py`: `USER = "user"`, `ADMIN = "admin"`.
- `User` model:
  - `id: str` — 36-char UUID (match existing model convention).
  - `email: str` — unique, stored lowercased/stripped.
  - `password_hash: str`.
  - `role: str` — defaults to `"user"`.
  - `created_at: datetime` — UTC default (match existing convention).

### 4.2 Security primitives (`app/auth/security.py`)
- `hash_password(pw: str) -> str` — `hashlib.pbkdf2_hmac("sha256", pw, salt, ITERATIONS)`,
  `ITERATIONS = 200_000`, 16-byte `secrets.token_bytes` salt. Stored as
  `"pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>"`.
- `verify_password(pw: str, stored: str) -> bool` — recompute, compare with
  `hmac.compare_digest`. Returns `False` on any malformed/blank input (never raises).
- `make_token(user) -> str` — payload `{"sub": user.id, "role": user.role, "exp": <unix>}`,
  `exp = now + settings.auth_token_ttl_seconds`. Encoding: `b64url(json).b64url(hmac_sha256(secret, json))`.
- `verify_token(token: str) -> dict | None` — recompute signature, `hmac.compare_digest`,
  check `exp`. Returns the payload dict on success, `None` otherwise (expired, bad sig,
  malformed). Never raises.
- Secret: `settings.auth_secret`. Time source passed in / via a tiny helper so tests can
  exercise expiry deterministically.

> Rationale: stdlib over PyJWT+passlib+bcrypt. The security-sensitive steps (KDF,
> constant-time comparison, expiry) use blessed stdlib primitives — no hand-rolled crypto.

### 4.3 Auth service (`app/auth/service.py`)
- `register_user(db, email, password) -> User` — normalize email; raise a 409-mapped
  error if the email already exists; create with `role="user"`.
- `authenticate(db, email, password) -> User | None` — fetch by email, `verify_password`.
- `get_user_by_id(db, uid) -> User | None`.
- `seed_admin(db)` — if no `role="admin"` row exists, create `settings.admin_email`
  with `settings.admin_password`. Log a warning when the default password is in use.
- `promote_to_admin(db, email) -> User` — used by the CLI; raise if email not found.

### 4.4 Dependencies (`app/auth/deps.py`)
- `get_current_user(authorization: str | None, db) -> User | None` — parse
  `Authorization: Bearer <token>`, `verify_token`, load user. Returns `None` if absent/invalid.
- `require_admin(user = Depends(get_current_user))` — `401` if `None`, `403` if
  `user.role != "admin"`, else returns the user.

### 4.5 Router (`app/api/auth.py`) — mounted at `/api/auth`
- `POST /register` — body `{email, password}` → `201`, returns `{token, user}`.
  Duplicate email → `409`. Basic validation: non-empty email containing `@`, password
  length ≥ 8 → else `422`.
- `POST /login` — body `{email, password}` → `200` `{token, user}`; bad creds → `401`.
- `GET /me` — `Depends(get_current_user)`; `401` if not authenticated, else the user.
- `user` is serialized **without** `password_hash` (response schema: `id, email, role, created_at`).

### 4.6 Gate the admin surface (`app/api/admin.py`)
- Add `dependencies=[Depends(require_admin)]` to the `APIRouter(...)` **definition** in
  `app/api/admin.py` (single source of truth, local to the router) — gates all seven
  endpoints (`/upload`, `/catalog`, `/documents`, `/batches`, `/verification`,
  `/verify`, `/dashboard`) at once. `main.py`'s `include_router(admin.router, ...)` is
  left unchanged.

### 4.7 Seeding & CLI
- `seed_admin(db)` is invoked from **two** call sites (so a fresh DB is demo-ready
  whichever entry point runs first): the FastAPI startup event in `app/main.py` (after
  `init_db()`), and at the end of `scripts.bootstrap_demo`. `database.py` does **not**
  import the auth service (preserves the existing layering); seeding lives one layer up.
- `scripts/make_admin.py` — `python -m scripts.make_admin <email>` → `promote_to_admin`.

### 4.8 Config (`app/config.py`)
- `auth_secret: str` — default a clearly-marked dev secret; warn if unset in non-dev.
- `auth_token_ttl_seconds: int` — default `86400` (24h).
- `admin_email: str` — default `admin@medarchive`.
- `admin_password: str` — default `admin12345` (env `ADMIN_PASSWORD`).

## 5. Frontend design

- **`src/auth/AuthContext.tsx`** — `AuthProvider` + `useAuth()` exposing
  `{ user, token, login, register, logout }`; persists `{token, user}` to `localStorage`
  and rehydrates on load.
- **`src/lib/api.ts`** — attach `Authorization: Bearer <token>` when present; add
  `register`, `login`, `me`; on any `401` clear the session.
- **`src/pages/LoginPage.tsx` / `RegisterPage.tsx`** — email + password forms; on success
  store session and redirect (back to the originally-requested page if any, else `/`).
- **`src/components/Layout.tsx`** — when logged in, show the email + a Logout button;
  otherwise a Login link. Render the **"Admin" nav item only when `user?.role === "admin"`**.
- **`src/components/RequireAdmin.tsx`** — wraps the `/admin` route element; non-admins are
  redirected to `/login` (preserving intended destination). Server remains source of truth.
- **`src/App.tsx`** — add `/login` and `/register` routes; wrap the `/admin` branch in
  `RequireAdmin`; mount `AuthProvider` at the app root.

## 6. Data flow

1. Register/login → backend returns `{token, user}` → stored in `localStorage`.
2. `api.ts` attaches `Bearer` on every request.
3. Admin requests hit `require_admin`: no/invalid token → `401`, non-admin → `403`.
4. Frontend `RequireAdmin` + conditional nav prevent non-admins from reaching admin UI;
   the server gate is the real enforcement (defense in depth).

## 7. Security properties

- Passwords: pbkdf2-hmac-sha256, 200k iterations, per-user random salt.
- Constant-time comparison for password hashes and token signatures (`hmac.compare_digest`).
- Tokens signed + expiring; tampering or expiry → rejected.
- Self-registration is hard-wired to `role="user"`; role is never taken from request input.
- `password_hash` never leaves the backend (excluded from all response schemas).
- Secret and admin password supplied via env; default password use emits a warning.
- **Known non-goals (future hardening):** auth-endpoint rate limiting, password reset,
  token revocation/refresh.

## 8. Testing (`backend/tests/test_auth.py`)

- Register → `201`, returned user has `role="user"`, no `password_hash` in payload.
- Duplicate email → `409`.
- Login correct password → `200` + token; wrong password → `401`; unknown email → `401`.
- `GET /me` with token → the user; without token → `401`.
- **Admin gate:** user token → `403` on `GET /api/admin/dashboard`; admin token → `200`;
  no token → `401`.
- Regression: a public endpoint (`GET /api/services`) still returns `200` with no auth.
- `verify_token` rejects an expired/tampered token (unit-level).

## 9. File summary

**New (backend):** `app/auth/__init__.py`, `app/auth/security.py`, `app/auth/service.py`,
`app/auth/deps.py`, `app/api/auth.py`, `scripts/make_admin.py`, `backend/tests/test_auth.py`.
**Edit (backend):** `app/models.py`, `app/enums.py`, `app/config.py`, `app/main.py`
(mount auth router + admin gate + seed), `app/schemas.py` (auth request/response schemas),
`.env.example`.

**New (frontend):** `src/auth/AuthContext.tsx`, `src/pages/LoginPage.tsx`,
`src/pages/RegisterPage.tsx`, `src/components/RequireAdmin.tsx`.
**Edit (frontend):** `src/App.tsx`, `src/components/Layout.tsx`, `src/lib/api.ts`,
`src/styles.css` (auth form styling).

**No new dependencies. No DB migration.**

## 10. Acceptance criteria

1. Anonymous user can still search, use the assistant, and browse services/partners.
2. Anonymous or `role="user"` request to any `/api/admin/*` endpoint → `401`/`403`.
3. `admin@medarchive` (seeded) logs in and reaches the full admin section.
4. A newly registered account is `role="user"` and sees no "Admin" nav; visiting
   `/admin` redirects to `/login`.
5. `python -m scripts.make_admin <email>` promotes an account; after re-login it has
   admin access.
6. `pytest -q` passes including the new `test_auth.py`.
