# Rolling out accounts & private workspaces

This release adds sign-in, private per-user workspaces and a database-backed
AI quota. The database migration (`a1f3c9d2e7b4`) is **additive only**: it creates
`users`, `company_memberships` and `usage_counters`, adds two columns and one
index. It drops, renames or rewrites nothing.

After it runs, events created before this release belong to no workspace and are
hidden from everyone until you assign them (step 5).

## 1. Back up the database

In Neon, create a branch (or a point-in-time restore point) of the production
database before deploying.

## 2. Set API environment variables (Render → happy-hour-ai → Environment)

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `AUTH_SECRET_KEY` | a new random value: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `AI_DAILY_REQUEST_LIMIT` | `10` |
| `AI_GLOBAL_DAILY_REQUEST_LIMIT` | `300` (your daily ceiling across all users) |
| `CORS_ORIGINS` | `["https://happy-hour-ai-beta.vercel.app"]` |

With `ENVIRONMENT=production` the API refuses to start without `AUTH_SECRET_KEY`.
The old `AI_DEMO_*` variables are no longer used and can be removed.

Nothing changes on Vercel: `NEXT_PUBLIC_API_URL` stays as it is.

## 3. Deploy the API, then the frontend

If Render runs the Docker image, `docker-entrypoint.sh` runs `alembic upgrade head`
automatically on boot. If the service uses a native start command instead, run
the migration once with the production `DATABASE_URL`:

    cd backend && alembic upgrade head

Startup no longer calls `create_all` (it is now opt-in with
`AUTO_CREATE_TABLES=true`, for throwaway local databases only), so the schema
comes from Alembic alone.

The scripts below use `DATABASE_URL`, like the API does. Run them in the Render
service's **Shell** tab, where it is already set, or locally with the production
value exported for that one command only.

## 4. Create your own account

Open the app and sign up. You get a personal workspace automatically.

Make yourself the catalogue admin (mappings and prices are shared by everyone):

    cd backend && python scripts/set_admin.py --email you@example.com

## 5. Reclaim events created before this release (optional)

Dry run first. It lists what would move and changes nothing:

    cd backend && python scripts/assign_legacy_events.py --email you@example.com

Then apply:

    cd backend && python scripts/assign_legacy_events.py --email you@example.com --apply

Events you don't reclaim stay hidden. Deleting them is a separate, manual
decision.

## 6. Check

- Two different accounts each see only their own events.
- `GET /api/events` without signing in returns `401`.
- The sidebar shows "AI today: N of 10 left".

## Rollback

`alembic downgrade 082021ca8d7f` removes only what this release added. Redeploy
the previous API and frontend versions with it.
