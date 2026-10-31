"""
Grant or revoke platform-admin rights (editing the shared catalogue:
ingredient mappings and prices). Admin is never grantable through the API.

    python scripts/set_admin.py --email you@example.com          # grant
    python scripts/set_admin.py --email you@example.com --revoke
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402


async def main(email: str, revoke: bool) -> int:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(
            select(User).where(User.email == email.strip().lower())
        )).scalar_one_or_none()
        if user is None:
            print(f"No user with email {email!r}.")
            return 1
        user.is_admin = not revoke
        await db.commit()
        print(f"{user.email}: is_admin = {user.is_admin}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--revoke", action="store_true")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.email, a.revoke)))
