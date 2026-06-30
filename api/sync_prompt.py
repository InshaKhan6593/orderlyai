"""Push the canonical agent prompt to LangSmith Prompt Hub.

    uv run python sync_prompt.py

Code stays the source of truth; this publishes a new commit of the in-code template
(``app.agent.prompts.base_chat_prompt``) to ``AGENT_PROMPT_NAME`` for versioning, the
Playground, and evals. Requires LANGSMITH_API_KEY in the environment / .env.
"""
from __future__ import annotations

from langsmith.utils import LangSmithConflictError

from app.agent.prompts import push_prompt
from app.core.config import settings


def main() -> None:
    if not settings.langsmith_api_key:
        raise SystemExit("LANGSMITH_API_KEY is not set; cannot push the prompt.")
    try:
        url = push_prompt()
    except LangSmithConflictError as exc:
        if "Nothing to commit" not in str(exc):
            raise
        print(f"Prompt '{settings.agent_prompt_name}' is already current in LangSmith.")
        return
    print(f"Pushed prompt '{settings.agent_prompt_name}' to LangSmith.")
    print(f"View / edit: {url}")


if __name__ == "__main__":
    main()
