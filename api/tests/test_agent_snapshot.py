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
