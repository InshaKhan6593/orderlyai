"""Agent working state — the live cart + flow, persisted by the checkpointer.

This is the LangGraph short-term memory keyed by ``thread_id = business_id:wa_phone``. It
(and the message history) is persisted by the LangGraph checkpointer — the Postgres
``checkpoint*`` tables, NOT a hand-rolled messages table — and is distinct from business data
(the CMS tables). The cart never becomes a DB row until the order is placed.

Cart lines are stored as plain ``dict``s (not Pydantic instances) so they round-trip
cleanly through the checkpointer's JSON serializer.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain.agents import AgentState  # type: ignore[import-not-found]

Step = Literal["browsing", "building", "confirming", "placed", "handed_off"]


class CartLine(TypedDict):
    product_id: str
    name: str                      # display snapshot only — price is always recomputed
    quantity: int
    option_item_ids: list[str]
    options_label: str             # "Large, Extra cheese" for summaries


class PendingUpdate(TypedDict):
    """One proposed change to a saved detail, awaiting the customer's Update tap.

    ``area`` is special: applying it re-resolves the value against the real delivery zones and
    re-asks the street address (handled in runtime), rather than writing one saved field.
    """

    field: Literal["name", "email", "alternate_phone", "address", "area"]
    value: str


def merge_pending_updates(
    left: list[PendingUpdate] | None, right: list[PendingUpdate] | None
) -> list[PendingUpdate]:
    """Reducer for ``pending_updates``.

    A list update APPENDS, so several ``update_detail`` calls in ONE turn (the customer asked to
    change their email AND alternate phone in one message) all accumulate instead of the last one
    overwriting the rest. A ``None`` update RESETS the queue to empty — used to clear it after the
    customer taps Update / Keep current. A later proposal for the same field supersedes the
    earlier one (dedupe by field), so re-stating one detail won't queue it twice.
    """
    if right is None:
        return []
    if not isinstance(right, list):
        right = [right]
    by_field: dict[str, PendingUpdate] = {u["field"]: u for u in (left or [])}
    for u in right:
        by_field[u["field"]] = u
    return list(by_field.values())


class OrderingState(AgentState):
    """Extends the built-in messages state with ordering-specific working memory."""

    cart: list[CartLine]
    selected_product_id: str | None
    fulfillment: Literal["delivery", "pickup"] | None
    address: str | None
    customer_name: str | None      # contact details, loaded deterministically from the saved
    customer_email: str | None     # customer record at checkout (the model never sets them)
    customer_alt_phone: str | None
    pending_checkout_field: Literal["fulfillment", "zone", "address", "name"] | None
                                   # set by place_order when a required checkout slot is missing;
                                   # run_turn then asks for it deterministically and validates the
                                   # typed reply / tap in code, then re-triggers checkout. Persists
                                   # across turns until filled (not reset per turn). Required slots
                                   # are fulfillment, the delivery AREA (zone) + street address, and
                                   # the name; email and alternate phone are OPTIONAL (update_detail).
    pending_updates: Annotated[list[PendingUpdate], merge_pending_updates]
                                   # changes the model surfaced via update_detail: each validated
                                   # NEW value awaits the customer tapping Update (deterministic) —
                                   # only then are they applied to the order + saved as defaults.
                                   # A LIST (not a scalar) so several detail changes asked for in
                                   # one message are all collected; the reducer appends + dedupes.
    zone_id: str | None
    zone_serviceable: bool | None
    zone_choices: list[dict] | None  # rows for the delivery-area pick list (id/title/description),
                                   # set by place_order and rendered by run_turn; None → the area is
                                   # asked as free text (more zones than a WhatsApp list can hold).
    zone_prompt: str | None        # the body text for the area question (first ask vs out-of-area).
    zone_query: str | None         # a typed area name awaiting a match against the business's zones.
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
        "pending_checkout_field": None,
        "pending_updates": [],
        "zone_id": None,
        "zone_serviceable": None,
        "zone_choices": None,
        "zone_prompt": None,
        "zone_query": None,
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
