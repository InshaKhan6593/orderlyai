"""Reset all customer-facing INTERACTION data for ALL businesses (fresh-start utility).

DRY RUN by default (pass --yes to actually delete). One scope: wipe everything a
customer interaction creates, keeping only the business's own setup.

DELETED (every trace of customer interaction):
  - LangGraph checkpoint tables   (the durable chat log + cart/flow state = "messages")
  - whatsapp_inbox                (inbound queue + message_id dedup + delivery receipts)
  - orders, order_items, order_status_history
  - customers                     (names, saved addresses, order counts)
  - and resets each business's order counter (businesses.next_order_no) to 1

NEVER touched (your business setup is safe): businesses (profile + status), users,
memberships, the menu (categories, products, modifier groups/options, assignments,
per-dish prices), business_hours, delivery_zones, agent_configs, and whatsapp_connections.

Usage (from api/):
    uv run python reset_agent_memory.py          # DRY RUN: show what would be deleted
    uv run python reset_agent_memory.py --yes    # actually delete

Stop the API and the agent worker first (so nothing is mid-write). This takes exclusive locks
and fails fast (5s) rather than hanging if the app is holding the tables.
"""
from __future__ import annotations

import sys

import psycopg

from app.core.config import settings

# Every table that holds customer-interaction data. All FK-referencing tables are included
# (order_items/order_status_history -> orders -> customers), so a single TRUNCATE is valid.
# The LangGraph checkpoint tables hold the durable chat log + cart/flow state ("messages").
INTERACTION_TABLES = [
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "whatsapp_inbox",
    "order_status_history",
    "order_items",
    "orders",
    "customers",
]


def main() -> int:
    execute = "--yes" in sys.argv or "-y" in sys.argv
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    db_name = dsn.rsplit("/", 1)[-1].split("?")[0]  # name only; never print credentials

    print(f"Target database: {db_name}")
    print("Scope: ALL interaction data (orders + customers + messages)")
    print(f"Mode: {'DELETE' if execute else 'dry run (pass --yes to delete)'}")
    print("Keeping: businesses, users, menu, hours, delivery zones, agent config, WhatsApp connections.\n")

    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SET lock_timeout = '5s'")
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        existing = {r[0] for r in cur.fetchall()}
        targets = [t for t in INTERACTION_TABLES if t in existing]
        if not targets:
            print("Nothing to clear: none of the target tables exist (in-memory mode?).")
            return 0

        total = 0
        for t in targets:
            cur.execute(f"SELECT count(*) FROM {t}")
            n = cur.fetchone()[0]
            total += n
            print(f"  {t}: {n} row(s)")
        print("  businesses.next_order_no -> will reset to 1")

        if not execute:
            print(f"\nWould delete {total} row(s) across {len(targets)} table(s). "
                  "Re-run with --yes to proceed.")
            return 0

        try:
            cur.execute("TRUNCATE TABLE " + ", ".join(targets) + " RESTART IDENTITY")
            if "businesses" in existing:
                # Reset only the order counter; every other business column is left untouched.
                cur.execute("UPDATE businesses SET next_order_no = 1")
        except psycopg.errors.LockNotAvailable:
            print("\nCould not lock the tables - the API or agent worker is probably running. "
                  "Stop it, then re-run.")
            return 1

    print(f"\nDeleted {total} row(s).")
    print("Orders, customers, and conversation memory reset for ALL businesses; "
          "order counters reset to 1.")
    print("Businesses, users, menu, hours, delivery zones, agent config, and WhatsApp connections are untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
