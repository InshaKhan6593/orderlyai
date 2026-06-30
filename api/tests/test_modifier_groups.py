"""Reusable modifier-group CRUD, assignment, pricing, and tenant isolation."""
from __future__ import annotations

from decimal import Decimal


def _group(client, owner, biz, *, name="Size", large_delta="250"):
    response = client.post(
        f"/api/v1/businesses/{biz}/modifier-groups",
        json={
            "name": name,
            "display_name": "Size" if "Size" in name else name,
            "select_type": "single",
            "is_template": True,
            "items": [
                {"name": "Regular", "price_delta": "0", "is_default": True},
                {"name": "Large", "price_delta": large_delta},
            ],
        },
        headers=owner,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _product(client, owner, biz, name, group_id=None, *, required=False):
    assignments = []
    if group_id is not None:
        assignments.append(
            {
                "modifier_group_id": group_id,
                "is_required": required,
                "min_select": 1 if required else 0,
                "max_select": 1,
            }
        )
    response = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={"name": name, "price": "850", "modifier_groups": assignments},
        headers=owner,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_group_can_be_reused_by_multiple_products_with_assignment_rules(client, business):
    owner, biz = business
    group = _group(client, owner, biz)
    pimento = _product(client, owner, biz, "Pimento", group["id"], required=True)
    classic = _product(client, owner, biz, "Classic", group["id"], required=False)

    assert pimento["modifier_groups"][0]["modifier_group_id"] == group["id"]
    assert classic["modifier_groups"][0]["modifier_group_id"] == group["id"]
    assert pimento["modifier_groups"][0]["is_required"] is True
    assert classic["modifier_groups"][0]["is_required"] is False

    large = next(item for item in group["items"] if item["name"] == "Large")
    response = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "+923001111111",
            "fulfillment": "pickup",
            "items": [
                {
                    "product_id": classic["id"],
                    "quantity": 2,
                    "option_item_ids": [large["id"]],
                }
            ],
        },
        headers=owner,
    )
    assert response.status_code == 201, response.text
    assert Decimal(str(response.json()["total"])) == Decimal("2200")


def test_modifier_option_description_flows_to_products_and_order_snapshots(
    client, business
):
    owner, biz = business
    response = client.post(
        f"/api/v1/businesses/{biz}/modifier-groups",
        json={
            "name": "Pizza sizes",
            "display_name": "Size",
            "select_type": "single",
            "items": [
                {
                    "name": "Small",
                    "description": "13-inch diameter, serves 1-2",
                    "price_delta": "0",
                    "is_default": True,
                }
            ],
        },
        headers=owner,
    )
    assert response.status_code == 201, response.text
    group = response.json()
    option = group["items"][0]
    assert option["description"] == "13-inch diameter, serves 1-2"

    product = _product(client, owner, biz, "Margherita", group["id"], required=True)
    assigned_option = product["modifier_groups"][0]["items"][0]
    assert assigned_option["description"] == "13-inch diameter, serves 1-2"

    order = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "+923001111121",
            "fulfillment": "pickup",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 1,
                    "option_item_ids": [option["id"]],
                }
            ],
        },
        headers=owner,
    )
    assert order.status_code == 201, order.text
    assert order.json()["items"][0]["options_json"][0]["description"] == (
        "13-inch diameter, serves 1-2"
    )


def test_shared_group_options_can_have_product_specific_prices(client, business):
    owner, biz = business
    group = _group(client, owner, biz, large_delta="0")
    large = next(item for item in group["items"] if item["name"] == "Large")

    burger = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Burger",
            "price": "850",
            "modifier_groups": [
                {
                    "modifier_group_id": group["id"],
                    "max_select": 1,
                    "items": [{"option_id": large["id"], "price_delta": "250"}],
                }
            ],
        },
        headers=owner,
    )
    assert burger.status_code == 201, burger.text

    pizza = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Pizza",
            "price": "850",
            "modifier_groups": [
                {
                    "modifier_group_id": group["id"],
                    "max_select": 1,
                    "items": [{"option_id": large["id"], "price_delta": "700"}],
                }
            ],
        },
        headers=owner,
    )
    assert pizza.status_code == 201, pizza.text

    burger_large = next(
        item
        for item in burger.json()["modifier_groups"][0]["items"]
        if item["id"] == large["id"]
    )
    pizza_large = next(
        item
        for item in pizza.json()["modifier_groups"][0]["items"]
        if item["id"] == large["id"]
    )
    assert Decimal(str(burger_large["price_delta"])) == Decimal("250")
    assert Decimal(str(pizza_large["price_delta"])) == Decimal("700")

    for product, expected_total in (
        (burger.json(), Decimal("1100")),
        (pizza.json(), Decimal("1550")),
    ):
        response = client.post(
            f"/api/v1/businesses/{biz}/orders",
            json={
                "customer_phone": "+923001111113",
                "fulfillment": "pickup",
                "items": [
                    {
                        "product_id": product["id"],
                        "quantity": 1,
                        "option_item_ids": [large["id"]],
                    }
                ],
            },
            headers=owner,
        )
        assert response.status_code == 201, response.text
        assert Decimal(str(response.json()["total"])) == expected_total


