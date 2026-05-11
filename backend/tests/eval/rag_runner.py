"""Run a single query through the live RAG pipeline (vector_store + KB agent).

Bypasses FastAPI: calls library functions directly. Captures both the retrieved
chunks (independent of what the agent ended up using) and the final answer.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field

from backend.app.kb_rag.vector_store import search
from backend.app.orchestrator import init_agents, run_chat_turn

logger = logging.getLogger(__name__)

DEFAULT_K = 5  # matches kb_agent.retrieve_from_knowledge_base


@dataclass
class RetrievedChunk:
    content: str
    source: str
    score: float


@dataclass
class RagResult:
    query: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    answer: str = ""
    agent_used: str = ""
    latency_seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "chunks": [asdict(c) for c in self.chunks],
            "answer": self.answer,
            "agent_used": self.agent_used,
            "latency_seconds": self.latency_seconds,
            "error": self.error,
        }


class RagRunner:
    """Thin wrapper around vector_store.search + orchestrator.run_chat_turn.

    Call ``setup()`` once before the first ``run()`` to initialize agents.
    """

    def __init__(self, k: int = DEFAULT_K):
        self._k = k
        self._initialized = False

    def setup(self) -> None:
        if self._initialized:
            return
        logger.info("RagRunner: initializing agents (no checkpointer)")
        init_agents(checkpointer=None)
        self._initialized = True

    def run(self, query: str, chat_id: str | int = "eval") -> RagResult:
        self.setup()
        start = time.time()
        result = RagResult(query=query)
        try:
            raw_chunks = search(query=query, k=self._k)
            result.chunks = [
                RetrievedChunk(
                    content=c.get("content", ""),
                    source=c.get("source", "unknown"),
                    score=float(c.get("score", 0.0)),
                )
                for c in raw_chunks
            ]

            orchestrator_result = run_chat_turn(
                [{"role": "user", "content": query}],
                chat_id=chat_id,
                force_agent="kb",
            )
            result.answer = orchestrator_result.reply
            result.agent_used = orchestrator_result.agent_used
        except Exception as exc:
            logger.exception("RagRunner.run failed for query: %s", query[:120])
            result.error = f"{type(exc).__name__}: {exc}"
        finally:
            result.latency_seconds = time.time() - start
        return result
