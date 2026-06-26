"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# psycopg's async mode (the durable Postgres checkpointer) can't run on Windows' default
# ProactorEventLoop. Select a compatible loop on Windows BEFORE the server loop is created.
# No effect on Linux/macOS (their default loop already works). asyncpg works on either.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging

configure_logging(settings.debug)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the WhatsApp agent worker alongside the app.

    Gated by ``run_agent_worker`` (off in tests). When on, builds the durable Postgres-backed
    agent and runs the inbox sweeper (crash recovery + send retries). The webhook's per-request
    drain works regardless; this just owns the long-lived agent and the background sweep.
    """
    sweeper: asyncio.Task | None = None
    if settings.run_agent_worker:
        from app.agent.runtime import start_durable_agent
        from app.services.whatsapp_worker import sweeper_loop

        if settings.whatsapp_durable_memory:
            try:
                await start_durable_agent()
                logger.info("Durable WhatsApp agent ready (Postgres checkpointer).")
            except Exception:  # noqa: BLE001 — don't let a checkpointer hiccup block startup
                logger.exception("Failed to start durable agent; using in-process memory.")
        sweeper = asyncio.create_task(sweeper_loop())
    try:
        yield
    finally:
        if sweeper is not None:
            sweeper.cancel()
            try:
                await sweeper
            except asyncio.CancelledError:
                pass
        from app.agent.runtime import stop_durable_agent

        await stop_durable_agent()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

upload_dir = Path(settings.upload_dir).resolve()
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.env}


app.include_router(api_router, prefix=settings.api_v1_prefix)
