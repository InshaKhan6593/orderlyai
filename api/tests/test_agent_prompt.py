"""Per-tenant system prompt: the upsell toggle and open/accepting state shape the prompt."""
from __future__ import annotations

from app.agent.prompts import (
    BusinessBrief,
    base_chat_prompt,
    build_system_prompt,
    customer_block,
    prompt_variables,
    render_system_prompt,
)


def _brief(**over) -> BusinessBrief:
    base = dict(
        name="Mario's Pizza",
        business_type="restaurant",
        currency="PKR",
        hours_summary="Mon: 10:00–22:00",
        is_open=True,
        accepting_orders=True,
        offers_delivery=True,
        offers_pickup=True,
        min_order_amount="500",
        packaging_fee="20",
        upsell_enabled=True,
        greeting="Welcome to Mario's!",
        extra_instructions=None,
        handoff_phone=None,
    )
    base.update(over)
    return BusinessBrief(**base)


def test_prompt_includes_identity_and_currency():
    p = build_system_prompt(_brief())
    assert "Mario's Pizza" in p
    assert "PKR" in p
    assert "English only" in p  # Meta en-only rule


def test_upsell_on_vs_off():
    on = build_system_prompt(_brief(upsell_enabled=True))
    off = build_system_prompt(_brief(upsell_enabled=False))
    assert "suggest ONE relevant add-on" in on
    assert "Do NOT upsell" in off


def test_not_accepting_orders_warns_model():
    p = build_system_prompt(_brief(accepting_orders=False))
    assert "NOT accepting orders" in p


def test_closed_state_noted():
    p = build_system_prompt(_brief(is_open=False, accepting_orders=True))
    assert "CLOSED" in p


def test_read_before_write_rule_present():
    p = build_system_prompt(_brief())
    # The prompt must state the order can't be placed before pricing + confirm.
    assert "place_order" in p
    assert "Confirm" in p


def test_tags_vs_facts_rule_present():
    p = build_system_prompt(_brief())
    # Owner tags are framed as labels/recommendations, never as hard sales data.
    assert "bestseller" in p
    assert "get_popular_items" not in p  # order-history popularity tool was removed
    assert "never guess" in p.lower()


def test_langsmith_template_matches_local_render():
    # The template pushed to LangSmith must render identically to the in-code build, and its
    # placeholders must be exactly the per-tenant variables we fill — otherwise a pulled
    # prompt would fail to format.
    b = _brief()
    tmpl = base_chat_prompt()
    assert sorted(tmpl.input_variables) == sorted(prompt_variables(b))
    assert tmpl.format_messages(**prompt_variables(b))[0].content == build_system_prompt(b)


def test_render_system_prompt_uses_local_template_without_ref():
    # With no AGENT_PROMPT_REF configured, runtime rendering equals the in-code build.
    b = _brief()
    assert render_system_prompt(b) == build_system_prompt(b)


def test_categories_listed_in_prompt():
    # The agent must see the business's real categories so it maps requests to them.
    p = build_system_prompt(_brief(categories_summary="Burgers, Pizza, Salads"))
    assert "Burgers, Pizza, Salads" in p
    assert "category" in p.lower()


def test_delivery_areas_listed_in_prompt():
    # Regression: the agent could not answer "where do you deliver?" because the zones were never
    # given to it. Now the active areas are inlined so it can reason and tell the customer.
    p = build_system_prompt(_brief(delivery_zones_summary="Gulberg (80 PKR), DHA (120 PKR)"))
    assert "Gulberg (80 PKR)" in p
    assert "DHA (120 PKR)" in p
    assert "Delivery areas" in p
    # ...and it's told to answer coverage questions from these facts (not via place_order).
    assert "whether you cover their area" in p


def test_delivery_areas_hint_when_no_zones_configured():
    # Delivery offered but no zones set → tell the agent to confirm the address at checkout.
    p = build_system_prompt(_brief(offers_delivery=True, delivery_zones_summary=""))
    assert "confirm the customer's address at checkout" in p


def test_no_delivery_area_line_for_pickup_only_business():
    # A pickup-only business must not advertise delivery areas, even if stale data is passed.
    p = build_system_prompt(
        _brief(offers_delivery=False, offers_pickup=True,
               delivery_zones_summary="Gulberg (80 PKR)")
    )
    assert "Gulberg (80 PKR)" not in p


def test_menu_not_inlined_points_to_get_menu():
    # With no inlined menu (large menu / unknown size), the prompt tells the model to fetch it.
    p = build_system_prompt(_brief())  # menu_index defaults to None
    assert "MENU ACCESS" in p
    assert "call get_menu" in p


def test_menu_inlined_when_provided_and_blocks_refetch():
    # A small menu is inlined verbatim, and the model is told NOT to re-fetch it.
    menu = "Available menu:\n\nMains:\n  - Burger - 850 PKR [id: abc-123]"
    p = build_system_prompt(_brief(menu_index=menu))
    assert "CURRENT MENU" in p
    assert "do NOT call get_menu" in p
    assert "Burger - 850 PKR [id: abc-123]" in p


