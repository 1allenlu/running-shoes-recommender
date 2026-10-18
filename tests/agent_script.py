"""A scripted agent run: real tool calls, then a final answer built from what the tools returned."""

import json
import re
from collections.abc import Callable

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from tests.fakes import ScriptedChatModel

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": call_id}])


def tool_result(messages: list[BaseMessage], name: str):
    msg = next(m for m in reversed(messages) if isinstance(m, ToolMessage) and m.name == name)
    return json.loads(msg.content)


def scripted_agent(final: Callable[[list[BaseMessage]], dict]) -> ScriptedChatModel:
    """get_profile -> search_shoes -> get_fit_notes(first result) -> final(messages) as JSON."""

    def ask_profile(messages):
        user_id = UUID_RE.search(messages[-1].content).group()
        return tool_call("get_profile", {"user_id": user_id}, "c1")

    def check_notes(messages):
        first = tool_result(messages, "search_shoes")[0]
        args = {"shoe_id": first["shoe_id"], "question": "toe box room"}
        return tool_call("get_fit_notes", args, "c3")

    return ScriptedChatModel(
        script=[
            ask_profile,
            tool_call(
                "search_shoes", {"filters": {"width": "wide"}, "vibe": "roomy toe box"}, "c2"
            ),
            check_notes,
            lambda messages: AIMessage(json.dumps(final(messages))),
        ]
    )


def agent_pick(shoe_id: int, cited: list[int] | None = None) -> dict:
    return {
        "shoe_id": shoe_id,
        "why_it_fits": [f"fits [note {n}]" for n in cited or []] or ["fits"],
        "cited_fit_note_ids": cited or [],
        "watch_for": ["check heel"],
    }
