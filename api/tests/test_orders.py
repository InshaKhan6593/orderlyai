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
