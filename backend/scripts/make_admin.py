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
