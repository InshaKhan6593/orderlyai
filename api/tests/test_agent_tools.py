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


def test_get_menu_category_arg_is_optional_and_described():
    # `category` is a real, functional filter now (case-insensitive), and described for the model.
    args = _by_name("get_menu").args
    assert "category" in args
    assert args["category"].get("description")
