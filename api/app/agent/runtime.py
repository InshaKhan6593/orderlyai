"""Assemble and run the ordering agent.

One compiled graph serves every tenant: the business is resolved per run from
``context`` (``business_id`` + ``customer_phone``), so the same graph works in
LangGraph Studio, the WhatsApp worker, and the local CLI. Durable state lives in the
checkpointer, keyed by ``thread_id = business_id:wa_phone``.

Model: Sonnet (default) / Opus (escalation) / Haiku (summariser), via OpenRouter or
Anthropic per settings (see ``_make_model``).
"""
from __future__ import annotations

import asyncio
import os
import uuid
from functools import lru_cache
from typing import Any

from langchain.agents import create_agent  # type: ignore[import-not-found]
from langchain.agents.middleware import (  # type: ignore[import-not-found]
    ModelCallLimitMiddleware,
    SummarizationMiddleware,
)
from langchain.agents.structured_output import ToolStrategy  # type: ignore[import-not-found]
from langchain.chat_models import init_chat_model  # type: ignore[import-not-found]

from app.agent.context import AgentContext
from app.agent.middleware import TenantMiddleware
from app.agent.prompts import ORDERING_SUMMARY_PROMPT
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

        # Turn off reasoning/thinking on OpenRouter. The agent forces a structured AgentReply
        # tool call (tool_choice=required); reasoning models reject that in thinking mode (400).
        # OpenRouter ignores `reasoning` for models that don't support it, so this is safe.
        extra_body = {"reasoning": {"enabled": False}} if settings.agent_disable_reasoning else None
        return ChatOpenAI(
            model=model_id,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            temperature=0,
            default_headers={"X-Title": settings.app_name},
            extra_body=extra_body,
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
            # Loop/cost guard: never let one inbound turn run away with tool calls.
            ModelCallLimitMiddleware(
                thread_limit=None,
                run_limit=settings.agent_max_model_calls,
                exit_behavior="error",
            ),
            # Compaction with an ordering-domain prompt (LangChain's default is a generic
            # coding-agent prompt that drops order-relevant context). Keep recent turns
            # verbatim; summarize the rest into customer/order/state notes.
            SummarizationMiddleware(
                model=summary,
                trigger=("tokens", settings.agent_summary_trigger_tokens),
                keep=("messages", settings.agent_summary_keep_messages),
                summary_prompt=ORDERING_SUMMARY_PROMPT,
                trim_tokens_to_summarize=settings.agent_summary_trim_tokens,
            ),
            TenantMiddleware(TOOLS, main, escalated),
        ],
        checkpointer=checkpointer,
    )


# Process-wide durable agent, created at app startup (see ``start_durable_agent``). Holds the
# psycopg connection pool that backs the Postgres checkpointer so it can be closed on shutdown.
_DURABLE: dict[str, Any] = {"pool": None, "agent": None}


@lru_cache(maxsize=1)
def _memory_agent():
    """Fallback agent on an in-process MemorySaver — for the CLI, LangGraph Studio, and tests
    (no Postgres, state lost on restart). Production uses the durable agent below."""
    from langgraph.checkpoint.memory import MemorySaver  # local import: keeps API import light

    return build_agent(checkpointer=MemorySaver())


def get_whatsapp_agent():
    """The shared agent for the WhatsApp worker, reused across messages.

    Returns the durable Postgres-backed agent once ``start_durable_agent`` has run (the normal
    production path: carts, conversation history, and the handoff flag survive restarts and are
    shared across instances). Falls back to the in-process MemorySaver agent otherwise.
    """
    if _DURABLE["agent"] is not None:
        return _DURABLE["agent"]
    return _memory_agent()


async def start_durable_agent():
    """Build the agent on a pooled Postgres checkpointer and create its tables (idempotent).

    Called once from the app lifespan. A connection *pool* (not a single connection) is
    required so concurrent conversations can read/write checkpoints safely.
    """
    if _DURABLE["agent"] is not None:
        return _DURABLE["agent"]

    # Fail fast on an incompatible loop (Windows ProactorEventLoop) instead of a 30s pool
    # timeout, so the caller can fall back to in-process memory immediately with a clear reason.
    loop = asyncio.get_running_loop()
    if type(loop).__name__ == "ProactorEventLoop":
        raise RuntimeError(
            "Durable Postgres memory needs a SelectorEventLoop, but the running loop is "
            "ProactorEventLoop (Windows default). Start the server via app.main (which sets "
            "WindowsSelectorEventLoopPolicy) or run on Linux."
        )

    from psycopg.rows import dict_row  # local imports: only when durable memory is enabled
    from psycopg_pool import AsyncConnectionPool
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    # The checkpointer uses psycopg (not asyncpg), so strip the SQLAlchemy driver tag.
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    # AsyncPostgresSaver requires autocommit + dict rows + no prepared-statement caching.
    pool = AsyncConnectionPool(
        conninfo=dsn,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open(wait=True, timeout=10)
    saver = AsyncPostgresSaver(pool)
    await saver.setup()  # creates checkpoint tables on first run; no-op thereafter
    _DURABLE["pool"] = pool
    _DURABLE["agent"] = build_agent(checkpointer=saver)
    return _DURABLE["agent"]


async def stop_durable_agent() -> None:
    """Tear down the durable agent's connection pool (called from the app lifespan)."""
    pool = _DURABLE.pop("pool", None)
    _DURABLE["agent"] = None
    if pool is not None:
        await pool.close()


def thread_id_for(business_id: uuid.UUID | str, wa_phone: str) -> str:
    return f"{business_id}:{wa_phone}"


def _message_value(message: Any, key: str) -> Any:
    if isinstance(message, dict):
        return message.get(key)
    return getattr(message, key, None)


def _has_current_structured_response(result: dict[str, Any]) -> bool:
    """ToolStrategy stores AgentReply as a tool message; reject stale prior-turn output."""
    messages = result.get("messages") or []
    if not messages:
        return True

    latest_human = -1
    for index, message in enumerate(messages):
        if _message_value(message, "type") == "human" or _message_value(message, "role") == "user":
            latest_human = index
    if latest_human < 0:
        return True

    for message in messages[latest_human + 1 :]:
        if _message_value(message, "type") != "tool" or _message_value(message, "name") != "AgentReply":
            continue
        content = str(_message_value(message, "content") or "")
        if content.startswith("Returning structured response:"):
            return True
    return False


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
    reply = result.get("structured_response")
    if reply is not None and not _has_current_structured_response(result):
        raise RuntimeError("Agent did not produce a valid structured response for the latest turn.")
    return reply


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
