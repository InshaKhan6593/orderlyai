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
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from langchain.agents import create_agent  # type: ignore[import-not-found]
from langchain.agents.middleware import (  # type: ignore[import-not-found]
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    ModelCallLimitMiddleware,
    SummarizationMiddleware,
)
from langchain.agents.structured_output import ToolStrategy  # type: ignore[import-not-found]
from langchain.chat_models import init_chat_model  # type: ignore[import-not-found]
from pydantic import ValidationError

from app.agent.context import AgentContext
from app.agent.middleware import TenantMiddleware
from app.agent.prompts import ORDERING_SUMMARY_PROMPT
from app.agent.schemas import (
    BTN_CANCEL,
    BTN_CONFIRM,
    BTN_EDIT,
    AgentReply,
    ButtonsMessage,
    ReplyButton,
    TextMessage,
)
from app.agent.state import OrderingState
from app.agent.tools import TOOLS
from app.core.config import settings
from app.schemas.customer import ContactDetails

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
            # Clear OLD tool outputs from what's sent to the model once history grows past
            # the trigger — trims the repeated menu/cart/item dumps that drive latency, while
            # keeping the most recent few verbatim and leaving stored history intact. Runs
            # below the summarizer so this cheap, lossless pass happens before lossy
            # summarization. AgentReply is the structured-output tool — never clear it.
            # Model-agnostic (approximate token counting; works with any chat model).
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=settings.agent_context_edit_trigger_tokens,
                        keep=settings.agent_context_edit_keep,
                        exclude_tools=("AgentReply",),
                    )
                ],
            ),
            TenantMiddleware(TOOLS, main, escalated),
        ],
        checkpointer=checkpointer,
    )


# Process-wide durable agent, created at app startup (see ``start_durable_agent``). Holds the
# psycopg connection pool that backs the Postgres checkpointer so it can be closed on shutdown,
# and the saver itself so retention can delete old threads' checkpoints.
_DURABLE: dict[str, Any] = {"pool": None, "saver": None, "agent": None}


def get_durable_saver():
    """The durable Postgres checkpointer once ``start_durable_agent`` has run, else None
    (in-process memory: CLI / Studio / tests). Used by retention to drop old threads."""
    return _DURABLE.get("saver")


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
    _DURABLE["saver"] = saver
    _DURABLE["agent"] = build_agent(checkpointer=saver)
    return _DURABLE["agent"]


async def stop_durable_agent() -> None:
    """Tear down the durable agent's connection pool (called from the app lifespan)."""
    pool = _DURABLE.pop("pool", None)
    _DURABLE["saver"] = None
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


def _handoff_active(values: dict[str, Any]) -> bool:
    """Whether a handed-off thread should still stay silent.

    Once ``request_human`` fires, the bot goes quiet — but the thread is permanent, so without
    a time-box one "talk to a human" would mute the customer forever. After
    ``whatsapp_handoff_mute_hours`` of silence we resume (0 = never auto-resume). A legacy
    handoff with no timestamp stays muted.
    """
    if values.get("step") != "handed_off":
        return False
    hours = settings.whatsapp_handoff_mute_hours
    if hours <= 0:
        return True
    handoff_at = values.get("handoff_at")
    if not handoff_at:
        return True
    try:
        ts = datetime.fromisoformat(handoff_at)
    except (ValueError, TypeError):
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts < timedelta(hours=hours)


_CONFIRM_CTA = "Tap *Confirm* to place your order, *Edit* to change it, or *Cancel* to discard it."


def _has_confirm_buttons(reply: AgentReply) -> bool:
    return any(
        isinstance(m, ButtonsMessage) and any(b.id == BTN_CONFIRM for b in m.buttons)
        for m in reply.messages
    )


def _ensure_confirm_buttons(reply: AgentReply, summary: str | None) -> AgentReply:
    """Guarantee the [Confirm][Edit][Cancel] reply buttons are sent at checkout.

    place_order sets ``awaiting_confirm`` when it needs the customer to tap Confirm — and the
    tap is the ONLY thing that flips ``confirmed`` (the place_order gate). The model is asked to
    render these buttons but is not reliable at this high-stakes step (it sometimes sends plain
    text like "tap the Confirm button above", leaving the customer no button to tap and the
    order impossible to place). So we render them deterministically here whenever the model
    didn't, keeping any text/image it produced.
    """
    if _has_confirm_buttons(reply):
        return reply
    body = f"{summary}\n\n{_CONFIRM_CTA}" if summary else _CONFIRM_CTA
    buttons = ButtonsMessage(
        kind="buttons",
        body=body,
        buttons=[
            ReplyButton(id=BTN_CONFIRM, title="Confirm"),
            ReplyButton(id=BTN_EDIT, title="Edit"),
            ReplyButton(id=BTN_CANCEL, title="Cancel"),
        ],
    )
    # Drop any non-canonical buttons the model emitted (wrong ids won't flip `confirmed`), keep
    # its text/image, and leave room for ours (AgentReply allows at most 4 messages).
    kept = [m for m in reply.messages if not isinstance(m, ButtonsMessage)]
    return AgentReply(messages=kept[:3] + [buttons], handoff=reply.handoff)


def _text_reply(body: str) -> AgentReply:
    """One deterministic, code-authored text message, sent verbatim and ALONE.

    Used for the high-stakes / structured moments that must not depend on the LLM's phrasing or
    numbers: the order-placed confirmation (real order number + server total — never doubled by a
    model-written summary) and the contact questions/re-asks below. Mirrors the deterministic
    confirm buttons above.
    """
    return AgentReply(messages=[TextMessage(kind="text", body=body)], handoff=False)


