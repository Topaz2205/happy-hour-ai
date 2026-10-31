"""
Assign events created before workspaces existed to one user's workspace.

After the a1f3c9d2e7b4 migration, an event is visible only inside the workspace
in events.company_id. Legacy events point at no company, or at a free-text
"company" row nobody is a member of, so nobody can see them. This script moves
them into a chosen user's default workspace.

DRY RUN BY DEFAULT. Nothing is written unless --apply is given.

    # list what would move
    python scripts/assign_legacy_events.py --email you@example.com

    # move every unowned legacy event into that user's workspace
    python scripts/assign_legacy_events.py --email you@example.com --apply

    # or only specific events
    python scripts/assign_legacy_events.py --email you@example.com \\
        --event-id 2222... --event-id 3333... --apply

The user must have signed up (and therefore have a workspace) first.
Uses DATABASE_URL like the API does.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import exists, or_, select  # noqa: E402

from app.core.auth import ensure_personal_workspace  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models import CompanyMembership, Event, User  # noqa: E402


async def main(email: str, event_ids: list[str], apply: bool) -> int:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(
            select(User).where(User.email == email.strip().lower())
        )).scalar_one_or_none()
        if user is None:
            print(f"No user with email {email!r}. Ask them to sign up first.")
            return 1
        membership = await ensure_personal_workspace(db, user)
        target = membership.company_id

        has_members = exists().where(CompanyMembership.company_id == Event.company_id)
        q = select(Event).where(or_(Event.company_id.is_(None), ~has_members))
        if event_ids:
            q = select(Event).where(Event.id.in_([uuid.UUID(e) for e in event_ids]))

        events = (await db.execute(q.order_by(Event.created_at))).scalars().all()
        if not events:
            print("Nothing to assign.")
            return 0

        for e in events:
            print(f"  {e.id}  {e.name!r:40}  company_id={e.company_id}")
        print(f"{len(events)} event(s) → workspace {target}")

        if not apply:
            print("Dry run — re-run with --apply to write.")
            await db.rollback()
            return 0

        for e in events:
            e.company_id = target
        await db.commit()
        print("Done.")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True)
    ap.add_argument("--event-id", action="append", default=[])
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.email, a.event_id, a.apply)))
