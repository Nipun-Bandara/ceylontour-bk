"""Create the authority account from the environment.

    python -m api.seed_user

Reads AUTHORITY_EMAIL and AUTHORITY_PASSWORD. The password is hashed with
argon2 before it goes anywhere near the database and is never written to the
log, so the only place the plain text exists is the .env file, which is
gitignored.

Re-running updates the existing account's password rather than creating a
second one.
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from api.config import settings
from api.database import SessionLocal
from api.models import User
from api.services.security import AUTHORITY_ROLE, hash_password

# Anything shorter is not worth the argon2 call.
MIN_PASSWORD_LENGTH = 12


def main() -> int:
    email = settings.authority_email.strip()
    password = settings.authority_password

    if not password:
        print(
            "AUTHORITY_PASSWORD is not set. Set it in .env and run again.\n"
            "Nothing was written: a blank password must never become an "
            "account.",
            file=sys.stderr,
        )
        return 1

    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"AUTHORITY_PASSWORD is {len(password)} characters; at least "
            f"{MIN_PASSWORD_LENGTH} are required.",
            file=sys.stderr,
        )
        return 1

    if not email:
        print("AUTHORITY_EMAIL is not set.", file=sys.stderr)
        return 1

    session = SessionLocal()
    try:
        user = session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if user is None:
            session.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    role=AUTHORITY_ROLE,
                )
            )
            action = "created"
        else:
            user.password_hash = hash_password(password)
            user.role = AUTHORITY_ROLE
            action = "updated"

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # The password itself is deliberately not printed.
    print(f"Authority account {action}: {email} (role: {AUTHORITY_ROLE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
