"""catalog.menu_overview category filtering + category_names, against the test DB.

Sync tests that drive the async catalog helpers via asyncio.run (same pattern as conftest),
reusing the session factory bound to the test database.
"""
from __future__ import annotations

import asyncio
import uuid

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