def test_product_rejects_price_override_for_option_outside_assigned_group(
    client, business
):
    owner, biz = business
    size = _group(client, owner, biz, name="Size")
    sauce = _group(client, owner, biz, name="Sauce", large_delta="50")
    sauce_option = sauce["items"][0]

    response = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Burger",
            "price": "850",
            "modifier_groups": [
                {
                    "modifier_group_id": size["id"],
                    "max_select": 1,
                    "items": [
                        {
                            "option_id": sauce_option["id"],
                            "price_delta": "150",
                        }
                    ],
                }
            ],
        },
        headers=owner,
    )
    assert response.status_code == 400, response.text


def test_updating_shared_group_is_visible_on_every_assigned_product(client, business):
    owner, biz = business
    group = _group(client, owner, biz)
    first = _product(client, owner, biz, "First", group["id"])
    second = _product(client, owner, biz, "Second", group["id"])

    response = client.patch(
        f"/api/v1/businesses/{biz}/modifier-groups/{group['id']}",
        json={"name": "Burger size"},
        headers=owner,
    )
    assert response.status_code == 200, response.text

    for product_id in (first["id"], second["id"]):
        product = client.get(
            f"/api/v1/businesses/{biz}/products/{product_id}", headers=owner
        ).json()
        assert product["modifier_groups"][0]["name"] == "Burger size"


def test_cross_tenant_modifier_group_cannot_be_attached(client, owner):
    biz_a = client.post(
        "/api/v1/businesses", json={"name": "A", "type": "restaurant"}, headers=owner
    ).json()["id"]
    biz_b = client.post(
        "/api/v1/businesses", json={"name": "B", "type": "restaurant"}, headers=owner
    ).json()["id"]
    foreign_group = _group(client, owner, biz_b)

    response = client.post(
        f"/api/v1/businesses/{biz_a}/products",
        json={
            "name": "Pimento",
            "price": "850",
            "modifier_groups": [{"modifier_group_id": foreign_group["id"]}],
        },
        headers=owner,
    )
    assert response.status_code == 400, response.text


def test_unassigned_option_is_rejected_even_within_same_business(client, business):
    owner, biz = business
    assigned = _group(client, owner, biz, name="Size")
    unassigned = _group(client, owner, biz, name="Sauce", large_delta="50")
    product = _product(client, owner, biz, "Pimento", assigned["id"])
    foreign_option = unassigned["items"][0]

    response = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "+923001111112",
            "fulfillment": "pickup",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 1,
                    "option_item_ids": [foreign_option["id"]],
                }
            ],
        },
        headers=owner,
    )
    assert response.status_code == 400, response.text


def test_modifier_group_library_is_tenant_guarded(client, business):
    _, biz = business
    outsider = client.post(
        "/api/v1/auth/register",
        json={"email": "modifier-outsider@example.com", "password": "password123"},
    ).json()
    headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    response = client.get(
        f"/api/v1/businesses/{biz}/modifier-groups", headers=headers
    )
    assert response.status_code == 403, response.text


def test_inline_group_is_dish_specific_and_hidden_from_template_library(
    client, business
):
    owner, biz = business
    response = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Cheese Burger",
            "price": "850",
            "modifier_groups": [
                {
                    "definition": {
                        "name": "Cheese Burger extras",
                        "display_name": "Extras",
                        "select_type": "multi",
                        "is_template": False,
                        "items": [
                            {
                                "name": "Extra cheese",
                                "price_delta": "100",
                                "is_default": False,
                            }
                        ],
                    },
                    "is_required": False,
                    "min_select": 0,
                    "max_select": 1,
                }
            ],
        },
        headers=owner,
    )

    assert response.status_code == 201, response.text
    assignment = response.json()["modifier_groups"][0]
    assert assignment["name"] == "Cheese Burger extras"
    assert assignment["display_name"] == "Extras"
    assert assignment["is_template"] is False
    assert assignment["items"][0]["name"] == "Extra cheese"

    library = client.get(
        f"/api/v1/businesses/{biz}/modifier-groups", headers=owner
    )
    assert library.status_code == 200, library.text
    assert library.json() == []


