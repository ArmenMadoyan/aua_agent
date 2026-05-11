"""Google Gemini LLM-as-judge wrapper. Returns structured JSON scores per dimension."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from backend.config import GEMINI_API_KEY
from backend.tests.eval.judge_prompts import (
    CITATION_ACCURACY_PROMPT,
    COMPLETENESS_PROMPT,
    HALLUCINATION_PROMPT,
    RELEVANCE_PROMPT,
    TOP1_ACCURACY_PROMPT,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
RATE_LIMIT_SLEEP_SECONDS = 0.5


class GeminiJudge:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY (or GOOGLE_API_KEY) must be set in backend/config.py "
                "or via env var to run the RAG evaluation"
            )

        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        self._genai = genai
        self._model = genai.GenerativeModel(model_name)
        self._gen_config = genai.GenerationConfig(
            temperature=0.0,
            response_mime_type="application/json",
        )

    def _ask(self, prompt: str) -> dict[str, Any]:
        try:
            response = self._model.generate_content(
                prompt, generation_config=self._gen_config
            )
            text = response.text or "{}"
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Gemini returned non-JSON; recording score=null. err=%s", exc
            )
            return {"score": None, "explanation": f"judge_parse_error: {exc}"}
        except Exception as exc:
            logger.warning("Gemini call failed: %s", exc)
            return {"score": None, "explanation": f"judge_call_error: {exc}"}
        finally:
            time.sleep(RATE_LIMIT_SLEEP_SECONDS)

    def evaluate_citation_accuracy(
        self,
        query: str,
        answer: str,
        retrieved_sources: list[str],
        expected_policies: list[str],
    ) -> dict[str, Any]:
        prompt = CITATION_ACCURACY_PROMPT.format(
            query=query,
            retrieved_sources=json.dumps(retrieved_sources, ensure_ascii=False),
            expected_policies=json.dumps(expected_policies, ensure_ascii=False),
            answer=answer,
        )
        return self._ask(prompt)

    def evaluate_top1_accuracy(
        self,
        query: str,
        answer: str,
        top1_source: str,
        top1_content: str,
    ) -> dict[str, Any]:
        prompt = TOP1_ACCURACY_PROMPT.format(
            query=query,
            top1_source=top1_source,
            top1_content=top1_content,
            answer=answer,
        )
        return self._ask(prompt)

    def evaluate_hallucination(
        self,
        query: str,
        answer: str,
        retrieved_chunks: list[dict],
    ) -> dict[str, Any]:
        formatted_chunks = (
            "\n\n---\n\n".join(
                f"[chunk {i + 1}] From: {c.get('source', 'unknown')}\n{c.get('content', '')}"
                for i, c in enumerate(retrieved_chunks)
            )
            or "(no chunks retrieved)"
        )
        prompt = HALLUCINATION_PROMPT.format(
            query=query,
            retrieved_chunks=formatted_chunks,
            answer=answer,
        )
        return self._ask(prompt)

    def evaluate_completeness(
        self,
        query: str,
        answer: str,
        expected_topics: list[str],
    ) -> dict[str, Any]:
        prompt = COMPLETENESS_PROMPT.format(
            query=query,
            expected_topics=json.dumps(expected_topics, ensure_ascii=False),
            answer=answer,
        )
        return self._ask(prompt)

    def evaluate_relevance(self, query: str, answer: str) -> dict[str, Any]:
        prompt = RELEVANCE_PROMPT.format(query=query, answer=answer)
        return self._ask(prompt)
