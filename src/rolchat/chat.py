from dataclasses import dataclass, field

from pydantic_ai.messages import ModelMessage, ToolCallPart
from sqlalchemy import Engine

from rolchat.agent import agent
from rolchat.guard import check_input
from rolchat.policy import allowed_tools
from rolchat.tools import Deps

REFUSAL = "Bu konuda bilgim yok."


@dataclass
class Reply:
    text: str
    history: list[ModelMessage]
    blocked_by: str | None = None
    tools_offered: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)


async def answer(text: str, role: str, history: list[ModelMessage], engine: Engine, guard=check_input) -> Reply:
    blocked_by = await guard(text)
    if blocked_by:
        return Reply(text=REFUSAL, history=history, blocked_by=blocked_by)

    result = await agent.run(text, deps=Deps(role=role, engine=engine), message_history=history)
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
