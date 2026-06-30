"""Agent middleware (async — the agent runs via ``ainvoke``).

``TenantMiddleware`` is the per-run brain wiring, done in one async hook:
  1. loads the per-tenant snapshot (identity + hours + fees + categories + the menu, cached
     for a few seconds) and renders the system prompt — inlining the menu when it fits, which
     is also the "read-before-write" guardrail stated in natural language,
  2. selects the tools the model may use: cart/checkout tools appear only once a cart exists,
     and ``get_menu`` is hidden when the menu is already inlined (so the model reads it from
     context instead of re-fetching it),
  3. escalates to the stronger model on long/hard turns.

Note: the hook MUST be async here — LangChain raises NotImplementedError if only the sync
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

from app.agent import snapshot
from app.agent.context import ctx_dict
from app.agent.prompts import customer_block, render_system_prompt
from app.agent.tools import CART_ONLY_TOOLS

_FALLBACK_PROMPT = (
    "You are a WhatsApp ordering assistant. This business is not available right now; "
    "apologize briefly and do not take an order."
)


def select_tools(tools: list, *, has_cart: bool, menu_preloaded: bool) -> list:
    """The tools the model may use this call (a guardrail + less for the model to confuse).

    - ``get_menu`` is dropped when the menu is already inlined in the prompt — the model
      should answer from context, not round-trip the tool.
    - Cart/checkout tools stay hidden until the cart has something in it.
    """
    chosen = tools
    if menu_preloaded:
        chosen = [t for t in chosen if getattr(t, "name", "") != "get_menu"]
    if not has_cart:
        chosen = [t for t in chosen if getattr(t, "name", "") not in CART_ONLY_TOOLS]
    return chosen


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
        context = ctx_dict(request.runtime)
        business_id = context.get("business_id")
        customer_phone = context.get("customer_phone")
        prompt = _FALLBACK_PROMPT
        menu_preloaded = False
        if business_id:
            snap = await snapshot.get_snapshot(uuid.UUID(business_id))
            if snap is not None:
                prompt = render_system_prompt(snap.brief)
                menu_preloaded = snap.menu_preloaded
                # Append the returning-customer profile (name + saved address) so the agent
                # personalises and doesn't re-ask details we already have. Loaded server-side
                # and scoped by phone, so it can't reach another tenant's customer.
                if customer_phone:
                    cust = await snapshot.get_customer_brief(
                        uuid.UUID(business_id), customer_phone
                    )
                    if cust is not None:
                        block = customer_block(
                            name=cust.name,
                            default_address=cust.default_address,
                            order_count=cust.order_count,
                        )
                        if block:
                            prompt = f"{prompt}\n\n{block}"

        tools = select_tools(
            self._tools,
            has_cart=bool(request.state.get("cart")),
            menu_preloaded=menu_preloaded,
        )
        model = self._escalated if len(request.messages) > self._escalate_after else self._base
        return await handler(
            request.override(system_prompt=prompt, tools=tools, model=model)
        )