def test_inline_template_and_product_assignment_are_atomic(client, business):
    owner, biz = business
    response = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Invalid Burger",
            "price": "850",
            "modifier_groups": [
                {
                    "definition": {
                        "name": "Burger patties",
                        "display_name": "Patties",
                        "select_type": "single",
                        "is_template": True,
                        "items": [
                            {"name": "Single", "price_delta": "0"},
                            {"name": "Double", "price_delta": "200"},
                        ],
                    },
                    "min_select": 0,
                    "max_select": 2,
                }
            ],
        },
        headers=owner,
    )

    assert response.status_code == 400, response.text
    library = client.get(
        f"/api/v1/businesses/{biz}/modifier-groups", headers=owner
    )
    assert library.status_code == 200, library.text
    assert library.json() == []


def test_product_update_reuses_existing_assignment_without_unique_collision(
    client, business
):
    owner, biz = business
    size = _group(client, owner, biz)
    product = _product(client, owner, biz, "Pimento", size["id"])
    original_assignment_id = product["modifier_groups"][0]["assignment_id"]

    response = client.patch(
        f"/api/v1/businesses/{biz}/products/{product['id']}",
        json={
            "modifier_groups": [
                {
                    "modifier_group_id": size["id"],
                    "is_required": True,
                    "min_select": 1,
                    "max_select": 1,
                },
                {
                    "definition": {
                        "name": "Pimento extras",
                        "display_name": "Extras",
                        "select_type": "multi",
                        "is_template": False,
                        "items": [
                            {"name": "Extra cheese", "price_delta": "100"}
                        ],
                    },
                    "max_select": 1,
                },
            ]
        },
        headers=owner,
    )

    assert response.status_code == 200, response.text
    assignments = response.json()["modifier_groups"]
    retained = next(item for item in assignments if item["modifier_group_id"] == size["id"])
    assert retained["assignment_id"] == original_assignment_id
    assert retained["is_required"] is True
    assert {item["display_name"] for item in assignments} == {"Size", "Extras"}


def test_dish_assignment_controls_enabled_options_defaults_and_price(client, business):
    owner, biz = business
    patties = _group(client, owner, biz, name="Burger patties", large_delta="200")
    single = next(item for item in patties["items"] if item["name"] == "Regular")
    double = next(item for item in patties["items"] if item["name"] == "Large")

    response = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Double Burger",
            "price": "900",
            "modifier_groups": [
                {
                    "modifier_group_id": patties["id"],
                    "is_required": True,
                    "min_select": 1,
                    "max_select": 1,
                    "items": [
                        {
                            "option_id": double["id"],
                            "price_delta": "175",
                            "is_default": True,
                        }
                    ],
                }
            ],
        },
        headers=owner,
    )

    assert response.status_code == 201, response.text
    product = response.json()
    assert [item["id"] for item in product["modifier_groups"][0]["items"]] == [
        double["id"]
    ]
    assert product["modifier_groups"][0]["items"][0]["is_default"] is True
    assert Decimal(
        str(product["modifier_groups"][0]["items"][0]["price_delta"])
    ) == Decimal("175")

    rejected = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "+923001111119",
            "fulfillment": "pickup",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 1,
                    "option_item_ids": [single["id"]],
                }
            ],
        },
        headers=owner,
    )
    assert rejected.status_code == 400, rejected.text

    accepted = client.post(
        f"/api/v1/businesses/{biz}/orders",
        json={
            "customer_phone": "+923001111120",
            "fulfillment": "pickup",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 1,
                    "option_item_ids": [double["id"]],
                }
            ],
        },
        headers=owner,
    )
    assert accepted.status_code == 201, accepted.text
    assert Decimal(str(accepted.json()["total"])) == Decimal("1075")


def test_attached_template_cannot_be_deleted(client, business):
    owner, biz = business
    group = _group(client, owner, biz)
    _product(client, owner, biz, "Classic", group["id"])

    response = client.delete(
        f"/api/v1/businesses/{biz}/modifier-groups/{group['id']}", headers=owner
    )

    assert response.status_code == 400, response.text
    assert "attached" in response.json()["error"]["message"].lower()