def test_whatsapp_output_rules_present():
    # WhatsApp-compatibility rules the model must follow: single-asterisk bold, product: row
    # ids, and the 10-row list cap.
    p = build_system_prompt(_brief())
    assert "*single asterisks*" in p
    assert "product:" in p
    assert "at most 10 rows" in p
    assert "max 72 chars" in p
    assert "max 20 chars" in p


def test_prompt_encourages_using_bold_for_key_details():
    # Beyond explaining the syntax, the prompt tells the agent to actually USE bold for what a
    # customer scans for (item names, prices, total) and to hug the markers to the text.
    p = build_system_prompt(_brief())
    assert "stand out with *bold*" in p
    assert "hug" in p.lower()


def test_prompt_blocks_ambiguous_full_menu_dump():
    p = build_system_prompt(_brief())
    assert "never use a list to show every product across the whole menu" in p.lower()
    assert "full-menu request" in p.lower()
    # A full-menu request becomes a tappable CATEGORY dropdown (or text if too many categories),
    # never a product dump.
    assert "CATEGORY list" in p


def test_prompt_restricts_interactive_ids_to_worker_contract():
    p = build_system_prompt(_brief())
    assert "Do NOT invent button ids" in p
    assert "confirm_order" in p
    assert "edit_cart" in p
    assert "cancel_order" in p
    # Row ids follow the worker contract: products are "product:<id>", categories "category:<name>".
    assert 'product row id MUST be "product:"' in p
    assert 'category row id MUST be "category:"' in p


def test_prompt_requires_single_valid_structured_reply():
    p = build_system_prompt(_brief())
    assert "exactly one AgentReply tool call" in p
    assert "valid JSON" in p
    assert "No extra text outside AgentReply" in p


def test_prompt_offers_saved_delivery_address():
    # The cart flow must tell the agent to offer a returning customer's saved address.
    p = build_system_prompt(_brief())
    assert "RETURNING CUSTOMER" in p
    assert "saved delivery address" in p.lower()


def test_customer_block_personalises_with_saved_details():
    block = customer_block(name="Ada", default_address="12 Park Lane", order_count=3)
    assert block is not None
    assert "RETURNING CUSTOMER" in block
    assert "Ada" in block
    assert "12 Park Lane" in block
    assert "ordered from you 3" in block


def test_customer_block_partial_profile_only_shows_known_fields():
    block = customer_block(name="Ada", default_address=None, order_count=0)
    assert block is not None and "Ada" in block
    assert "delivery address" not in block.lower()  # nothing saved → not mentioned


def test_customer_block_empty_profile_is_none():
    # A first-time sender with no saved details adds no personalisation block at all.
    assert customer_block(name=None, default_address=None, order_count=0) is None


def test_prompt_describes_reordering():
    # The agent must know how to show past orders (with items) and repeat one via the reorder tool.
    p = build_system_prompt(_brief())
    assert "PAST ORDERS & REORDERING" in p
    assert "reorder" in p
    assert "get_order_status" in p
    # The reorder button id contract: "reorder:" + the order number.
    assert "reorder:" in p


def test_prompt_sections_wrapped_in_xml_tags():
    # Sections are delimited with semantic XML tags (Anthropic-recommended structure) so the
    # model parses instruction boundaries reliably.
    p = build_system_prompt(_brief())
    for tag in ("role", "menu", "how_you_work", "ordering_flow", "whatsapp_output"):
        assert f"<{tag}>" in p and f"</{tag}>" in p


def test_prompt_explains_each_whatsapp_message_kind():
    # The output rules must teach WHEN to use each WhatsApp message kind, with the dropdown
    # (category list) and the specific-dish image behaviour the owner asked for.
    p = build_system_prompt(_brief())
    assert "CHOOSE THE MESSAGE KIND" in p
    assert "CATEGORY list" in p and "PRODUCT list" in p
    assert "IMAGE" in p
    assert "category:" in p  # category-row id contract for the dropdown
    # Buttons stay reserved (confirm flow + the single reorder offer), not for browsing.
    assert "almost never yours to send" in p


def test_returning_customer_block_wrapped_in_xml_tag():
    block = customer_block(name="Ada", default_address="12 Park Lane", order_count=2)
    assert block is not None
    assert block.startswith("<returning_customer>")
    assert block.endswith("</returning_customer>")
    assert "RETURNING CUSTOMER" in block


def test_prompt_describes_automatic_confirm_buttons():
    # Regression: the confirm buttons are rendered by the SYSTEM (run_turn), not hand-built by
    # the model — and the model must never reference a button that isn't in the reply (the old
    # dead-end where it sent text "tap the Confirm button above" but no actual button). A typed
    # confirmation is not a tap.
    p = build_system_prompt(_brief())
    assert "SYSTEM adds them automatically" in p
    assert "never tell the customer to tap a button that is not in the reply" in p
    assert "is NOT a tap" in p
