"""Test doubles: keyword embeddings (deterministic overlap) and a scripted chat model."""

import hashlib
import math
import re

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
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
    """Replies with the given messages in order (tool calls included); records what it saw."""

    script: list[AIMessage]
    seen: list[list] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(list(messages))
        reply = self.script.pop(0) if self.script else AIMessage(content="(no more script)")
        return ChatResult(generations=[ChatGeneration(message=reply)])