def test_new_template_option_is_not_enabled_on_existing_dishes(client, business):
    owner, biz = business
    group = _group(client, owner, biz)
    product = _product(client, owner, biz, "Classic", group["id"])

    response = client.patch(
        f"/api/v1/businesses/{biz}/modifier-groups/{group['id']}",
        json={
            "items": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "price_delta": item["price_delta"],
                    "is_default": item["is_default"],
                    "sort_order": item["sort_order"],
                }
                for item in group["items"]
            ]
            + [{"name": "Family", "price_delta": "500", "sort_order": 2}]
        },
        headers=owner,
    )
    assert response.status_code == 200, response.text
    family = next(item for item in response.json()["items"] if item["name"] == "Family")

    saved_product = client.get(
        f"/api/v1/businesses/{biz}/products/{product['id']}", headers=owner
    )
    assert saved_product.status_code == 200, saved_product.text
    enabled_ids = {
        item["id"] for item in saved_product.json()["modifier_groups"][0]["items"]
    }
    assert family["id"] not in enabled_ids
    assert enabled_ids == {item["id"] for item in group["items"]}


def test_dish_specific_group_can_be_promoted_and_is_cleaned_with_product(
    client, business
):
    owner, biz = business
    product_response = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Cheese Burger",
            "price": "850",
            "modifier_groups": [
                {
                    "definition": {
                        "name": "Cheese Burger extras",
                        "display_name": "Extras",
                        "select_type": "multi",
                        "is_template": False,
                        "items": [{"name": "Extra cheese", "price_delta": "100"}],
                    },
                    "max_select": 1,
                }
            ],
        },
        headers=owner,
    )
    assert product_response.status_code == 201, product_response.text
    product = product_response.json()
    group_id = product["modifier_groups"][0]["modifier_group_id"]

    promoted = client.patch(
        f"/api/v1/businesses/{biz}/modifier-groups/{group_id}",
        json={"is_template": True},
        headers=owner,
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["is_template"] is True
    assert [
        item["id"]
        for item in client.get(
            f"/api/v1/businesses/{biz}/modifier-groups", headers=owner
        ).json()
    ] == [group_id]

    client.patch(
        f"/api/v1/businesses/{biz}/modifier-groups/{group_id}",
        json={"is_template": False},
        headers=owner,
    )
    deleted = client.delete(
        f"/api/v1/businesses/{biz}/products/{product['id']}", headers=owner
    )
    assert deleted.status_code == 204, deleted.text
    missing = client.get(
        f"/api/v1/businesses/{biz}/modifier-groups/{group_id}", headers=owner
    )
    assert missing.status_code == 404, missing.text


def test_assignment_rejects_zero_enabled_options_and_multiple_single_defaults(
    client, business
):
    owner, biz = business
    group = _group(client, owner, biz)

    empty = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "No Sizes",
            "price": "850",
            "modifier_groups": [
                {
                    "modifier_group_id": group["id"],
                    "max_select": 1,
                    "items": [],
                }
            ],
        },
        headers=owner,
    )
    assert empty.status_code == 400, empty.text

    duplicate_defaults = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Two Defaults",
            "price": "850",
            "modifier_groups": [
                {
                    "modifier_group_id": group["id"],
                    "max_select": 1,
                    "items": [
                        {"option_id": item["id"], "is_default": True}
                        for item in group["items"]
                    ],
                }
            ],
        },
        headers=owner,
    )
    assert duplicate_defaults.status_code == 400, duplicate_defaults.text


def test_dish_specific_group_cannot_be_attached_to_another_dish(client, business):
    owner, biz = business
    first = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "First Burger",
            "price": "850",
            "modifier_groups": [
                {
                    "definition": {
                        "name": "First Burger extras",
                        "display_name": "Extras",
                        "select_type": "multi",
                        "is_template": False,
                        "items": [{"name": "Extra cheese", "price_delta": "100"}],
                    },
                    "max_select": 1,
                }
            ],
        },
        headers=owner,
    )
    assert first.status_code == 201, first.text
    group_id = first.json()["modifier_groups"][0]["modifier_group_id"]

    second = client.post(
        f"/api/v1/businesses/{biz}/products",
        json={
            "name": "Second Burger",
            "price": "900",
            "modifier_groups": [
                {"modifier_group_id": group_id, "max_select": 1}
            ],
        },
        headers=owner,
    )
    assert second.status_code == 400, second.text
    assert "dish-specific" in second.json()["error"]["message"].lower()
