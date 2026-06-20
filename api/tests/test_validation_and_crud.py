"""Input validation, enum ('dropdown') values, CRUD lifecycle, and business rules."""
from __future__ import annotations


def _order(client, menu, **overrides):
    body = {
        "customer_phone": "+923000000000",
        "fulfillment": "pickup",
        "items": [
            {"product_id": menu["product"]["id"], "quantity": 1, "option_item_ids": [menu["regular"]]}
        ],
    }
    body.update(overrides)
    return client.post(
        f"/api/v1/businesses/{menu['biz']}/orders", json=body, headers=menu["owner"]
    )


# ── Enum / "dropdown" value validation (must 422) ───────────────
def test_invalid_business_type_rejected(client, owner):
    r = client.post("/api/v1/businesses", json={"name": "X", "type": "diner"}, headers=owner)
    assert r.status_code == 422


def test_invalid_business_status_rejected(client, business):
    owner, biz = business
    r = client.patch(f"/api/v1/businesses/{biz}", json={"status": "deleted"}, headers=owner)
    assert r.status_code == 422


def test_invalid_select_type_rejected(client, business):
    owner, biz = business
    r = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "P",
            "price": "10",
            "option_groups": [{"name": "Size", "select_type": "triple", "items": []}],
        },
        headers=owner,
    )
    assert r.status_code == 422


def test_invalid_fulfillment_rejected(client, menu):
    assert _order(client, menu, fulfillment="dine_in").status_code == 422


def test_invalid_payment_method_rejected(client, menu):
    assert _order(client, menu, payment_method="bitcoin").status_code == 422


def test_invalid_status_value_rejected(client, menu):
    order = _order(client, menu).json()
    r = client.patch(
        f"/api/v1/businesses/{menu['biz']}/orders/{order['id']}/status",
        json={"status": "flying"},
        headers=menu["owner"],
    )
    assert r.status_code == 422


# ── Required fields / value constraints (must 422) ──────────────
def test_business_requires_name(client, owner):
    assert client.post("/api/v1/businesses", json={"type": "cafe"}, headers=owner).status_code == 422


def test_product_price_must_be_nonnegative(client, business):
    owner, biz = business
    r = client.post(f"/api/v1/businesses/{biz}/products", json={"name": "P", "price": "-5"}, headers=owner)
    assert r.status_code == 422


def test_order_quantity_must_be_positive(client, menu):
    assert _order(
        client,
        menu,
        items=[{"product_id": menu["product"]["id"], "quantity": 0, "option_item_ids": [menu["regular"]]}],
    ).status_code == 422


def test_hours_day_of_week_out_of_range(client, business):
    owner, biz = business
    r = client.put(
        f"/api/v1/businesses/{biz}/hours",
        json={"hours": [{"day_of_week": 9, "is_closed": True}]},
        headers=owner,
    )
    assert r.status_code == 422


def test_register_bad_email_rejected(client):
    r = client.post("/api/v1/auth/register", json={"email": "notanemail", "password": "password123"})
    assert r.status_code == 422


# ── Business-rule validation (must 400) ─────────────────────────
def test_required_option_must_be_selected(client, menu):
    # No Size chosen for a required group → rejected
    r = _order(
        client, menu, items=[{"product_id": menu["product"]["id"], "quantity": 1}]
    )
    assert r.status_code == 400


def test_single_select_rejects_multiple(client, menu):
    r = _order(
        client,
        menu,
        items=[
            {
                "product_id": menu["product"]["id"],
                "quantity": 1,
                "option_item_ids": [menu["regular"], menu["large"]],
            }
        ],
    )
    assert r.status_code == 400


def test_order_rejects_product_from_other_business(client, menu):
    owner = menu["owner"]
    biz2 = client.post(
        "/api/v1/businesses", json={"name": "Other", "type": "cafe"}, headers=owner
    ).json()["id"]
    foreign = client.post(
        f"/api/v1/businesses/{biz2}/products", json={"name": "Tea", "price": "100"}, headers=owner
    ).json()
    r = _order(client, menu, items=[{"product_id": foreign["id"], "quantity": 1}])
    assert r.status_code == 400


def test_order_blocked_when_not_accepting(client, menu):
    client.patch(
        f"/api/v1/businesses/{menu['biz']}", json={"accepting_orders": False}, headers=menu["owner"]
    )
    assert _order(client, menu).status_code == 400


def test_delivery_blocked_when_not_offered(client, menu):
    client.patch(
        f"/api/v1/businesses/{menu['biz']}", json={"offers_delivery": False}, headers=menu["owner"]
    )
    assert _order(client, menu, fulfillment="delivery").status_code == 400


# ── CRUD lifecycle ──────────────────────────────────────────────
def test_category_crud(client, business):
    owner, biz = business
    cid = client.post(
        f"/api/v1/businesses/{biz}/categories", json={"name": "Drinks"}, headers=owner
    ).json()["id"]
    patched = client.patch(
        f"/api/v1/businesses/{biz}/categories/{cid}", json={"name": "Beverages"}, headers=owner
    )
    assert patched.json()["name"] == "Beverages"
    assert client.delete(f"/api/v1/businesses/{biz}/categories/{cid}", headers=owner).status_code == 204
    names = [c["name"] for c in client.get(f"/api/v1/businesses/{biz}/categories", headers=owner).json()]
    assert "Beverages" not in names


def test_product_modifier_replace(client, menu):
    pid, biz, owner = menu["product"]["id"], menu["biz"], menu["owner"]
    r = client.patch(
        f"/api/v1/businesses/{biz}/products/{pid}",
        json={
            "option_groups": [
                {"name": "Spice", "select_type": "single", "items": [{"name": "Mild"}, {"name": "Hot"}]}
            ]
        },
        headers=owner,
    )
    assert r.status_code == 200
    groups = r.json()["option_groups"]
    assert len(groups) == 1 and groups[0]["name"] == "Spice" and len(groups[0]["items"]) == 2


def test_zone_crud(client, business):
    owner, biz = business
    zid = client.post(
        f"/api/v1/businesses/{biz}/delivery-zones", json={"name": "Gulshan", "fee": "150"}, headers=owner
    ).json()["id"]
    assert client.patch(
        f"/api/v1/businesses/{biz}/delivery-zones/{zid}", json={"fee": "200"}, headers=owner
    ).status_code == 200
    assert client.delete(
        f"/api/v1/businesses/{biz}/delivery-zones/{zid}", headers=owner
    ).status_code == 204


def test_hours_put_and_get(client, business):
    owner, biz = business
    client.put(
        f"/api/v1/businesses/{biz}/hours",
        json={"hours": [{"day_of_week": 1, "open_time": "09:00:00", "close_time": "22:00:00"}]},
        headers=owner,
    )
    rows = client.get(f"/api/v1/businesses/{biz}/hours", headers=owner).json()
    assert len(rows) == 1 and rows[0]["day_of_week"] == 1
