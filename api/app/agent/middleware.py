"""Agent middleware (async — the agent runs via ``ainvoke``).

``TenantMiddleware`` is the per-run brain wiring done in one async hook:
  1. loads the business from ``runtime.context`` and renders the per-tenant system prompt
     (this is also the "read-before-write" guardrail, stated in natural language),
  2. exposes cart/checkout tools only once a cart exists (a guardrail + less confusion),
  3. escalates to the stronger model on long/hard turns.

Note: hooks MUST be async here — LangChain raises NotImplementedError if only the sync
variant is defined and the agent is invoked with ``ainvoke``.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import (  # type: ignore[import-not-found]
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)

from app.agent import catalog
from app.agent.context import ctx_dict
from app.agent.prompts import BusinessBrief, build_system_prompt
from app.agent.tools import CART_ONLY_TOOLS
from app.core.db import SessionLocal


def _brief(business: Any) -> BusinessBrief:
    cfg = business.agent_config
    hours = list(business.hours)
    return BusinessBrief(
        name=business.name,
        business_type=business.type.replace("_", " "),
        currency=business.currency,
        hours_summary=catalog.format_hours(hours),
        is_open=catalog.is_open_now(hours, business.timezone),
        accepting_orders=business.accepting_orders,
        offers_delivery=business.offers_delivery,
        offers_pickup=business.offers_pickup,
        min_order_amount=str(business.min_order_amount),
        packaging_fee=str(business.packaging_fee),
        upsell_enabled=cfg.upsell_enabled if cfg else True,
        greeting=(cfg.greeting_message if cfg else None)
        or f"Hi! Welcome to {business.name}. How can I help?",
        extra_instructions=cfg.extra_instructions if cfg else None,
        handoff_phone=cfg.human_handoff_phone if cfg else None,
    )

_FALLBACK_PROMPT = (
    "You are a WhatsApp ordering assistant. This business is not available right now; "
    "apologize briefly and do not take an order."
)


class TenantMiddleware(AgentMiddleware):
    """Per-run prompt + tool gating + model selection (all async)."""

    def __init__(
        self, tools: list, base_model: Any, escalated_model: Any, *, escalate_after: int = 24
    ) -> None:
        super().__init__()
        self._tools = tools
        self._base = base_model
        self._escalated = escalated_model
        self._escalate_after = escalate_after

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        business_id = ctx_dict(request.runtime).get("business_id")
        prompt = _FALLBACK_PROMPT
        if business_id:
            async with SessionLocal() as s:
                business = await catalog.load_business_for_agent(s, uuid.UUID(business_id))
            if business is not None:
                prompt = build_system_prompt(_brief(business))

        cart = request.state.get("cart") or []
        tools = (
            self._tools
            if cart
            else [t for t in self._tools if getattr(t, "name", "") not in CART_ONLY_TOOLS]
        )
        model = self._escalated if len(request.messages) > self._escalate_after else self._base
        return await handler(
            request.override(system_prompt=prompt, tools=tools, model=model)
        )
