"""Per-tenant system prompt.

Read the prompt text in ``sections.py`` (each block is a named constant); ``builder.py``
fills the placeholders and stitches them together; ``hub.py`` is the LangSmith layer.

    from app.agent.prompts import BusinessBrief, render_system_prompt

- ``build_system_prompt`` — pure, in-code render (the canonical source of truth).
- ``render_system_prompt`` — same, but honours an optional LangSmith pull-override
  (``settings.agent_prompt_ref``). The agent runtime uses this one.
"""
from __future__ import annotations

from app.agent.prompts.builder import BusinessBrief, build_system_prompt, prompt_variables
from app.agent.prompts.hub import base_chat_prompt, push_prompt, render_system_prompt
from app.agent.prompts.summary import ORDERING_SUMMARY_PROMPT

__all__ = [
    "BusinessBrief",
    "build_system_prompt",
    "prompt_variables",
    "base_chat_prompt",
    "push_prompt",
    "render_system_prompt",
    "ORDERING_SUMMARY_PROMPT",
]
