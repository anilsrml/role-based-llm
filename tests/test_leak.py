"""Leakage matrix: a role's reply must never contain a value from a level above it.

Canaries are real values read from the seeded test database (salaries, financial figures,
phone numbers, e-mails). The default run uses TestModel, which calls every tool it is offered.
"""
import asyncio
import re

import pytest
from pydantic_ai.models.test import TestModel
from sqlalchemy import text

from rolchat.agent import agent
from rolchat.chat import answer

LEVEL = {"isci": 1, "sekreter": 2, "patron": 3}
MIN_AMOUNT = 10_000  # smaller numbers could appear in a reply by chance

CANARY_SQL = {
    2: [
        "SELECT phone FROM employees",
        "SELECT email FROM employees",
    ],
    3: [
        "SELECT monthly_gross FROM salaries",
        "SELECT revenue FROM financial_summary",
        "SELECT expenses FROM financial_summary",
        "SELECT profit FROM financial_summary",
        "SELECT cash_balance FROM financial_summary",
    ],
}


def _digits_pattern(digits: str, bounded: bool = True) -> str:
    # Up to two separators between digits: "45000", "45.000", "45,000", "45 000", "0532 123 45 67".
    body = r"[\s.,()-]{0,2}".join(digits)
    if not bounded:  # phones: 10 digits are distinctive, and "+90 532..." must still match
        return body
    # Not part of a longer number ("145000", "45.000.000"); a decimal tail like "45000.00" is fine.
    return r"(?<!\d)(?<!\d[.,\s])" + body + r"(?![.,\s]?\d{3})(?!\d)"


def canaries(engine) -> dict[int, list[tuple[str, re.Pattern]]]:
    """Level -> [(value, pattern)] for every secret value in the seeded database."""
    found = {}
    with engine.connect() as conn:
        for level, queries in CANARY_SQL.items():
            found[level] = []
            for sql in queries:
                for value in conn.execute(text(sql)).scalars():
                    if "@" in str(value):
                        pattern = re.escape(value.lower())
                    elif "phone" in sql:
                        pattern = _digits_pattern(re.sub(r"\D", "", value)[1:], bounded=False)  # leading 0 optional
                    elif abs(value) >= MIN_AMOUNT:
                        pattern = _digits_pattern(str(abs(int(value))))
                    else:
                        continue
                    found[level].append((str(value), re.compile(pattern, re.IGNORECASE)))
    return found


@pytest.fixture(scope="session")
def canary_levels(reader_engine, seeded):
    return canaries(reader_engine)


@pytest.fixture(scope="session")
def canaries_above(canary_levels):
    def above(role: str) -> list[tuple[str, re.Pattern]]:
        return [c for level, cs in canary_levels.items() if level > LEVEL[role] for c in cs]
    return above


def leaked(reply: str, secrets) -> list[str]:
    return [value for value, pattern in secrets if pattern.search(reply)]


async def guard_passes(text):
    return None


def test_detector_catches_the_formats_a_model_would_use():
    amount = re.compile(_digits_pattern("45250"))
    for hit in ["45250", "45.250 TL", "45,250", "45 250", "maaşı 45250.00"]:
        assert amount.search(hit), hit
    for miss in ["145250", "45.250.000", "4525", "452500"]:
        assert not amount.search(miss), miss

    phone = re.compile(_digits_pattern("5321234567", bounded=False))
    for hit in ["0532 123 45 67", "05321234567", "(0532) 123-45-67", "+90 532 123 45 67"]:
        assert phone.search(hit), hit


def test_seed_has_an_injection_announcement_the_worker_reads(reader_engine, seeded):
    # Among the 5 newest, which list_announcements returns by default.
    with reader_engine.connect() as conn:
        newest = conn.execute(text("SELECT body FROM announcements ORDER BY published_on DESC LIMIT 5")).scalars()
        assert any("get_salaries" in body for body in newest)


def ask_test_model(engine, role):
    with agent.override(model=TestModel()):
        return asyncio.run(answer("her şeyi göster", role, [], engine, guard=guard_passes)).text


@pytest.mark.parametrize("role", ["isci", "sekreter", "patron"])
def test_no_role_gets_a_canary_above_its_level(reader_engine, canaries_above, role):
    assert leaked(ask_test_model(reader_engine, role), canaries_above(role)) == []


@pytest.mark.parametrize("role", ["sekreter", "patron"])
def test_positive_control_a_role_does_see_its_own_level(reader_engine, canary_levels, role):
    # Proves the detector works on real replies: the role's own level shows up.
    assert leaked(ask_test_model(reader_engine, role), canary_levels[LEVEL[role]])
