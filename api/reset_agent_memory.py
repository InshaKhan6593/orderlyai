"""Reset the WhatsApp agent's conversation memory for ALL businesses (fresh-start utility).

Deletes ONLY agent conversation data:
  - LangGraph checkpoint tables  -> the durable chat log + per-conversation cart/flow state
  - whatsapp_inbox               -> the durable inbound queue + message_id dedup

Does NOT touch businesses, menu, products, orders, customers, agent configs, or WhatsApp
connections. checkpoint_migrations (the saver's schema-version marker) is kept on purpose.

Usage (from api/):
    uv run python reset_agent_memory.py          # DRY RUN: show what would be deleted
    uv run python reset_agent_memory.py --yes     # actually delete

Stop the agent worker first (so it isn't mid-drain). This takes an exclusive lock and fails
fast (5s) rather than hanging if the worker is holding the tables.
"""
from __future__ import annotations

import sys

import psycopg

from app.core.config import settings

# Agent conversation/memory tables only (truncated together so any cross-refs are fine).
TARGETS = ["checkpoints", "checkpoint_blobs", "checkpoint_writes", "whatsapp_inbox"]


def main() -> int:
    execute = "--yes" in sys.argv or "-y" in sys.argv
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    db_name = dsn.rsplit("/", 1)[-1].split("?")[0]  # name only; never print credentials
    print(f"Target database: {db_name}")
    print(f"Mode: {'DELETE' if execute else 'dry run (pass --yes to delete)'}\n")

    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SET lock_timeout = '5s'")
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        existing = {r[0] for r in cur.fetchall()}
        targets = [t for t in TARGETS if t in existing]
        if not targets:
            print("Nothing to clear: no checkpoint/inbox tables found (in-memory mode?).")
            return 0

        total = 0
        for t in targets:
            cur.execute(f"SELECT count(*) FROM {t}")
            n = cur.fetchone()[0]
            total += n
            print(f"  {t}: {n} row(s)")

        if not execute:
            print(f"\nWould delete {total} row(s) across {len(targets)} table(s). "
                  "Re-run with --yes to proceed.")
            return 0

        try:
            cur.execute("TRUNCATE TABLE " + ", ".join(targets) + " RESTART IDENTITY")
        except psycopg.errors.LockNotAvailable:
            print("\nCould not lock the tables - the agent worker is probably running. "
                  "Stop it, then re-run.")
            return 1

    print(f"\nDeleted {total} row(s). Agent conversation memory reset for ALL businesses.")
    print("Businesses, menu, orders, customers, and WhatsApp connections are untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
