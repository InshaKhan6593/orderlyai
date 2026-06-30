"""catalog.menu_overview category filtering + category_names, against the test DB.

Sync tests that drive the async catalog helpers via asyncio.run (same pattern as conftest),
reusing the session factory bound to the test database.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace

from conftest import _TestSession

from app.agent import catalog


def test_menu_overview_filters_by_category(menu):
    biz_id = uuid.UUID(menu["biz"])

    async def go():
        async with _TestSession() as s:
            b = await catalog.load_business_for_agent(s, biz_id)
            full = await catalog.menu_overview(s, b)
            mains = await catalog.menu_overview(s, b, category="mains")  # case-insensitive
            missing = await catalog.menu_overview(s, b, category="Sushi")
            return full, mains, missing, catalog.category_names(b)

    full, mains, missing, names = asyncio.run(go())
    assert "Burger" in full
    assert "Burger" in mains                          # filtered section returned the item
    assert names == ["Mains"]                         # prompt-facing, active categories only
    assert "Available categories: Mains" in missing   # unknown category lists the real ones
    assert "Burger" not in missing                    # ...and no items


# --------------------------------------------------------------------------- #
# zones_summary — the prompt-facing delivery-area list (pure; no DB)
# --------------------------------------------------------------------------- #
def _zone(name, fee):
    return SimpleNamespace(name=name, fee=Decimal(fee))


def test_zones_summary_lists_areas_with_fees():
    out = catalog.zones_summary([_zone("Gulberg", "80"), _zone("DHA", "0")], "PKR")
    assert "Gulberg (80 PKR)" in out
    assert "DHA (free)" in out  # a zero fee reads as "free", not "0 PKR"


def test_zones_summary_empty_when_no_zones():
    assert catalog.zones_summary([], "PKR") == ""


def test_zones_summary_caps_long_lists():
    zones = [_zone(f"Area {i}", "50") for i in range(25)]
    out = catalog.zones_summary(zones, "PKR", max_listed=20)
    assert "and 5 more areas" in out  # overflow summarised so the prompt can't bloat
    assert out.count("(50 PKR)") == 20
