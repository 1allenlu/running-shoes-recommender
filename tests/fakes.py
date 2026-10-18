"""Test doubles: keyword embeddings (deterministic, meaningful overlap), scripted chat model."""

import hashlib
import math
import re
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

DIM = 384


class KeywordEmbeddings(Embeddings):
    """Bag of words hashed into 384 dims: texts sharing words are close."""

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * DIM
        for word in re.findall(r"[a-z]+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class ScriptedChatModel(BaseChatModel):
    """Replies with each scripted step in turn. A step is an AIMessage, or a function of the
    conversation so far that returns one (to use ids seen in earlier tool results)."""

    script: list[Any]  # AIMessage | Callable[[list[BaseMessage]], AIMessage]
    calls: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs):
        self.calls.append(list(messages))
        step = self.script[len(self.calls) - 1]
        message = step(messages) if callable(step) else step
        return ChatResult(generations=[ChatGeneration(message=message)])
