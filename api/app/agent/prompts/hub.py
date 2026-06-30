"""LangSmith Prompt Hub integration — code is the source of truth.

``base_chat_prompt()`` is the canonical agent prompt as a LangChain ``ChatPromptTemplate``
(one system message built from the same ``SYSTEM_SCAFFOLD`` rendered locally). ``sync_prompt.py``
pushes it to LangSmith for versioning, the Playground, and evals.

At runtime ``render_system_prompt(brief)`` uses the in-code template by default. If
``settings.agent_prompt_ref`` is set it pulls that ref from LangSmith once (cached for the
process) and renders it with the same per-tenant variables — falling back to the in-code
template on any error, so a Hub/network problem can never break a live conversation.

The ``langsmith`` client is imported lazily inside functions so importing this module (and
running prompt tests) never needs network or credentials.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate

from app.agent.prompts.builder import (
    SYSTEM_SCAFFOLD,
    BusinessBrief,
    build_system_prompt,
    prompt_variables,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


def _client():
    """LangSmith client using app settings loaded from .env.

    LangSmith's Client reads process env by default, but our local commands load
    credentials through pydantic-settings. Passing them explicitly keeps
    ``sync_prompt.py`` and runtime prompt pulls consistent.
    """
    from langsmith import Client

    return Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint)


def base_chat_prompt() -> ChatPromptTemplate:
    """The canonical prompt as a single-system-message ChatPromptTemplate (f-string format).

    This is the object pushed to LangSmith; its placeholders are filled per tenant by
    ``prompt_variables``."""
    return ChatPromptTemplate.from_messages([("system", SYSTEM_SCAFFOLD)])


@lru_cache(maxsize=1)
def _pulled_prompt(ref: str) -> ChatPromptTemplate:
    """Fetch a prompt ref from LangSmith. Cached for the process (one network call)."""
    return _client().pull_prompt(ref)


def render_system_prompt(brief: BusinessBrief) -> str:
    """Per-tenant system prompt string for the agent's ``system_prompt`` override.

    In-code template unless ``agent_prompt_ref`` is set, in which case the pulled (cached)
    template is used, with the in-code template as the guaranteed fallback."""
    ref = settings.agent_prompt_ref
    if not ref:
        return build_system_prompt(brief)
    try:
        template = _pulled_prompt(ref)
        messages = template.format_messages(**prompt_variables(brief))
        return "\n\n".join(str(m.content) for m in messages)
    except Exception:  # noqa: BLE001 — a prompt fetch must never break a conversation.
        logger.warning(
            "Pull of LangSmith prompt %r failed; using in-code template.", ref, exc_info=True
        )
        return build_system_prompt(brief)


def push_prompt() -> str:
    """Publish the canonical in-code template to LangSmith (creates a new commit).

    Returns the prompt's UI URL. Requires ``LANGSMITH_API_KEY`` in app settings."""
    return _client().push_prompt(settings.agent_prompt_name, object=base_chat_prompt())
