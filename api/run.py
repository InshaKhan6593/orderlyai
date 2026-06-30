"""Dev/prod server launcher.

Use this instead of the bare ``uvicorn`` CLI on Windows: the durable Postgres checkpointer
runs on psycopg's async mode, which cannot use Windows' default ProactorEventLoop.

Two wrinkles make this non-trivial on Windows:
  1. uvicorn builds its event loop before importing the app, so setting the policy inside
     ``app.main`` is too late.
  2. uvicorn's own loop setup re-installs a Proactor loop even if we set the policy first.

So for the normal (no-reload) path we build a SelectorEventLoop ourselves and run uvicorn's
server inside it (``loop="none"`` tells uvicorn not to touch the loop). On Linux/macOS this is
all a no-op — the default loop already supports psycopg, so plain ``uvicorn app.main:app``
works there too. ``--reload`` on Windows runs in a uvicorn-managed subprocess (Proactor loop),
so durable memory falls back to in-process memory while reloading — use ``--no-reload`` to
exercise durable memory locally.

    uv run python run.py --no-reload   # durable memory (recommended for testing the agent)
    uv run python run.py               # reload on; durable memory falls back on Windows
"""
from __future__ import annotations

import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    if "--no-reload" in sys.argv:
        # Run uvicorn inside OUR selector loop so psycopg async (durable memory) works.
        config = uvicorn.Config("app.main:app", host=host, port=port, loop="none")
        asyncio.run(uvicorn.Server(config).serve())
    else:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=True,
            reload_dirs=["app"],  # never watch .venv (reload-loops on .pyc writes)
        )
