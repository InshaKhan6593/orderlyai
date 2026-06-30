"""Local chat REPL for the WhatsApp ordering agent — test it WITHOUT WhatsApp.

Runs the real agent (tools, prompt, middleware, structured output) against your real
database and a chosen business. Uses an in-memory checkpointer, so cart/state persist
for the life of this process. (For a nicer UI, use LangGraph Studio: `uv run langgraph dev`.)

Prereqs:
  - .env has LLM_PROVIDER + OPENROUTER_API_KEY (or ANTHROPIC_API_KEY) and the model ids.
  - Postgres is up (docker compose up -d) and your business + menu exist.

Usage (from api/):
  uv run python chat_cli.py                 # lists businesses, then picks the first
  uv run python chat_cli.py --business <id> --phone 923001234567

Commands inside the chat:
  /confirm   simulate the customer tapping the [Confirm] button (sets confirmed=True)
  /quit      exit
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

# The agent replies in a friendly tone that can include emojis; the Windows console
# is cp1252 and would crash on them, so force UTF-8 (replace anything unencodable).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from app.agent import AgentReply
from app.agent.runtime import build_agent, run_turn, thread_id_for
from app.agent.schemas import ButtonsMessage, ImageMessage, ListMessage, TextMessage
from app.core.db import SessionLocal
from app.models.business import Business


def render(reply: AgentReply | None) -> None:
    if reply is None:
        print("  [agent stayed silent — handed off to a human]")
        return
    for m in reply.messages:
        if isinstance(m, TextMessage):
            print(f"  {m.body}")
        elif isinstance(m, ImageMessage):
            cap = f" — {m.caption}" if m.caption else ""
            print(f"  [image: {m.image_url}]{cap}")
        elif isinstance(m, ButtonsMessage):
            print(f"  {m.body}")
            print("  buttons: " + " | ".join(f"[{b.title}]" for b in m.buttons))
        elif isinstance(m, ListMessage):
            print(f"  {m.body}")
            for sec in m.sections:
                print(f"  - {sec.title}:")
                for r in sec.rows:
                    desc = f"  ({r.description})" if r.description else ""
                    print(f"      * {r.title}{desc}")
    if reply.handoff:
        print("  [handoff flagged]")


async def pick_business(business_id: str | None) -> uuid.UUID:
    async with SessionLocal() as s:
        rows = (await s.execute(select(Business.id, Business.name))).all()
    if not rows:
        raise SystemExit("No businesses found. Register one first (web app or API).")
    if business_id:
        return uuid.UUID(business_id)
    print("Businesses:")
    for bid, name in rows:
        print(f"  {bid}  {name}")
    print(f"\nUsing the first: {rows[0][1]} ({rows[0][0]})\n")
    return rows[0][0]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--business", help="business id (defaults to the first one)")
    ap.add_argument("--phone", default="923001234567", help="simulated customer phone")
    args = ap.parse_args()

    business_id = await pick_business(args.business)
    phone = args.phone
    tid = thread_id_for(business_id, phone)
    agent = build_agent(checkpointer=InMemorySaver())

    print("Type a message (or /confirm, /quit). The agent replies below.\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text == "/quit":
            break
        confirmed = False
        if text == "/confirm":
            text, confirmed = "Yes, please confirm and place the order.", True
        try:
            reply = await run_turn(
                agent,
                business_id=business_id,
                customer_phone=phone,
                thread_id=tid,
                text=text,
                confirmed=confirmed,
            )
        except Exception as exc:  # noqa: BLE001 — surface errors in the REPL
            print(f"  [error: {type(exc).__name__}: {exc}]")
            continue
        print("agent>")
        render(reply)
        print()


if __name__ == "__main__":
    asyncio.run(main())
