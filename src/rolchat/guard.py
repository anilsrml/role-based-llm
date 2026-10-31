from functools import cache
from pathlib import Path

from nemoguardrails import LLMRails, RailsConfig
from nemoguardrails.rails.llm.options import RailStatus

CONFIG_DIR = Path(__file__).parent / "guardrails"


def make_rails(llm=None) -> LLMRails:
    return LLMRails(RailsConfig.from_path(str(CONFIG_DIR)), llm=llm)


@cache
def _default_rails() -> LLMRails:
    # Built on first use: creating it needs OPENROUTER_API_KEY.
    return make_rails()


async def check_input(text: str, rails: LLMRails | None = None) -> str | None:
    """Return the name of the rail that blocked the message, or None if it may go to the agent."""
    result = await (rails or _default_rails()).check_async([{"role": "user", "content": text}])
    return result.rail if result.status == RailStatus.BLOCKED else None
