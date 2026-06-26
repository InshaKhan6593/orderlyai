"""Agent runtime behavior that is independent of the real LLM."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.runtime import run_turn
from app.agent.schemas import AgentReply, TextMessage


class _FakeAgent:
    def __init__(self, result: dict):
        self.result = result

    async def aget_state(self, config):
        return SimpleNamespace(values={})

    async def ainvoke(self, *args, **kwargs):
        return self.result


@pytest.mark.asyncio
async def test_run_turn_rejects_stale_structured_response_after_latest_user_message():
    stale = AgentReply(messages=[TextMessage(kind="text", body="old greeting")])
    agent = _FakeAgent(
        {
            "messages": [
                {"type": "human", "content": "Hi"},
                {
                    "type": "tool",
                    "name": "AgentReply",
                    "content": "Returning structured response: old greeting",
                },
                {"type": "human", "content": "your menu?"},
                {
                    "type": "tool",
                    "name": "AgentReply",
                    "content": "Error: Failed to parse structured output for tool 'AgentReply'",
                },
            ],
            "structured_response": stale,
        }
    )

    with pytest.raises(RuntimeError, match="latest turn"):
        await run_turn(
            agent,
            business_id="a5bda699-9834-481e-ba99-b0d39161fac4",
            customer_phone="923241452724",
            thread_id="a5bda699-9834-481e-ba99-b0d39161fac4:923241452724",
            text="your menu?",
        )


@pytest.mark.asyncio
async def test_run_turn_returns_structured_response_from_latest_user_message():
    reply = AgentReply(messages=[TextMessage(kind="text", body="current menu")])
    agent = _FakeAgent(
        {
            "messages": [
                {"type": "human", "content": "your menu?"},
                {
                    "type": "tool",
                    "name": "AgentReply",
                    "content": "Returning structured response: current menu",
                },
            ],
            "structured_response": reply,
        }
    )

    result = await run_turn(
        agent,
        business_id="a5bda699-9834-481e-ba99-b0d39161fac4",
        customer_phone="923241452724",
        thread_id="a5bda699-9834-481e-ba99-b0d39161fac4:923241452724",
        text="your menu?",
    )

    assert result == reply
