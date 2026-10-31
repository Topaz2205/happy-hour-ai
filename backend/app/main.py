"""
Happy Hour Cocktails AI — FastAPI Application
"""
import logging
import traceback
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.db.base import Base
from app.db.session import engine
from app.core.config import settings
from app.api import cocktails, events, suppliers, agent, mappings, plan, event_builder, auth
from app.core.auth import get_auth_context
from app.core.security import validate_security_settings

log = logging.getLogger("happyhour")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail at boot, not at first sign-in, if production is missing its secret.
    validate_security_settings()
    # The schema is owned by Alembic (`alembic upgrade head`, run by
    # docker-entrypoint.sh). create_all is opt-in for throwaway local databases
    # only: it can create a table that a later migration then fails to create.
    if settings.AUTO_CREATE_TABLES:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Happy Hour Cocktails AI",
    description="AI-powered cocktail event planning & procurement for HR teams",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Return a JSON body for anything that escapes an endpoint.

    Starlette's default handler for an unhandled exception re-raises, so the
    response never passes back through CORSMiddleware. The browser then sees a
    response with no Access-Control-Allow-Origin header and reports a generic
    network failure ("Load failed" in Safari) instead of the real error — which
    makes genuine backend bugs almost impossible to diagnose from the UI.
    Handling it here keeps the CORS headers and sends something readable.
    """
    log.error("Unhandled error on %s %s\n%s",
              request.method, request.url.path, traceback.format_exc())
    # Exception text can contain SQL, ids or provider messages; only show it
    # outside production.
    detail = ("Something went wrong on our side. Please try again."
              if settings.is_production else f"{type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": detail, "hint": "See the API logs for the full traceback."},
    )


# Public: sign-up / sign-in, and the health check below.
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])

# Everything else requires a signed-in user with a workspace. Event routes
# additionally check ownership per event (app/core/auth.py: require_event_access);
# catalogue writes additionally require a platform admin (see mappings.py).
_signed_in = [Depends(get_auth_context)]
app.include_router(cocktails.router, prefix="/api/cocktails", tags=["Cocktails"], dependencies=_signed_in)
app.include_router(events.router, prefix="/api/events", tags=["Events"], dependencies=_signed_in)
app.include_router(suppliers.router, prefix="/api/suppliers", tags=["Suppliers"], dependencies=_signed_in)
app.include_router(agent.router, prefix="/api/agent", tags=["AI Agent"], dependencies=_signed_in)
app.include_router(mappings.router, prefix="/api/mappings", tags=["Ingredient Mapping"], dependencies=_signed_in)
app.include_router(plan.router, prefix="/api/plan", tags=["Planning"], dependencies=_signed_in)
app.include_router(event_builder.router, prefix="/api/event-builder", tags=["Event Builder"], dependencies=_signed_in)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "happy-hour-ai"}
