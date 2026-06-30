"""Agent business snapshot: menu-preload threshold, TTL caching, and tool gating.

The DB-backed cases drive ``snapshot.get_snapshot`` against the test database (the same
pattern as ``test_agent_catalog``), pointing the module's own ``SessionLocal`` at the test
session factory. The ``select_tools`` cases are pure (no DB).
"""
from __future__ import annotations

import asyncio
import uuid

from conftest import _TestSession

from app.agent import snapshot
from app.agent.middleware import select_tools
from app.agent.tools import CART_ONLY_TOOLS, TOOLS
from app.core.config import settings


def _build_snapshot(biz_id, monkeypatch, **setting_overrides):
    """Run get_snapshot against the test DB with a clean cache and given settings."""
    monkeypatch.setattr(snapshot, "SessionLocal", _TestSession)
    for key, value in setting_overrides.items():
        monkeypatch.setattr(settings, key, value)
    snapshot._CACHE.clear()
    return asyncio.run(snapshot.get_snapshot(biz_id))


# --------------------------------------------------------------------------- #
# Snapshot build + menu preload threshold (DB-backed)
# --------------------------------------------------------------------------- #
def test_small_menu_is_inlined(menu, monkeypatch):
    snap = _build_snapshot(
        uuid.UUID(menu["biz"]), monkeypatch, agent_snapshot_ttl_seconds=0
    )
    assert snap is not None
    assert snap.menu_preloaded is True
    assert snap.brief.menu_index and "Burger" in snap.brief.menu_index


def test_large_menu_falls_back_to_get_menu(menu, monkeypatch):
    # Tiny budget → the rendered menu exceeds it → not inlined, fetched via the tool instead.
    snap = _build_snapshot(
        uuid.UUID(menu["biz"]),
        monkeypatch,
        agent_snapshot_ttl_seconds=0,
        agent_menu_preload_max_chars=10,
    )
    assert snap is not None
    assert snap.menu_preloaded is False
    assert snap.brief.menu_index is None


def test_missing_business_returns_none(monkeypatch):
    snap = _build_snapshot(uuid.uuid4(), monkeypatch, agent_snapshot_ttl_seconds=0)
    assert snap is None


# --------------------------------------------------------------------------- #
# TTL cache behavior (DB-backed)
# --------------------------------------------------------------------------- #
def test_cache_hit_reuses_snapshot(menu, monkeypatch):
    biz = uuid.UUID(menu["biz"])
    monkeypatch.setattr(snapshot, "SessionLocal", _TestSession)
    monkeypatch.setattr(settings, "agent_snapshot_ttl_seconds", 60)
    snapshot._CACHE.clear()

    async def go():
        return await snapshot.get_snapshot(biz), await snapshot.get_snapshot(biz)

    first, second = asyncio.run(go())
    assert first is second  # second call served from cache, no rebuild


def test_ttl_zero_disables_cache(menu, monkeypatch):
    biz = uuid.UUID(menu["biz"])
    monkeypatch.setattr(snapshot, "SessionLocal", _TestSession)
    monkeypatch.setattr(settings, "agent_snapshot_ttl_seconds", 0)
    snapshot._CACHE.clear()

    async def go():
        return await snapshot.get_snapshot(biz), await snapshot.get_snapshot(biz)

    first, second = asyncio.run(go())
    assert first is not second  # rebuilt each call
    assert str(biz) not in snapshot._CACHE  # nothing cached


# --------------------------------------------------------------------------- #
# Returning-customer profile (DB-backed, tenant-scoped)
# --------------------------------------------------------------------------- #
def _seed_customer(biz_id, phone, *, name=None, address=None, count=0):
    from app.models.customer import Customer

    async def go():
        async with _TestSession() as s:
            s.add(
                Customer(
                    business_id=uuid.UUID(biz_id),
                    wa_phone=phone,
                    name=name,
                    default_address=address,
                    order_count=count,
                )
            )
            await s.commit()

    asyncio.run(go())


def _get_brief(biz_id, phone, monkeypatch):
    monkeypatch.setattr(snapshot, "SessionLocal", _TestSession)
    monkeypatch.setattr(settings, "agent_snapshot_ttl_seconds", 0)
    snapshot._CUSTOMER_CACHE.clear()
    return asyncio.run(snapshot.get_customer_brief(uuid.UUID(biz_id), phone))


def test_customer_brief_loads_saved_profile(business, monkeypatch):
    _, biz = business
    _seed_customer(biz, "16500001111", name="Ada", address="12 Park Lane", count=3)
    brief = _get_brief(biz, "16500001111", monkeypatch)
    assert brief is not None
    assert brief.name == "Ada"
    assert brief.default_address == "12 Park Lane"
    assert brief.order_count == 3


def test_customer_brief_none_for_unknown_sender(business, monkeypatch):
    _, biz = business
    assert _get_brief(biz, "16500009999", monkeypatch) is None


def test_customer_brief_is_tenant_scoped(client, business, monkeypatch):
    owner, biz = business
    other = client.post(
        "/api/v1/businesses",
        json={"name": "Other Cafe", "type": "cafe", "currency": "PKR"},
        headers=owner,
    ).json()
    # Same phone, different saved name per business → each agent sees only its own customer.
    _seed_customer(biz, "16500001111", name="Ada")
    _seed_customer(other["id"], "16500001111", name="Bilal")
    assert _get_brief(biz, "16500001111", monkeypatch).name == "Ada"
    assert _get_brief(other["id"], "16500001111", monkeypatch).name == "Bilal"


# --------------------------------------------------------------------------- #
# Tool gating (pure)
# --------------------------------------------------------------------------- #
def test_get_menu_dropped_when_menu_preloaded():
    names = {t.name for t in select_tools(TOOLS, has_cart=True, menu_preloaded=True)}
    assert "get_menu" not in names
    assert CART_ONLY_TOOLS <= names  # a cart exists → checkout tools are available


def test_get_menu_kept_when_menu_not_preloaded():
    names = {t.name for t in select_tools(TOOLS, has_cart=True, menu_preloaded=False)}
    assert "get_menu" in names


def test_cart_tools_hidden_until_cart_has_items():
    names = {t.name for t in select_tools(TOOLS, has_cart=False, menu_preloaded=False)}
    assert names.isdisjoint(CART_ONLY_TOOLS)  # no view_cart/place_order yet
    assert "add_to_cart" in names  # ...but you can still start a cart
    assert "get_menu" in names  # not preloaded → menu tool available
