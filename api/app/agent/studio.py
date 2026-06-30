"""LangGraph Studio / Platform entrypoint.

`langgraph dev` (and the Studio UI) load this module's ``graph``. It's the
tenant-agnostic agent compiled WITHOUT a checkpointer — the dev server / platform
supplies persistence. Set the per-run tenant in Studio's context panel:

    business_id     = <a UUID from your DB>
    customer_phone  = <any phone, e.g. 923001234567>

Requires the model env (LLM_PROVIDER + OPENROUTER_API_KEY / ANTHROPIC_API_KEY) in .env.
"""
from __future__ import annotations

from app.agent.runtime import build_agent

graph = build_agent(checkpointer=None)
