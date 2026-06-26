"""Reorder: repeat a customer's own past order, re-priced against today's menu.

The reorder tool rebuilds the cart from a past order — re-validating and re-pricing every line
against the LIVE menu (golden rule: pricing is server-authoritative), skipping anything now sold
out / removed / changed, and never reaching another customer's or another tenant's orders. These
drive the tool directly against the test DB with a fake ToolRuntime (the agent injects the real
one in production); get_order_status enrichment is covered here too.
"""
from __future__ import annotations

import asyncio

from conftest import _TestSession
from app.agent.tools import get_order_status, reorder


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class _Runtime:
    """Stand-in for the injected ToolRuntime: just the context/state the tools read."""

    def __init__(self, business_id, phone, *, cart=None):
        self.context = {"business_id": str(business_id), "customer_phone": phone}
        self.tool_call_id = "test-call"
        self.state = {"cart": list(cart or [])}


def _seed_burger(client, owner, biz):
    """A Burger (850) with an optional single-select Size group (Regular +0, Large +250)."""
    cat = client.post(
        f"/api/v1/businesses/{biz}/categories", json={"name": "Mains"}, headers=owner
    ).json()
    group = client.post(
        f"/api/v1/businesses/{biz}/modifier-groups",
        json={
            "name": "Size",
            "select_type": "single",
            "items": [
                {"name": "Regular", "price_delta": "0", "is_default": True},
                {"name": "Large", "price_delta": "250"},
            ],
        },
        headers=owner,
    ).json()
    prod = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Burger",
            "price": "850",
            "category_id": cat["id"],
            "modifier_groups": [{"modifier_group_id": group["id"], "max_select": 1}],
        },
        headers=owner,
    ).json()
    large = next(i for i in group["items"] if i["name"] == "Large")
    return prod, large


def _create_order(client, owner, biz, prod_id, phone, *, qty=2, options=None):
    item = {"product_id": prod_id, "quantity": qty}
    if options:
        item["option_item_ids"] = options
    r = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": phone,
            "customer_name": "Ada",
            "fulfillment": "pickup",
            "items": [item],
        },
        headers=owner,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# reorder — happy path
# --------------------------------------------------------------------------- #
def test_reorder_rebuilds_cart_from_most_recent_order(client, business, monkeypatch):
    owner, biz = business
    prod, large = _seed_burger(client, owner, biz)
    _create_order(client, owner, biz, prod["id"], "16500001111", qty=2, options=[large["id"]])

    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    rt = _Runtime(biz, "16500001111", cart=[])
    cmd = _run(reorder.coroutine(order_no=None, runtime=rt))

    cart = cmd.update["cart"]
    assert len(cart) == 1
    assert cart[0]["product_id"] == prod["id"]
    assert cart[0]["quantity"] == 2
    assert cart[0]["options_label"] == "Large"
    assert cmd.update["step"] == "building"
    assert "Re-added" in cmd.update["messages"][0].content


def test_reorder_specific_order_number(client, business, monkeypatch):
    owner, biz = business
    prod, large = _seed_burger(client, owner, biz)
    first = _create_order(client, owner, biz, prod["id"], "16500001111", qty=1)
    _create_order(client, owner, biz, prod["id"], "16500001111", qty=3, options=[large["id"]])

    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    rt = _Runtime(biz, "16500001111", cart=[])
    cmd = _run(reorder.coroutine(order_no=first["order_no"], runtime=rt))

    cart = cmd.update["cart"]
    assert len(cart) == 1
    assert cart[0]["quantity"] == 1  # the FIRST order, not the most recent (qty 3)
    assert cart[0]["options_label"] == ""


def test_reorder_reprices_against_live_menu_not_snapshot(client, business, monkeypatch):
    # The order snapshots name "Burger"; renaming the product proves reorder re-resolves the line
    # against the LIVE product (and therefore its current price), never the frozen snapshot.
    owner, biz = business
    prod, _ = _seed_burger(client, owner, biz)
    _create_order(client, owner, biz, prod["id"], "16500001111", qty=1)
    client.patch(
        f"/api/v1/businesses/{biz}/products/{prod['id']}",
        json={"name": "Cheeseburger", "price": "900"},
        headers=owner,
    )

    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    rt = _Runtime(biz, "16500001111", cart=[])
    cmd = _run(reorder.coroutine(order_no=None, runtime=rt))

    assert cmd.update["cart"][0]["name"] == "Cheeseburger"
    assert "Cheeseburger" in cmd.update["messages"][0].content


# --------------------------------------------------------------------------- #
# reorder — items that can no longer be re-added
# --------------------------------------------------------------------------- #
def test_reorder_skips_unavailable_item(client, business, monkeypatch):
    owner, biz = business
    prod, _ = _seed_burger(client, owner, biz)
    _create_order(client, owner, biz, prod["id"], "16500001111", qty=1)
    client.patch(
        f"/api/v1/businesses/{biz}/products/{prod['id']}",
        json={"is_available": False},
        headers=owner,
    )

    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    rt = _Runtime(biz, "16500001111", cart=[])
    cmd = _run(reorder.coroutine(order_no=None, runtime=rt))

    # Nothing re-addable → cart is left untouched (no cart key in the update) and we explain.
    assert "cart" not in cmd.update
    assert "couldn't re-add" in cmd.update["messages"][0].content.lower()


