"""The agent tools expose detailed, model-facing descriptions and never leak the injected
``ToolRuntime`` into the schema the model sees."""
from __future__ import annotations

from app.agent.tools import TOOLS


def _by_name(name: str):
    return next(t for t in TOOLS if t.name == name)


def test_every_tool_has_a_substantive_description():
    for t in TOOLS:
        assert t.description and len(t.description.strip()) >= 20, t.name


def test_injected_runtime_not_in_model_schema():
    # `runtime: ToolRuntime` is injected by the agent, never chosen by the model.
    for t in TOOLS:
        assert "runtime" not in (t.args or {}), t.name


def test_add_to_cart_args_are_described():
    args = _by_name("add_to_cart").args
    assert set(args) == {"product_id", "quantity", "option_item_ids"}
    assert all(args[a].get("description") for a in args)


def test_add_to_cart_option_ids_description_warns_against_stringifying():
    # The arg description must steer the model to a real JSON array, since a stringified
    # array is the exact malformation that previously looped the turn.
    desc = _by_name("add_to_cart").args["option_item_ids"]["description"].lower()
    assert "array" in desc
    assert "not send" in desc or "do not" in desc


def test_add_to_cart_coerces_mis_encoded_option_item_ids():
    # Belt-and-suspenders: even if a weak model sends the list as a string, validation
    # repairs the recoverable shapes instead of rejecting (which would loop).
    schema = _by_name("add_to_cart").args_schema

    def opts(value):
        return schema(
            product_id="453aa17e-9664-4dfd-a466-00d827638469",
            quantity=1,
            option_item_ids=value,
        ).option_item_ids

    one = "692c124c-c478-4a75-bae4-d01c59c65428"
    assert opts([one]) == [one]              # correct shape passes through
    assert opts(f'["{one}"]') == [one]       # stringified JSON array → parsed
    assert opts("a-id,b-id") == ["a-id", "b-id"]  # comma-joined → split
    assert opts("just-one-id") == ["just-one-id"]  # single bare id → wrapped
    assert opts("") == []                    # empty string → empty list
    assert opts(None) is None                # omitted stays omitted


def test_get_menu_category_arg_is_optional_and_described():
    # `category` is a real, functional filter now (case-insensitive), and described for the model.
    args = _by_name("get_menu").args
    assert "category" in args
    assert args["category"].get("description")


def test_remove_from_cart_tool_dropped_as_redundant():
    # Removal is folded into update_cart_quantity(line, 0); the separate tool is gone so the
    # model has one fewer redundant choice.
    names = {t.name for t in TOOLS}
    assert "remove_from_cart" not in names
    assert "update_cart_quantity" in names


def test_fulfillment_and_zone_tools_are_internal_not_model_tools():
    # Checkout is deterministic: the model no longer chooses delivery/pickup or resolves the
    # delivery zone — that's done in code (place_order + run_turn). Those tools must be gone.
    names = {t.name for t in TOOLS}
    assert "set_fulfillment" not in names
    assert "check_delivery_area" not in names
    # place_order is the single checkout trigger; update_detail relays a saved-detail change.
    assert "place_order" in names
    assert "update_detail" in names


def test_update_detail_args_described():
    args = _by_name("update_detail").args
    assert set(args) == {"field", "value"}
    assert all(args[a].get("description") for a in args)
