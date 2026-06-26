"""Per-turn agent business snapshot, with a short TTL cache.

The agent needs the same tenant facts (identity, hours, fees, categories) AND the current
menu on nearly every model call. Loading them from Postgres on each of the up-to-N model
calls in a turn — and again on the next turn seconds later — is wasteful, so the rendered
snapshot is cached per business for a few seconds (``agent_snapshot_ttl_seconds``).

This is safe because the snapshot only feeds the *system prompt* (guidance). The hard
guarantees — ``accepting_orders``, opening hours, and pricing — are always re-validated
live against the DB at order time in ``order_service`` (see ``place_order``), so a few
seconds of prompt staleness can never let a bad order through.

The menu is inlined into the prompt when its rendered size is within
``agent_menu_preload_max_chars``; otherwise ``menu_preloaded`` is False and the agent fetches
it on demand via the ``get_menu`` tool. ``TenantMiddleware`` reads ``menu_preloaded`` to drop
``get_menu`` from the tool set on inlined turns.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from app.agent import catalog
from app.agent.prompts import BusinessBrief
from app.core.config import settings
from app.core.db import SessionLocal


@dataclass(frozen=True, slots=True)
class AgentSnapshot:
    """One business's prompt inputs for a turn. ``brief`` fills the system-prompt
    placeholders; ``menu_preloaded`` says whether the menu was inlined into it."""

    brief: BusinessBrief
    menu_preloaded: bool


# business_id (str) -> (expires_at_monotonic, snapshot). Process-local; bounded by the
# tenant count (~150), so no eviction policy is needed beyond TTL overwrite.
_CACHE: dict[str, tuple[float, AgentSnapshot]] = {}


def _brief(business, menu_index: str | None) -> BusinessBrief:
    """Render the per-tenant prompt brief off the eager-loaded business."""
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
        categories_summary=", ".join(catalog.category_names(business)),
        extra_instructions=cfg.extra_instructions if cfg else None,
        handoff_phone=cfg.human_handoff_phone if cfg else None,
        menu_index=menu_index,
    )


async def _build(business_id: uuid.UUID) -> AgentSnapshot | None:
    """Load the business + menu and decide whether the menu fits the preload budget."""
    async with SessionLocal() as s:
        business = await catalog.load_business_for_agent(s, business_id)
        if business is None:
            return None
        menu_text = await catalog.menu_overview(s, business)

    budget = settings.agent_menu_preload_max_chars
    preloaded = budget > 0 and len(menu_text) <= budget
    return AgentSnapshot(
        brief=_brief(business, menu_text if preloaded else None),
        menu_preloaded=preloaded,
    )


async def get_snapshot(business_id: uuid.UUID) -> AgentSnapshot | None:
    """Return the cached snapshot for a business, rebuilding it when the TTL has lapsed.

    Returns ``None`` when the business doesn't exist (the caller falls back to a safe
    "unavailable" prompt). A rare concurrent miss simply rebuilds twice — both reads are
    idempotent — so no lock is needed.
    """
    ttl = settings.agent_snapshot_ttl_seconds
    key = str(business_id)
    now = time.monotonic()

    if ttl > 0:
        cached = _CACHE.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

    snapshot = await _build(business_id)

    if ttl > 0 and snapshot is not None:
        _CACHE[key] = (now + ttl, snapshot)
    return snapshot
