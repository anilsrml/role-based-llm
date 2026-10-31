from types import SimpleNamespace

import pytest

from rolchat import tools
from rolchat.policy import allowed_tools
from rolchat.tools import TOOLS, Deps


@pytest.fixture
def ctx(reader_engine, seeded):
    # Tools only read ctx.deps, so a plain namespace stands in for pydantic_ai's RunContext.
    def make(role):
        return SimpleNamespace(deps=Deps(role=role, engine=reader_engine))
    return make


def test_every_tool_has_a_policy_entry():
    assert {f.__name__ for f in TOOLS} == allowed_tools("patron")


@pytest.mark.parametrize("tool", TOOLS, ids=lambda f: f.__name__)
def test_patron_can_call_every_tool_and_gets_rows(ctx, tool):
    assert tool(ctx("patron"))


@pytest.mark.parametrize("tool", TOOLS, ids=lambda f: f.__name__)
def test_tool_refuses_role_without_permission(ctx, tool):
    # Second layer: even if the model somehow calls a hidden tool, the tool itself refuses.
    roles_without = [r for r in ("isci", "sekreter") if tool.__name__ not in allowed_tools(r)]
    for role in roles_without:
        with pytest.raises(PermissionError):
            tool(ctx(role))


def test_find_employee_matches_part_of_name_case_insensitively(ctx):
    c = ctx("sekreter")
    someone = tools.find_employee(c)[0]["full_name"]
    part = someone.split()[0][1:].upper()
    assert any(r["full_name"] == someone for r in tools.find_employee(c, name=part))
