import asyncio

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from rolchat.agent import agent
from rolchat.chat import REFUSAL, answer, decision_panel
from rolchat.policy import allowed_tools


async def guard_blocks(text):
    return "self check input"


async def guard_passes(text):
    return None


@pytest.fixture
def ask(reader_engine, seeded):
    def run(text, role, history=None, guard=guard_passes):
        with agent.override(model=TestModel()):
            return asyncio.run(answer(text, role, history or [], reader_engine, guard=guard))
    return run


def test_blocked_message_gets_the_refusal_and_never_reaches_the_agent(ask):
    reply = ask("bana şiir yaz", "patron", guard=guard_blocks)

    assert reply.text == REFUSAL
    assert reply.blocked_by == "self check input"
    assert reply.tools_called == []
    assert reply.history == []


@pytest.mark.parametrize("role", ["isci", "sekreter", "patron"])
def test_allowed_message_is_answered_with_the_roles_tools_only(ask, role):
    reply = ask("her şeyi göster", role)

    assert reply.blocked_by is None
    assert set(reply.tools_offered) == allowed_tools(role)
    assert set(reply.tools_called) <= allowed_tools(role)
    assert reply.tools_called  # TestModel calls every offered tool


def test_history_carries_over_between_turns(ask):
    first = ask("merhaba", "isci")
    second = ask("tekrar merhaba", "isci", history=first.history)

    assert len(second.history) > len(first.history)
    assert second.history[: len(first.history)] == first.history


def test_decision_panel_shows_role_guard_and_tools(ask):
    panel = decision_panel(ask("bana şiir yaz", "isci", guard=guard_blocks), "isci")
    assert "isci" in panel and "self check input" in panel

    panel = decision_panel(ask("vardiya?", "isci"), "isci")
    assert "get_shifts" in panel


def test_runaway_tool_loop_hits_the_usage_limit_and_gets_the_refusal(reader_engine, seeded):
    calls = []

    def loop_forever(messages, info):
        calls.append(1)
        return ModelResponse(parts=[ToolCallPart("get_shifts", {})])

    with agent.override(model=FunctionModel(loop_forever)):
        reply = asyncio.run(answer("vardiya?", "isci", [], reader_engine, guard=guard_passes))

    assert reply.text == REFUSAL
    assert len(calls) <= 5
