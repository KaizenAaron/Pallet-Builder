"""Command-line helpers.

    python cli.py create-platform-admin <email> <password> [name]
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from app import models  # noqa: F401
from app import rls  # noqa: F401
from app.db import Base, engine, system_session
from app.models import User
from app.security import check_password_strength, hash_password
from app.services.accounts import find_user, normalize_email


def create_platform_admin(email: str, password: str, name: str = "") -> None:
    check_password_strength(password)
    Base.metadata.create_all(bind=engine)
    with system_session() as db:
        user = find_user(db, email)
        if user is None:
            user = User(email=normalize_email(email), name=name or email.split("@")[0])
            db.add(user)
        user.password_hash = hash_password(password)
        user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
        user.is_platform_admin = True
        if name:
            user.name = name
        db.commit()
        print(f"Platform admin ready: {user.email}")


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "create-platform-admin":
        create_platform_admin(argv[1], argv[2], argv[3] if len(argv) > 3 else "")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
