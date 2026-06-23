"""Regression tests for the backend review findings.

Each test maps to a finding: cross-tenant category leak, negative totals,
delivery-zone rules, fulfillment-aware + audited status machine, duplicate
business hours, pagination, and input caps.
"""
from __future__ import annotations


def _product(client, owner, biz, **body):
    base = {"name": "Item", "price": "100"}
    base.update(body)
    return client.post(
        f"/api/v1/businesses/{biz}/products", json=base, headers=owner
    ).json()


def _modifier_group(client, owner, biz, **body):
    base = {"name": "Options", "select_type": "single", "items": []}
    base.update(body)
    response = client.post(
        f"/api/v1/businesses/{biz}/modifier-groups", json=base, headers=owner
    )
    assert response.status_code == 201, response.text
    return response.json()


def _order(client, owner, biz, **body):
    base = {"customer_phone": "+923000000000", "fulfillment": "pickup", "items": []}
    base.update(body)
    return client.post(
        f"/api/v1/businesses/{biz}/orders", json=base, headers=owner
    )


# ── 1. Cross-tenant category references rejected ─────────────────
def test_product_rejects_foreign_category(client, business):
    owner, biz_a = business
    biz_b = client.post(
        "/api/v1/businesses", json={"name": "B", "type": "cafe"}, headers=owner
    ).json()["id"]
    foreign_cat = client.post(
        f"/api/v1/businesses/{biz_b}/categories", json={"name": "X"}, headers=owner
    ).json()["id"]

    # Create with another tenant's category → rejected.
    r = client.post(
        f"/api/v1/businesses/{biz_a}/products",
        json={"name": "P", "price": "10", "category_id": foreign_cat},
        headers=owner,
    )
    assert r.status_code == 400, r.text

    # Update to another tenant's category → rejected.
    pid = _product(client, owner, biz_a)["id"]
    r = client.patch(
        f"/api/v1/businesses/{biz_a}/products/{pid}",
        json={"category_id": foreign_cat},
        headers=owner,
    )
    assert r.status_code == 400, r.text


# ── 2. Negative totals / duplicate options rejected ─────────────
def test_negative_unit_price_rejected(client, business):
    owner, biz = business
    group = _modifier_group(
        client,
        owner,
        biz,
        name="Discount",
        items=[{"name": "Coupon", "price_delta": "-200"}],
    )
    prod = _product(
        client,
        owner,
        biz,
        price="100",
        modifier_groups=[
            {"modifier_group_id": group["id"], "max_select": 1}
        ],
    )
    coupon = group["items"][0]["id"]
    r = _order(
        client,
        owner,
        biz,
        items=[{"product_id": prod["id"], "quantity": 1, "option_item_ids": [coupon]}],
    )
    assert r.status_code == 400, r.text


def test_duplicate_option_ids_rejected(client, business):
    owner, biz = business
    group = _modifier_group(
        client,
        owner,
        biz,
        name="Add-ons",
        select_type="multi",
        items=[{"name": "Cheese", "price_delta": "50"}],
    )
    prod = _product(
        client,
        owner,
        biz,
        modifier_groups=[
            {"modifier_group_id": group["id"], "max_select": 5}
        ],
    )
    cheese = group["items"][0]["id"]
    r = _order(
        client,
        owner,
        biz,
        items=[
            {"product_id": prod["id"], "quantity": 1, "option_item_ids": [cheese, cheese]}
        ],
    )
    assert r.status_code == 400, r.text


# ── 3. Delivery-zone rules enforced ─────────────────────────────
def test_inactive_zone_rejected(client, business):
    owner, biz = business
    prod = _product(client, owner, biz, price="500")
    zone = client.post(
        f"/api/v1/businesses/{biz}/delivery-zones",
        json={"name": "Z", "fee": "100", "is_active": False},
        headers=owner,
    ).json()
    r = _order(
        client,
        owner,
        biz,
        fulfillment="delivery",
        zone_id=zone["id"],
        items=[{"product_id": prod["id"], "quantity": 1}],
    )
    assert r.status_code == 400, r.text


