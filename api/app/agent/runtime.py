"""Assemble and run the ordering agent.

One compiled graph serves every tenant: the business is resolved per run from
``context`` (``business_id`` + ``customer_phone``), so the same graph works in
LangGraph Studio, the WhatsApp worker, and the local CLI. Durable state lives in the
checkpointer, keyed by ``thread_id = business_id:wa_phone``.

Model: Sonnet (default) / Opus (escalation) / Haiku (summariser), via OpenRouter or
Anthropic per settings (see ``_make_model``).
"""
from __future__ import annotations

import os
import uuid
from functools import lru_cache
from typing import Any

from langchain.agents import create_agent  # type: ignore[import-not-found]
from langchain.agents.middleware import SummarizationMiddleware  # type: ignore[import-not-found]
from langchain.agents.structured_output import ToolStrategy  # type: ignore[import-not-found]
from langchain.chat_models import init_chat_model  # type: ignore[import-not-found]

from app.agent.context import AgentContext
from app.agent.middleware import TenantMiddleware
from app.agent.schemas import AgentReply
from app.agent.state import OrderingState
from app.agent.tools import TOOLS
from app.core.config import settings

# re-export so callers can `from app.agent.runtime import load_business_for_agent`
from app.agent.catalog import load_business_for_agent  # noqa: F401


def configure_tracing() -> None:
    """Export LangSmith settings into the process env so LangChain auto-traces.

    pydantic loads ``.env`` into Settings, not ``os.environ`` — but LangChain reads
    tracing config from env vars. ``langgraph dev`` injects ``.env`` itself; this makes
    the CLI and worker trace too. Real env vars already set take precedence.
    """
    if not settings.langsmith_tracing:
        return
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)


def _make_model(model_id: str) -> Any:
    """Build a chat model for the configured provider.

    - ``openrouter``: OpenAI-compatible client at OpenRouter (one key, many models);
      ``model_id`` is the OpenRouter slug, e.g. "anthropic/claude-sonnet-4.6".
    - ``anthropic``: native client; ``model_id`` is "anthropic:<model>".
    """
    if settings.llm_provider == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            temperature=0,
            default_headers={"X-Title": settings.app_name},
        )
    return init_chat_model(model_id, temperature=0)


@lru_cache
def _models() -> tuple[Any, Any, Any]:
    """(main, escalated, summary) chat models. Cached; created lazily (no network)."""
    return (
        _make_model(settings.agent_model),
        _make_model(settings.agent_escalation_model),
        _make_model(settings.agent_summary_model),
    )


def build_agent(*, checkpointer: Any = None):
    """Compile the tenant-agnostic agent graph. Pass a checkpointer for the worker/CLI;
    pass None for LangGraph Studio / Platform (the runtime supplies persistence)."""
    configure_tracing()
    main, escalated, summary = _models()
    return create_agent(
        model=main,  # TenantMiddleware overrides per run
        tools=TOOLS,
        state_schema=OrderingState,
        context_schema=AgentContext,
        response_format=ToolStrategy(AgentReply),
        middleware=[
            SummarizationMiddleware(
                model=summary,
                trigger=("tokens", 6000),
                keep=("messages", 16),
            ),
            TenantMiddleware(TOOLS, main, escalated),
        ],
        checkpointer=checkpointer,
    )


def thread_id_for(business_id: uuid.UUID | str, wa_phone: str) -> str:
    return f"{business_id}:{wa_phone}"


async def run_turn(
    agent: Any,
    *,
    business_id: uuid.UUID | str,
    customer_phone: str,
    thread_id: str,
    text: str,
    confirmed: bool = False,
) -> AgentReply | None:
    """Run one inbound message. Returns the structured reply, or ``None`` when the agent
    intentionally stays silent (already handed off to a human).

    ``confirmed`` is set by the caller from a deterministic confirm-button tap — never
    inferred by the model. It is the gate ``place_order`` checks.
    """
    config = {"configurable": {"thread_id": thread_id}}
    # Once handed off, stop auto-replying (don't even call the model).
    try:
        snapshot = await agent.aget_state(config)
        if snapshot and snapshot.values.get("step") == "handed_off":
            return None
    except Exception:  # noqa: BLE001 — no prior state is fine
        pass

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": text}], "confirmed": confirmed},
        config,
        context=AgentContext(business_id=str(business_id), customer_phone=customer_phone),
    )
    return result.get("structured_response")


def get_checkpointer():
    """Async context manager for the Postgres checkpointer (worker owns its lifecycle).

        from app.agent.runtime import get_checkpointer, build_agent, run_turn
        async with get_checkpointer() as cp:
            await cp.setup()                  # once, creates checkpoint tables
            agent = build_agent(checkpointer=cp)
            reply = await run_turn(agent, business_id=..., customer_phone=..., ...)
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # local import

    # The checkpointer uses psycopg (not asyncpg), so strip the SQLAlchemy driver tag.
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return AsyncPostgresSaver.from_conn_string(dsn)