def test_reorder_skips_archived_but_adds_the_rest(client, business, monkeypatch):
    owner, biz = business
    burger, _ = _seed_burger(client, owner, biz)
    fries = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={"name": "Fries", "price": "200"},
        headers=owner,
    ).json()
    # One order with both items, then archive the burger.
    r = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "16500001111",
            "fulfillment": "pickup",
            "items": [
                {"product_id": burger["id"], "quantity": 1},
                {"product_id": fries["id"], "quantity": 2},
            ],
        },
        headers=owner,
    )
    assert r.status_code == 201, r.text
    client.patch(
        f"/api/v1/businesses/{biz}/products/{burger['id']}",
        json={"is_archived": True},
        headers=owner,
    )

    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    rt = _Runtime(biz, "16500001111", cart=[])
    cmd = _run(reorder.coroutine(order_no=None, runtime=rt))

    cart = cmd.update["cart"]
    assert len(cart) == 1  # only Fries survived
    assert cart[0]["product_id"] == fries["id"]
    body = cmd.update["messages"][0].content
    assert "Fries" in body and "Couldn't re-add" in body and "Burger" in body


# --------------------------------------------------------------------------- #
# reorder — cart handling and "no past order"
# --------------------------------------------------------------------------- #
def test_reorder_appends_to_existing_cart(client, business, monkeypatch):
    owner, biz = business
    prod, _ = _seed_burger(client, owner, biz)
    _create_order(client, owner, biz, prod["id"], "16500001111", qty=1)

    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    existing = {
        "product_id": prod["id"],
        "name": "Burger",
        "quantity": 5,
        "option_item_ids": [],
        "options_label": "",
    }
    rt = _Runtime(biz, "16500001111", cart=[existing])
    cmd = _run(reorder.coroutine(order_no=None, runtime=rt))

    cart = cmd.update["cart"]
    assert len(cart) == 2  # the pre-existing line is kept, the reordered line appended
    assert cart[0]["quantity"] == 5


def test_reorder_no_previous_order_is_friendly(client, business, monkeypatch):
    owner, biz = business
    _seed_burger(client, owner, biz)

    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    rt = _Runtime(biz, "16500009999", cart=[])  # this phone never ordered
    cmd = _run(reorder.coroutine(order_no=None, runtime=rt))

    assert "cart" not in cmd.update
    assert "couldn't find a past order" in cmd.update["messages"][0].content.lower()


# --------------------------------------------------------------------------- #
# reorder — isolation (a customer can only repeat their OWN order, in THIS tenant)
# --------------------------------------------------------------------------- #
def test_reorder_is_customer_scoped(client, business, monkeypatch):
    owner, biz = business
    prod, _ = _seed_burger(client, owner, biz)
    _create_order(client, owner, biz, prod["id"], "16500001111", qty=1)

    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    # A DIFFERENT phone cannot see (or repeat) the first customer's order.
    rt = _Runtime(biz, "16500002222", cart=[])
    cmd = _run(reorder.coroutine(order_no=None, runtime=rt))
    assert "cart" not in cmd.update
    assert "couldn't find" in cmd.update["messages"][0].content.lower()


def test_reorder_is_tenant_scoped(client, business, monkeypatch):
    owner, biz = business
    prod, _ = _seed_burger(client, owner, biz)
    _create_order(client, owner, biz, prod["id"], "16500001111", qty=1)
    # A second business owned by the same user; its agent must not reach biz's orders.
    other = client.post(
        "/api/v1/businesses",
        json={"name": "Other Cafe", "type": "cafe", "currency": "PKR"},
        headers=owner,
    ).json()

    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    rt = _Runtime(other["id"], "16500001111", cart=[])
    cmd = _run(reorder.coroutine(order_no=None, runtime=rt))
    assert "cart" not in cmd.update
    assert "couldn't find" in cmd.update["messages"][0].content.lower()


# --------------------------------------------------------------------------- #
# get_order_status — now itemized
# --------------------------------------------------------------------------- #
def test_get_order_status_lists_items_with_quantities(client, business, monkeypatch):
    owner, biz = business
    prod, large = _seed_burger(client, owner, biz)
    _create_order(client, owner, biz, prod["id"], "16500001111", qty=2, options=[large["id"]])

    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    rt = _Runtime(biz, "16500001111", cart=[])
    out = _run(get_order_status.coroutine(order_no=None, runtime=rt))

    assert "Order #" in out
    assert "Burger x2" in out  # item name + quantity now surfaced
    assert "Large" in out  # chosen option shown too


def test_get_order_status_no_orders(client, business, monkeypatch):
    owner, biz = business
    _seed_burger(client, owner, biz)
    monkeypatch.setattr("app.agent.tools.SessionLocal", _TestSession)
    rt = _Runtime(biz, "16500007777", cart=[])
    out = _run(get_order_status.coroutine(order_no=None, runtime=rt))
    assert "No orders found" in out
