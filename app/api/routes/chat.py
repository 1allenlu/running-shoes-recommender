import json
import uuid
from collections.abc import Callable, Iterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_session, get_session_factory
from app.api.routes.users import get_user
from app.chat_agent import stream_chat
from app.recommend import confirmed_profile

router = APIRouter(tags=["chat"])
SessionDep = Annotated[Session, Depends(get_session)]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


def get_chat_model_factory() -> Callable[[], BaseChatModel]:
    """Tests override this with a scripted model."""
    from app.llm import get_chat_model, llm_ready

    ready, reason = llm_ready()
    if not ready:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"chat is unavailable: {reason}")
    return get_chat_model


def sse(events: Iterator[dict]) -> Iterator[str]:
    for e in events:
        yield f"event: {e['event']}\ndata: {json.dumps(e['data'])}\n\n"


@router.post("/users/{user_id}/chat")
def chat(
    user_id: uuid.UUID,
    body: ChatIn,
    session: SessionDep,
    session_factory: Annotated[sessionmaker, Depends(get_session_factory)],
    model_factory: Annotated[Callable[[], BaseChatModel], Depends(get_chat_model_factory)],
) -> StreamingResponse:
    """Follow-up chat about the runner's picks, streamed as server-sent events:
    `token` (text), `tool` (a tool started), `picks` (a re-ranked Recommendation),
    `error`, then `done`."""
    get_user(session, user_id)
    if confirmed_profile(session, user_id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "confirm a foot profile first")
    if body.messages[-1].role != "user":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "last message must be the user's"
        )
    model = model_factory()
    messages = [m.model_dump() for m in body.messages]

    def events() -> Iterator[str]:
        # Own session: the request's session closes before the stream finishes.
        with session_factory() as stream_session:
            yield from sse(stream_chat(stream_session, model, user_id, messages))

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
