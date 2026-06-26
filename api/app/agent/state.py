"""Agent working state — the live cart + flow, persisted by the checkpointer.

This is the LangGraph short-term memory keyed by ``thread_id = business_id:wa_phone``. It
(and the message history) is persisted by the LangGraph checkpointer — the Postgres
``checkpoint*`` tables, NOT a hand-rolled messages table — and is distinct from business data
(the CMS tables). The cart never becomes a DB row until the order is placed.

Cart lines are stored as plain ``dict``s (not Pydantic instances) so they round-trip
cleanly through the checkpointer's JSON serializer.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

from langchain.agents import AgentState  # type: ignore[import-not-found]

Step = Literal["browsing", "building", "confirming", "placed", "handed_off"]


class CartLine(TypedDict):
    product_id: str
    name: str                      # display snapshot only — price is always recomputed
    quantity: int
    option_item_ids: list[str]
    options_label: str             # "Large, Extra cheese" for summaries


class OrderingState(AgentState):
    """Extends the built-in messages state with ordering-specific working memory."""

    cart: list[CartLine]
    selected_product_id: str | None
    fulfillment: Literal["delivery", "pickup"] | None
    address: str | None
    customer_name: str | None      # contact details, loaded deterministically from the saved
    customer_email: str | None     # customer record at checkout (the model never sets them)
    customer_alt_phone: str | None
    pending_contact_field: Literal["name", "email", "alternate_phone"] | None
                                   # set by place_order when a required contact field is missing;
                                   # run_turn then asks for it and validates/saves the typed reply
                                   # in code. Persists across turns until filled (not reset per turn)
    zone_id: str | None
    zone_serviceable: bool | None
    notes: str | None
    step: Step
    confirmed: bool                # flipped ONLY by the confirm-button handler (worker)
    awaiting_confirm: bool         # set by place_order when a Confirm tap is needed; run_turn
                                   # then GUARANTEES the [Confirm][Edit][Cancel] buttons render
    confirm_summary: str | None    # server-priced cart total shown alongside those buttons
    order_placed_summary: str | None  # set by place_order on success; run_turn sends it verbatim
    handoff_reason: str | None
    handoff_at: str | None         # ISO time of handoff; run_turn auto-resumes after the mute window


def new_line(
    product_id: str, name: str, quantity: int, option_item_ids: list[str], options_label: str
) -> CartLine:
    return {
        "product_id": product_id,
        "name": name,
        "quantity": quantity,
        "option_item_ids": option_item_ids,
        "options_label": options_label,
    }


def initial_state(**overrides: Any) -> dict[str, Any]:
    """Defaults applied for a brand-new thread (merged into the first turn's input)."""
    base: dict[str, Any] = {
        "cart": [],
        "selected_product_id": None,
        "fulfillment": None,
        "address": None,
        "customer_name": None,
        "customer_email": None,
        "customer_alt_phone": None,
        "pending_contact_field": None,
        "zone_id": None,
        "zone_serviceable": None,
        "notes": None,
        "step": "browsing",
        "confirmed": False,
        "awaiting_confirm": False,
        "confirm_summary": None,
        "order_placed_summary": None,
        "handoff_reason": None,
        "handoff_at": None,
    }
    base.update(overrides)
    return base
