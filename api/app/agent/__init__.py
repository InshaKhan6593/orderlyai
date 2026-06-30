"""OrderlyAI WhatsApp ordering agent (LangChain v1 + LangGraph + Claude).

See docs/agent/ARCHITECTURE.md for the full design. The agent is one tenant-agnostic
compiled graph; the tenant is resolved per run from `AgentContext`. Public entrypoints:

    from app.agent import build_agent, run_turn, thread_id_for, AgentContext, AgentReply
    from app.agent.runtime import get_checkpointer

Imports are lazy so the LangChain-free modules (schemas, prompts, whatsapp_render,
context) stay importable without the agent runtime dependencies installed.
"""
from __future__ import annotations

from app.agent.context import AgentContext  # LangChain-free
from app.agent.schemas import AgentReply  # LangChain-free

__all__ = [
    "AgentContext",
    "AgentReply",
    "build_agent",
    "run_turn",
    "thread_id_for",
    "load_business_for_agent",
]

_RUNTIME = {"build_agent", "run_turn", "thread_id_for", "load_business_for_agent"}


def __getattr__(name: str):
    if name in _RUNTIME:
        from app.agent import runtime

        return getattr(runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
