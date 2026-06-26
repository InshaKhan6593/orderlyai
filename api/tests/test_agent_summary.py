"""The ordering-domain summarization prompt: format contract + domain coverage.

SummarizationMiddleware renders this with ``prompt.format(messages=...)``. A stray ``{``/``}``
or a missing ``{messages}`` would crash summarization mid-conversation, so the contract is
worth a unit test.
"""
from __future__ import annotations

import string

from app.agent.prompts import ORDERING_SUMMARY_PROMPT


def test_summary_prompt_format_contract():
    # `{messages}` must be the ONLY replacement field (anything else would raise at runtime).
    fields = [
        name
        for _, name, _, _ in string.Formatter().parse(ORDERING_SUMMARY_PROMPT)
        if name is not None
    ]
    assert fields == ["messages"]
    # And it renders exactly as the middleware calls it.
    rendered = ORDERING_SUMMARY_PROMPT.format(messages="USER: hi\nASSISTANT: welcome")
    assert "USER: hi" in rendered
    assert "{messages}" not in rendered


def test_summary_prompt_is_ordering_domain_and_production_grade():
    p = ORDERING_SUMMARY_PROMPT
    # Not the generic coding-agent default.
    assert "ARTIFACTS" not in p and "file paths" not in p
    # Domain headings the assistant relies on.
    for heading in ("CUSTOMER", "ORDER", "STATE"):
        assert heading in p
    # Key production guarantees: exact preservation, carry-forward across repeated summarization,
    # conversation-not-plumbing, and deferring the live cart to view_cart.
    assert "EXACTLY" in p
    assert "CARRY" in p
    assert "view_cart" in p
