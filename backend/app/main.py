"""
Happy Hour AI — FastAPI Application
"""
import logging
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.db.base import Base
from app.db.session import engine
from app.core.config import settings
from app.api import cocktails, events, suppliers, agent, mappings, plan, event_builder

log = logging.getLogger("happyhour")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Happy Hour AI",
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
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{type(exc).__name__}: {exc}",
            "hint": "See the API terminal for the full traceback.",
        },
    )


app.include_router(cocktails.router, prefix="/api/cocktails", tags=["Cocktails"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(suppliers.router, prefix="/api/suppliers", tags=["Suppliers"])
app.include_router(agent.router, prefix="/api/agent", tags=["AI Agent"])
app.include_router(mappings.router, prefix="/api/mappings", tags=["Ingredient Mapping"])
app.include_router(plan.router, prefix="/api/plan", tags=["Planning"])
app.include_router(event_builder.router, prefix="/api/event-builder", tags=["Event Builder"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "happy-hour-ai"}
