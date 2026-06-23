"""Agent working state — the live cart + flow, persisted by the checkpointer.

This is the LangGraph short-term memory keyed by ``thread_id = business_id:wa_phone``.
It is NOT the durable chat log (that's the ``messages`` table) and NOT business data
(that's the CMS tables). The cart never becomes a DB row until the order is placed.

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
    zone_id: str | None
    zone_serviceable: bool | None
    notes: str | None
    step: Step
    confirmed: bool                # flipped ONLY by the confirm-button handler (worker)
    handoff_reason: str | None


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
        "zone_id": None,
        "zone_serviceable": None,
        "notes": None,
        "step": "browsing",
        "confirmed": False,
        "handoff_reason": None,
    }
    base.update(overrides)
    return base
