import pytest

from rolchat.policy import allowed_tools, can_use

LEVEL_1 = {"list_announcements", "get_shifts"}
LEVEL_2 = {"find_employee", "list_leaves", "list_meetings"}
LEVEL_3 = {"get_salaries", "get_financial_summary"}


@pytest.mark.parametrize(
    "role, expected",
    [
        ("isci", LEVEL_1),
        ("sekreter", LEVEL_1 | LEVEL_2),
        ("patron", LEVEL_1 | LEVEL_2 | LEVEL_3),
    ],
)
def test_each_role_gets_its_level_and_below(role, expected):
    assert allowed_tools(role) == expected


@pytest.mark.parametrize(
    "role, tool, expected",
    [
        ("patron", "list_announcements", True),  # inherited from isci
        ("sekreter", "find_employee", True),
        ("sekreter", "get_salaries", False),  # no upward access
        ("isci", "find_employee", False),
        ("isci", "get_financial_summary", False),
        ("admin", "list_announcements", False),  # unknown role
        ("", "list_announcements", False),
        ("patron", "drop_tables", False),  # unknown tool
    ],
)
def test_can_use(role, tool, expected):
    assert can_use(role, tool) is expected


def test_unknown_role_gets_no_tools():
    assert allowed_tools("admin") == set()
