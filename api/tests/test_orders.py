"""Order pricing and status-machine tests."""
from __future__ import annotations

from decimal import Decimal


def _seed_burger(client, owner, biz):
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
            "modifier_groups": [
                {"modifier_group_id": group["id"], "max_select": 1}
            ],
        },
        headers=owner,
    ).json()
    large = next(i for i in group["items"] if i["name"] == "Large")
    return prod, large


def test_order_total_includes_modifier_deltas(client, business):
    owner, biz = business
    prod, large = _seed_burger(client, owner, biz)
    r = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "+923001112222",
            "fulfillment": "pickup",
            "items": [{"product_id": prod["id"], "quantity": 2, "option_item_ids": [large["id"]]}],
        },
        headers=owner,
    )
    assert r.status_code == 201, r.text
    # (850 base + 250 Large) * 2 = 2200
    assert Decimal(str(r.json()["total"])) == Decimal("2200")


def test_order_number_increments_per_business(client, business):
    owner, biz = business
    prod, _ = _seed_burger(client, owner, biz)
    payload = {
        "customer_phone": "+923000000000",
        "fulfillment": "pickup",
        "items": [{"product_id": prod["id"], "quantity": 1}],
    }
    o1 = client.post(f"/api/v1/businesses/{biz}/orders", json=payload, headers=owner).json()
    o2 = client.post(f"/api/v1/businesses/{biz}/orders", json=payload, headers=owner).json()
    assert o2["order_no"] == o1["order_no"] + 1


def test_order_response_includes_customer_and_zone_for_dashboard(client, business):
    owner, biz = business
    prod, _ = _seed_burger(client, owner, biz)
    zone = client.post(
        f"/api/v1/businesses/{biz}/delivery-zones",
        json={"name": "Gulshan", "fee": "150", "min_order": "0"},
        headers=owner,
    ).json()

    created = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "+923001234567",
            "customer_name": "Ayesha Khan",
            "fulfillment": "delivery",
            "address": "House 18, Block 7, Gulshan, Karachi",
            "zone_id": zone["id"],
            "items": [{"product_id": prod["id"], "quantity": 1}],
        },
        headers=owner,
    )
    assert created.status_code == 201, created.text

    order = client.get(
        f"/api/v1/businesses/{biz}/orders/{created.json()['id']}", headers=owner
    ).json()
    assert order["customer"]["name"] == "Ayesha Khan"
    assert order["customer"]["wa_phone"] == "+923001234567"
    assert order["zone"]["name"] == "Gulshan"
    assert order["zone"]["fee"] == "150.00"


def test_delivery_order_saves_area_and_address_as_customer_preference(client, business):
    # A delivery order persists the chosen area (zone) + street address onto the customer record,
    # so the agent can prefill them on the next order instead of re-asking.
    import asyncio
    import uuid as _uuid

    from sqlalchemy import select
    from conftest import _TestSession
    from app.models.customer import Customer

    owner, biz = business
    prod, _ = _seed_burger(client, owner, biz)
    zone = client.post(
        f"/api/v1/businesses/{biz}/delivery-zones",
        json={"name": "Defence", "fee": "120", "min_order": "0"},
        headers=owner,
    ).json()
    created = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "+923004445566",
            "customer_name": "Sara",
            "fulfillment": "delivery",
            "address": "House 5, Street 10, Defence",
            "zone_id": zone["id"],
            "items": [{"product_id": prod["id"], "quantity": 1}],
        },
        headers=owner,
    )
    assert created.status_code == 201, created.text

    async def _load():
        async with _TestSession() as s:
            return await s.scalar(
                select(Customer).where(
                    Customer.business_id == _uuid.UUID(biz),
                    Customer.wa_phone == "+923004445566",
                )
            )

    cust = asyncio.run(_load())
    assert str(cust.default_zone_id) == zone["id"]
    assert cust.default_address == "House 5, Street 10, Defence"


def test_invalid_status_transition_rejected(client, business):
    owner, biz = business
    prod, _ = _seed_burger(client, owner, biz)
    order = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "+923009998888",
            "fulfillment": "pickup",
            "items": [{"product_id": prod["id"], "quantity": 1}],
        },
        headers=owner,
    ).json()
    oid = order["id"]
    # pending -> accepted is allowed
    assert (
        client.patch(
            f"/api/v1/businesses/{biz}/orders/{oid}/status",
            json={"status": "accepted"},
            headers=owner,
        ).status_code
        == 200
    )
    # accepted -> completed is NOT allowed (must go through preparing → ready/out)
    assert (
        client.patch(
            f"/api/v1/businesses/{biz}/orders/{oid}/status",
            json={"status": "completed"},
            headers=owner,
        ).status_code
        == 400
    )
