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
    BTN_FUL_DELIVERY,
    BTN_FUL_PICKUP,
    BTN_UPDATE_CONFIRM,
    BTN_UPDATE_KEEP,
    ROW_ZONE_PREFIX,
    AgentReply,
    ButtonsMessage,
    ImageMessage,
    ListMessage,
    ListRow,
    ListSection,
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

        extra_body: dict[str, Any] = {}
        # Turn off reasoning/thinking on OpenRouter. The agent forces a structured AgentReply
        # tool call (tool_choice=required); reasoning models reject that in thinking mode (400).
        # OpenRouter ignores `reasoning` for models that don't support it, so this is safe.
        if settings.agent_disable_reasoning:
            extra_body["reasoning"] = {"enabled": False}
        # Pin upstream providers (see settings.openrouter_provider_order). A model slug is
        # load-balanced across many providers; without this a turn can land on one that blips
        # with an opaque 400 or won't honor the forced tool call. Empty list = default routing.
        provider_order = [p.strip() for p in settings.openrouter_provider_order.split(",") if p.strip()]
        if provider_order:
            extra_body["provider"] = {
                "order": provider_order,
                "allow_fallbacks": settings.openrouter_provider_allow_fallbacks,
            }
        return ChatOpenAI(
            model=model_id,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            temperature=0,
            default_headers={"X-Title": settings.app_name},
            extra_body=extra_body or None,
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
    # When we render the deterministic, server-priced summary in the button body, IT is the single
    # source of truth — drop the model's own text (it usually re-summarizes the order too, which
    # showed the customer the summary TWICE). Keep an image if the model included one. With no
    # summary, keep the model's text/image and just add the buttons.
    if summary:
        kept = [m for m in reply.messages if isinstance(m, ImageMessage)]
    else:
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
# The model never sets contact values. When the required name is missing, place_order sets
# ``pending_checkout_field="name"``; run_turn asks the question below, then validates + stores the
# typed reply in code (server-side, via ContactDetails) before the next model turn. Email and
# alternate phone are OPTIONAL — they are only ever changed through the update_detail flow.
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


# --- Deterministic checkout slots (fulfillment + address) + detail-update confirmation -------- #
# place_order sets ``pending_checkout_field`` for a missing required slot; the model never
# collects these. run_turn asks deterministically and captures the tap/typed reply in code.
_RETRIGGER = "Please go ahead and place my order."  # synthetic text that re-enters place_order
_CHECKOUT_QUESTIONS = {
    # The delivery AREA is picked first (zone slot); this is the street address for the driver.
    "address": (
        "What's the full delivery address - house/flat, street, and any landmark? "
        "(Or reply 'pickup' to collect it instead.)"
    ),
    "name": _CONTACT_QUESTIONS["name"],
}
_ZONE_TEXT_FALLBACK = "What area should we deliver to?"
# Maps an update_detail field to the state key it writes (the model proposes the value via
# update_detail; the customer's Update tap is what actually applies + persists it).
_UPDATE_STATE_KEY = {
    "name": "customer_name",
    "email": "customer_email",
    "alternate_phone": "customer_alt_phone",
    "address": "address",
}
_UPDATE_FIELD_LABEL = {
    "name": "name",
    "email": "email",
    "alternate_phone": "alternate phone",
    "address": "delivery address",
    "area": "delivery area",
}


def _render_fulfillment_question() -> AgentReply:
    """Deterministic Delivery/Pickup choice (asked when the business offers both)."""
    return AgentReply(
        messages=[
            ButtonsMessage(
                kind="buttons",
                body="Will this be delivery or pickup?",
                buttons=[
                    ReplyButton(id=BTN_FUL_DELIVERY, title="Delivery"),
                    ReplyButton(id=BTN_FUL_PICKUP, title="Pickup"),
                ],
            )
        ]
    )


def _render_zone_list(zone_choices: list[dict[str, Any]], body: str | None) -> AgentReply:
    """Deterministic 'pick your delivery area' list — each row is one active zone; a tap selects it
    exactly (no address-text guessing) and confirms serviceability. Used when the zones fit a
    WhatsApp list (<= 10 rows); with more zones than that, run_turn asks for the area as text."""
    rows = [
        ListRow(id=c["id"], title=c["title"], description=c.get("description"))
        for c in zone_choices
    ]
    return AgentReply(
        messages=[
            ListMessage(
                kind="list",
                body=body or _ZONE_TEXT_FALLBACK,
                button="Select area",
                sections=[ListSection(title="Delivery areas", rows=rows)],
            )
        ]
    )


def _describe_update(upd: dict[str, Any], current: dict[str, Any]) -> str:
    """One 'email to *x@y.com* (currently old)' clause for the confirm prompt."""
    field = upd["field"]
    label = _UPDATE_FIELD_LABEL.get(field, field)
    if field == "area":  # the saved area is a zone id, not a readable name — skip the "currently"
        return f"{label} to *{upd['value']}*"
    old = current.get(_UPDATE_STATE_KEY[field])
    was = f" (currently {old})" if old else ""
    return f"{label} to *{upd['value']}*{was}"


def _render_update_confirm(updates: list[dict[str, Any]], current: dict[str, Any]) -> AgentReply:
    """Deterministic 'update your saved <detail(s)>?' confirmation — the customer's tap applies
    them. Handles several pending changes at once (one combined prompt, one Update tap), so a
    request like 'change my email and alternate number' is confirmed together, not piecemeal."""
    clauses = [_describe_update(u, current) for u in updates]
    if len(clauses) == 1:
        body = f"Update your {clauses[0]}?"
    elif len(clauses) == 2:
        body = f"Update your {clauses[0]} and {clauses[1]}?"
    else:
        body = "Update your " + ", ".join(clauses[:-1]) + f", and {clauses[-1]}?"
    return AgentReply(
        messages=[
            ButtonsMessage(
                kind="buttons",
                body=body,
                buttons=[
                    ReplyButton(id=BTN_UPDATE_CONFIRM, title="Update"),
                    ReplyButton(id=BTN_UPDATE_KEEP, title="Keep current"),
                ],
            )
        ]
    )


def _capture_checkout(
    values: dict[str, Any], text: str, reply_id: str | None, confirmed: bool
) -> tuple[dict[str, Any] | None, AgentReply | None, str | None]:
    """Deterministically capture a checkout slot or a detail-update confirmation.

    Returns ``(state_overrides, early_reply, new_text)``:
    - ``early_reply`` not None  → run_turn returns it immediately (a re-ask / confirm prompt).
    - otherwise ``state_overrides`` is merged and the agent is re-triggered with ``new_text``.
    - ``(None, None, None)`` → nothing pending this turn; run the model normally.
    The model never supplies these values — code validates the typed reply / button tap.
    """
    # (a) Detail-update(s) awaiting the customer's tap: apply ALL on Update, drop all on Keep.
    pending = values.get("pending_updates") or []
    if pending:
        clear = {"pending_updates": None}  # the reducer resets the queue to empty
        if reply_id == BTN_UPDATE_CONFIRM:
            overrides: dict[str, Any] = {**clear}
            fields = {u["field"] for u in pending}
            for upd in pending:
                if upd["field"] == "area":
                    # Re-resolve the new AREA against the real zones (place_order matches
                    # zone_query) and re-collect the street address within it — unless a street
                    # address change was sent in the same batch (then keep the one they gave).
                    overrides["zone_query"] = upd["value"]
                    overrides["zone_id"] = None
                    overrides["zone_serviceable"] = None
                    if "address" not in fields:
                        overrides["address"] = None
                else:
                    # name / email / alternate_phone / address (street) → write the saved field. A
                    # street-address change stays WITHIN the same area, so it does NOT touch the zone.
                    overrides[_UPDATE_STATE_KEY[upd["field"]]] = upd["value"]
            return overrides, None, _RETRIGGER
        if reply_id == BTN_UPDATE_KEEP:
            return clear, None, _RETRIGGER
        # Any other reply while awaiting the tap → re-show the confirm buttons.
        return None, _render_update_confirm(pending, values), None

    # (b) A required slot is being collected: fulfillment / address / name.
    field = values.get("pending_checkout_field")
    if not field or confirmed:
        return None, None, None
    # A tap that isn't a recognized answer for this slot → don't capture; let the model handle it
    # (e.g. the customer tapped a product row to change the order while we were asking the name).
    if reply_id and not (
        (field == "fulfillment" and reply_id in (BTN_FUL_DELIVERY, BTN_FUL_PICKUP))
        or (field == "zone" and reply_id.startswith(ROW_ZONE_PREFIX))
    ):
        return None, None, None
    cleaned = " ".join((text or "").split())
    if not reply_id and cleaned.lower() in _CONTACT_ABORT_WORDS:
        # Change of mind → drop the prompt and let the agent handle it conversationally.
        return {"pending_checkout_field": None}, None, text

    if field == "fulfillment":
        ful = None
        if reply_id == BTN_FUL_DELIVERY or "deliver" in cleaned.lower():
            ful = "delivery"
        elif reply_id == BTN_FUL_PICKUP or "pick" in cleaned.lower() or "collect" in cleaned.lower():
            ful = "pickup"
        if ful is None:
            return None, _render_fulfillment_question(), None
        return {"fulfillment": ful, "pending_checkout_field": None}, None, _RETRIGGER

    if field == "zone":
        # An exact area tap → select that zone and confirm serviceability.
        if reply_id and reply_id.startswith(ROW_ZONE_PREFIX):
            return (
                {"zone_id": reply_id[len(ROW_ZONE_PREFIX) :], "zone_serviceable": True,
                 "zone_choices": None, "zone_prompt": None, "zone_query": None,
                 "pending_checkout_field": None},
                None, _RETRIGGER,
            )
        if cleaned.lower() in ("pickup", "pick up", "collect"):  # bail out of delivery → pickup
            return (
                {"fulfillment": "pickup", "zone_id": None, "zone_serviceable": None,
                 "zone_choices": None, "zone_prompt": None, "zone_query": None,
                 "pending_checkout_field": None},
                None, _RETRIGGER,
            )
        if cleaned:
            # A typed area → place_order matches it against the zones (and re-asks if no match).
            return (
                {"zone_query": cleaned, "zone_choices": None, "zone_prompt": None,
                 "pending_checkout_field": None},
                None, _RETRIGGER,
            )
        # Empty/unrecognized → re-show however we last asked (the list, or a text question).
        choices = values.get("zone_choices")
        if choices:
            return None, _render_zone_list(choices, values.get("zone_prompt")), None
        return None, _text_reply(values.get("zone_prompt") or _ZONE_TEXT_FALLBACK), None

    if field == "address":
        if cleaned.lower() in ("pickup", "pick up", "collect"):
            return (
                {"fulfillment": "pickup", "address": None, "zone_id": None,
                 "zone_serviceable": None, "pending_checkout_field": None},
                None, _RETRIGGER,
            )
        if not cleaned:
            return None, _text_reply(_CHECKOUT_QUESTIONS["address"]), None
        # The AREA (zone) was already chosen before this step, so the street address stays WITHIN
        # it — don't clear the zone here (that would loop back to re-asking the area).
        return ({"address": cleaned, "pending_checkout_field": None}, None, _RETRIGGER)

    if field == "name":
        value, error = _capture_contact("name", text)
        if error:
            return None, _text_reply(error), None
        return {"customer_name": value, "pending_checkout_field": None}, None, _RETRIGGER

    return None, None, None


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

    # Deterministic checkout capture: if we're collecting a slot (fulfillment / address / name) or
    # awaiting a detail-update tap, validate + store it in CODE here — the model never sets these
    # values. A re-ask is returned immediately; a captured value re-triggers place_order.
    capture_overrides: dict[str, Any] = {}
    overrides, early_reply, new_text = _capture_checkout(values, text, reply_id, confirmed)
    if early_reply is not None:
        return early_reply
    if overrides is not None:
        capture_overrides = overrides
        if new_text is not None:
            text = new_text

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
            # Area-pick prompt state is re-set by place_order each turn when it (re-)asks; reset it
            # here so a resolved/stale area question can't linger and re-render. capture_overrides
            # (spread last) re-supplies zone_query when the customer typed an area this turn.
            "zone_choices": None,
            "zone_prompt": None,
            "zone_query": None,
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
    # A detail-update was proposed this turn (model called update_detail) → ask the customer to
    # confirm it deterministically; their tap (next turn) applies + persists the new value.
    updates_now = result.get("pending_updates")
    if updates_now:
        return _render_update_confirm(updates_now, result)
    # A required checkout slot is missing → ask for it with a fixed, code-rendered prompt (the
    # next reply is captured deterministically above, not by the model).
    pending_now = result.get("pending_checkout_field")
    if pending_now == "fulfillment":
        return _render_fulfillment_question()
    if pending_now == "zone":
        # A list of the delivery areas to tap (exact pick), or a free-text ask when there are
        # more zones than a WhatsApp list can hold. The body carries any out-of-area apology.
        choices = result.get("zone_choices")
        if choices:
            return _render_zone_list(choices, result.get("zone_prompt"))
        return _text_reply(result.get("zone_prompt") or _ZONE_TEXT_FALLBACK)
    if pending_now in ("address", "name"):
        return _text_reply(_CHECKOUT_QUESTIONS[pending_now])
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
