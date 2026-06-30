"""Per-run agent context — the tenant boundary, resolved server-side.

The agent is one long-lived compiled graph (works in LangGraph Studio, the worker, and
the CLI). The tenant is NOT baked into the graph; it arrives per run as context:

    agent.ainvoke(input, config, context={"business_id": ..., "customer_phone": ...})

Tools read these from ``runtime.context`` and open their own DB session — the LLM never
supplies a ``business_id``, so it cannot reach another tenant. In LangGraph Studio you set
these two fields in the run's context panel.
"""
from __future__ import annotations

from typing import Any
from typing_extensions import TypedDict


class AgentContext(TypedDict):
    business_id: str
    customer_phone: str


def ctx_dict(runtime: Any) -> dict[str, Any]:
    """Return the context as a dict whether it's a TypedDict or a dataclass."""
    c = runtime.context
    if isinstance(c, dict):
        return c
    return getattr(c, "__dict__", {}) or {}
