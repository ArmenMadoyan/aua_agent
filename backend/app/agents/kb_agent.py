"""Knowledge-base RAG agent — searches AUA policy PDFs."""

from __future__ import annotations

import logging

from langchain.agents import create_agent
from langchain_core.tools import tool

from backend.app.kb_rag.vector_store import search
from backend.app.llm import get_default_llm
from backend.app.prompts import KB_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class KBAgent:
    """AUA policy knowledge-base agent with vector search tool."""

    def __init__(self, checkpointer=None):
        self._checkpointer = checkpointer
        self._agent = None

    @staticmethod
    @tool(
        description=(
            "Search the AUA policy PDF knowledge base for information relevant to a question. "
            "Use this tool when you need to find AUA policies, procedures, or official information "
            "from the American University of Armenia policy documents. The tool runs embedding-based "
            "vector similarity search over policy chunks stored in PostgreSQL (embedding arrays). Use it "
            "for questions about AUA rules, academic policies, HR, facilities, admissions, conduct, "
            "etc. If the question is unrelated to AUA policies or general knowledge you already "
            "know, you may answer without this tool. Input: the user's question or a search query."
        )
    )
    def retrieve_from_knowledge_base(question: str) -> str:
        logger.info("retrieve_from_knowledge_base called with query: %s", question[:120])
        results = search(query=question, k=5)

        if not results:
            return (
                "No relevant information found in the AUA policy documents. "
                "The collection may be empty or the question doesn't match any stored policy content."
            )

        formatted_results = []
        for chunk in results:
            source = chunk.get("source", "unknown")
            content = chunk.get("content", "")
            formatted_results.append(f"From: {source}\n{content}")

        return "\n\n---\n\n".join(formatted_results)

    def build(self):
        logger.info("Building KB agent")
        self._agent = create_agent(
            model=get_default_llm(),
            tools=[self.retrieve_from_knowledge_base],
            system_prompt=KB_SYSTEM_PROMPT,
            checkpointer=self._checkpointer,
            name="kb_agent",
        )
        return self._agent

    def get_agent(self):
        if self._agent is None:
            self.build()
        return self._agent