# --- Deterministic contact collection -------------------------------------------------------- #
# The model never sets contact values. When a required field is missing, place_order sets
# ``pending_contact_field``; run_turn asks the question below, then validates + stores the typed
# reply in code (server-side, via ContactDetails) before the next model turn.
_CONTACT_STATE_KEY = {
    "name": "customer_name",
    "email": "customer_email",
    "alternate_phone": "customer_alt_phone",
}
_CONTACT_QUESTIONS = {
    "name": "Almost done! What name should we put on the order?",
    "email": "What email should we use for the order?",
    "alternate_phone": "What's a good alternate phone number for the order?",
}
_CONTACT_RETRY = {
    "name": "Sorry, I didn't catch that - what name should we put on the order?",
    "email": "That doesn't look like a valid email - could you type it again?",
    "alternate_phone": "That doesn't look like a valid phone number - please send it again.",
}
# If the customer backs out mid-collection, don't store the word as their name/email/phone.
_CONTACT_ABORT_WORDS = {"cancel", "stop", "quit", "no", "nevermind", "never mind", "back"}


def _capture_contact(field: str, text: str) -> tuple[str | None, str | None]:
    """Validate a free-text reply as one contact field. Returns ``(value, error_message)``.

    Deterministic and server-side (``ContactDetails`` — EmailStr / phone-digit checks); the LLM
    is not involved in extracting or storing the value. A blank or invalid entry returns a
    re-ask message instead of a value.
    """
    raw = " ".join((text or "").split())
    if not raw:
        return None, _CONTACT_QUESTIONS[field]
    try:
        details = ContactDetails(**{field: raw})
    except ValidationError:
        return None, _CONTACT_RETRY[field]
    value = getattr(details, field)
    if value is None:
        return None, _CONTACT_QUESTIONS[field]
    return str(value), None


async def run_turn(
    agent: Any,
    *,
    business_id: uuid.UUID | str,
    customer_phone: str,
    thread_id: str,
    text: str,
    confirmed: bool = False,
    reply_id: str | None = None,
) -> AgentReply | None:
    """Run one inbound message. Returns the structured reply, or ``None`` when the agent
    intentionally stays silent (handed off to a human and still inside the mute window).

    ``confirmed`` is set by the caller from a deterministic confirm-button tap — never
    inferred by the model. It is the gate ``place_order`` checks. ``reply_id`` is the tapped
    button/list id (if any), so a tap is never mistaken for a typed contact-detail answer.
    """
    config = {"configurable": {"thread_id": thread_id}}
    resume_overrides: dict[str, Any] = {}
    try:
        snapshot = await agent.aget_state(config)
    except Exception:  # noqa: BLE001 — no prior state is fine
        snapshot = None
    values = snapshot.values if snapshot is not None else {}
    if values.get("step") == "handed_off":
        if _handoff_active(values):
            return None  # still handed off → stay silent, don't even call the model
        # Mute window elapsed → resume the bot, clearing the handoff flags for this turn.
        resume_overrides = {"step": "browsing", "handoff_reason": None, "handoff_at": None}

    # Deterministic contact capture: if we're collecting a field and the customer typed a plain
    # reply (not a button tap / confirm), validate + store it in CODE here — the model never sets
    # contact values. An abort word drops the prompt and lets the agent handle the change of mind.
    capture_overrides: dict[str, Any] = {}
    pending = values.get("pending_contact_field")
    if pending and not confirmed and not reply_id:
        if " ".join((text or "").split()).lower() in _CONTACT_ABORT_WORDS:
            capture_overrides = {"pending_contact_field": None}
        else:
            value, error = _capture_contact(pending, text)
            if error:
                return _text_reply(error)  # re-ask; pending stays set in the checkpoint
            capture_overrides = {_CONTACT_STATE_KEY[pending]: value, "pending_contact_field": None}
            text = "Please go ahead and place my order."  # value already saved in code above

    result = await agent.ainvoke(
        {
            "messages": [{"role": "user", "content": text}],
            "confirmed": confirmed,
            # Reset each turn so a stale flag can't linger; place_order re-sets these within the
            # turn when it needs a Confirm tap (then _ensure_confirm_buttons renders the buttons)
            # or when it finalizes an order (then we send order_placed_summary below).
            "awaiting_confirm": False,
            "confirm_summary": None,
            "order_placed_summary": None,
            **resume_overrides,
            **capture_overrides,  # deterministically-captured contact value + cleared pending flag
        },
        config,
        context=AgentContext(business_id=str(business_id), customer_phone=customer_phone),
    )
    # An order was just committed → send the deterministic confirmation verbatim and ALONE,
    # regardless of what the model produced. This guarantees the customer is told (the order
    # exists in the DB), with the correct order number/total, and never a duplicate summary.
    placed_summary = result.get("order_placed_summary")
    if placed_summary:
        return _text_reply(placed_summary)
    # A required contact field is missing → ask for it with a fixed, code-rendered question (the
    # next typed reply is captured deterministically above, not by the model).
    pending_now = result.get("pending_contact_field")
    if pending_now:
        return _text_reply(_CONTACT_QUESTIONS.get(pending_now, _CONTACT_QUESTIONS["name"]))
    reply = result.get("structured_response")
    if reply is not None and not _has_current_structured_response(result):
        raise RuntimeError("Agent did not produce a valid structured response for the latest turn.")
    if reply is not None and result.get("awaiting_confirm"):
        reply = _ensure_confirm_buttons(reply, result.get("confirm_summary"))
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
