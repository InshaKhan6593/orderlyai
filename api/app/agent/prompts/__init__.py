"""Per-tenant system prompt.

Read the prompt text in ``sections.py`` (each block is a named constant); ``builder.py``
fills the placeholders and stitches them together. Public API is unchanged:

    from app.agent.prompts import BusinessBrief, build_system_prompt
"""
from __future__ import annotations

from app.agent.prompts.builder import BusinessBrief, build_system_prompt

__all__ = ["BusinessBrief", "build_system_prompt"]
