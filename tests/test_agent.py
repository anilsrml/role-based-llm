from datetime import date

import pytest
from pydantic_ai.models.test import TestModel

from rolchat.agent import agent
from rolchat.policy import allowed_tools
from rolchat.tools import Deps


@pytest.fixture
def deps(reader_engine, seeded):
    def make(role):
        return Deps(role=role, engine=reader_engine)
    return make


@pytest.mark.parametrize("role", ["isci", "sekreter", "patron"])
def test_model_is_offered_only_the_roles_tools(deps, role):
    model = TestModel(call_tools=[])
    with agent.override(model=model):
        agent.run_sync("merhaba", deps=deps(role))

    offered = {t.name for t in model.last_model_request_parameters.function_tools}
    assert offered == allowed_tools(role)


@pytest.mark.parametrize("role", ["isci", "sekreter", "patron"])
def test_model_can_call_every_offered_tool(deps, role):
    # TestModel calls every tool it is offered; none may hit the second-layer refusal.
    with agent.override(model=TestModel()):
        result = agent.run_sync("her şeyi göster", deps=deps(role))
    assert result.output


def test_instructions_carry_todays_date_and_the_refusal_sentence(deps):
    with agent.override(model=TestModel(call_tools=[])):
        result = agent.run_sync("merhaba", deps=deps("isci"))

    instructions = result.all_messages()[0].instructions
    assert date.today().isoformat() in instructions
    assert "Bu konuda bilgim yok." in instructions


def test_tool_schema_caps_row_counts(deps):
    # Unbounded consumption: the model cannot ask for 100000 rows.
    model = TestModel(call_tools=[])
    with agent.override(model=model):
        agent.run_sync("merhaba", deps=deps("patron"))

    params = {t.name: t.parameters_json_schema["properties"] for t in model.last_model_request_parameters.function_tools}
    assert params["list_announcements"]["limit"] | {"minimum": 1, "maximum": 50} == params["list_announcements"]["limit"]
    assert params["get_financial_summary"]["months"] | {"minimum": 1, "maximum": 24} == params["get_financial_summary"]["months"]
