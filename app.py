import os

# Without keys, Langfuse would still try to export and get 401s; turn tracing off instead.
if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
    os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.input_widget import Switch
from langfuse import Langfuse
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart
from sqlalchemy import create_engine

from rolchat.chat import answer, decision_panel, mask_level3_spans
from rolchat.models import ROLE_LEVELS, reader_url

CHARACTERS = {"patron", "sekreter", "isci"}
PANEL_AUTHOR = "Karar paneli"

engines = {level: create_engine(reader_url(level)) for level in set(ROLE_LEVELS.values())}
Langfuse(mask_otel_spans=mask_level3_spans)  # created first, so get_client() returns this masked client
Agent.instrument_all()  # LLM and tool calls show up in Langfuse under each chat trace


@cl.data_layer
def data_layer():
    return SQLAlchemyDataLayer(conninfo=os.environ["CHAINLIT_DATABASE_URL"])


@cl.password_auth_callback
def login(username: str, password: str):
    # Demo login: the character name is enough, the password is ignored.
    # The role then lives in Chainlit's signed session token, never in a message.
    name = username.strip().lower()
    if name in CHARACTERS:
        return cl.User(identifier=name, metadata={"role": name})
    return None


@cl.on_chat_start
async def start():
    cl.user_session.set("history", [])
    cl.user_session.set("dev_mode", False)
    await cl.ChatSettings([Switch(id="dev_mode", label="Geliştirici modu", initial=False)]).send()


@cl.on_settings_update
async def settings(values):
    cl.user_session.set("dev_mode", values["dev_mode"])


@cl.on_chat_resume
async def resume(thread):
    history = []
    for step in thread["steps"]:
        if step["type"] == "user_message":
            history.append(ModelRequest.user_text_prompt(step["output"]))
        elif step["type"] == "assistant_message" and step["name"] != PANEL_AUTHOR:
            history.append(ModelResponse(parts=[TextPart(step["output"])]))
    cl.user_session.set("history", history)
    cl.user_session.set("dev_mode", False)


@cl.on_message
async def message(msg: cl.Message):
    role = cl.user_session.get("user").metadata["role"]
    reply = await answer(
        msg.content, role, cl.user_session.get("history"), engines, session_id=cl.context.session.thread_id
    )
    cl.user_session.set("history", reply.history)
    await cl.Message(content=reply.text).send()
    if cl.user_session.get("dev_mode"):
        await cl.Message(content=decision_panel(reply, role), author=PANEL_AUTHOR).send()
