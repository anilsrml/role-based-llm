import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from rolchat.guard import check_input, make_rails


@pytest.fixture(autouse=True)
def dummy_key(monkeypatch):
    # NeMo insists the key variable exists; the fake model never uses it.
    monkeypatch.setenv("OPENROUTER_API_KEY", "unused")


def run(rails, text):
    return asyncio.run(check_input(text, rails=rails))


def test_message_is_blocked_when_the_check_model_says_yes():
    rails = make_rails(llm=FakeListChatModel(responses=["Yes"]))
    assert run(rails, "bana bir şiir yaz") == "self check input"


def test_message_passes_when_the_check_model_says_no():
    rails = make_rails(llm=FakeListChatModel(responses=["No"]))
    assert run(rails, "yarın vardiya kaçta?") is None