def test_zone_min_order_enforced(client, business):
    owner, biz = business
    prod = _product(client, owner, biz, price="50")
    zone = client.post(
        f"/api/v1/businesses/{biz}/delivery-zones",
        json={"name": "Z", "fee": "100", "min_order": "100"},
        headers=owner,
    ).json()
    r = _order(
        client,
        owner,
        biz,
        fulfillment="delivery",
        zone_id=zone["id"],
        items=[{"product_id": prod["id"], "quantity": 1}],  # subtotal 50 < 100
    )
    assert r.status_code == 400, r.text


# ── 4. Fulfillment-aware status machine ─────────────────────────
def _advance(client, owner, biz, oid, status):
    return client.patch(
        f"/api/v1/businesses/{biz}/orders/{oid}/status",
        json={"status": status},
        headers=owner,
    )


def test_pickup_cannot_go_out_for_delivery(client, business):
    owner, biz = business
    prod = _product(client, owner, biz)
    oid = _order(
        client, owner, biz, items=[{"product_id": prod["id"], "quantity": 1}]
    ).json()["id"]
    assert _advance(client, owner, biz, oid, "accepted").status_code == 200
    assert _advance(client, owner, biz, oid, "preparing").status_code == 200
    # Pickup orders have no out_for_delivery step.
    assert _advance(client, owner, biz, oid, "out_for_delivery").status_code == 400
    assert _advance(client, owner, biz, oid, "ready").status_code == 200
    assert _advance(client, owner, biz, oid, "completed").status_code == 200


def test_delivery_dispatches_directly_from_preparing(client, business):
    owner, biz = business
    prod = _product(client, owner, biz)
    oid = _order(
        client,
        owner,
        biz,
        fulfillment="delivery",
        items=[{"product_id": prod["id"], "quantity": 1}],
    ).json()["id"]
    assert _advance(client, owner, biz, oid, "accepted").status_code == 200
    assert _advance(client, owner, biz, oid, "preparing").status_code == 200
    # Delivery has no 'ready' stage — that's pickup-only (design docs 07 §3).
    assert _advance(client, owner, biz, oid, "ready").status_code == 400
    # It dispatches directly from preparing ("Out for delivery").
    assert _advance(client, owner, biz, oid, "out_for_delivery").status_code == 200
    assert _advance(client, owner, biz, oid, "completed").status_code == 200


# ── 6. Audit identity derived from the authenticated user ───────
def test_changed_by_is_authenticated_user(client, business):
    owner, biz = business
    user_id = client.get("/api/v1/auth/me", headers=owner).json()["id"]
    prod = _product(client, owner, biz)
    oid = _order(
        client, owner, biz, items=[{"product_id": prod["id"], "quantity": 1}]
    ).json()["id"]
    # Spoofed changed_by in the body must be ignored.
    r = client.patch(
        f"/api/v1/businesses/{biz}/orders/{oid}/status",
        json={"status": "accepted", "changed_by": "attacker"},
        headers=owner,
    )
    assert r.status_code == 200, r.text
    history = r.json()["status_history"]
    accepted = next(h for h in history if h["status"] == "accepted")
    assert accepted["changed_by"] == user_id


# ── 7. Duplicate business-hour rows rejected ────────────────────
def test_duplicate_hours_rejected(client, business):
    owner, biz = business
    r = client.put(
        f"/api/v1/businesses/{biz}/hours",
        json={"hours": [{"day_of_week": 1}, {"day_of_week": 1}]},
        headers=owner,
    )
    assert r.status_code == 422, r.text


# ── 8. Pagination + input caps ──────────────────────────────────
def test_orders_pagination(client, business):
    owner, biz = business
    prod = _product(client, owner, biz)
    for _ in range(3):
        _order(client, owner, biz, items=[{"product_id": prod["id"], "quantity": 1}])
    page1 = client.get(
        f"/api/v1/businesses/{biz}/orders?limit=2&offset=0", headers=owner
    ).json()
    page2 = client.get(
        f"/api/v1/businesses/{biz}/orders?limit=2&offset=2", headers=owner
    ).json()
    assert len(page1) == 2 and len(page2) == 1


def test_order_quantity_capped(client, business):
    owner, biz = business
    prod = _product(client, owner, biz)
    r = _order(
        client, owner, biz, items=[{"product_id": prod["id"], "quantity": 1000}]
    )
    assert r.status_code == 422, r.text
