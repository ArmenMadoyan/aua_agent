"""Pytest wrapper for the RAG evaluation. Skipped unless RUN_RAG_EVAL=true.

The wrapper always passes — the evaluation is informational and produces an
artifact report, not a pass/fail signal.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.tests.eval.evaluator import RAGEvaluator


def _flag_enabled() -> bool:
    return os.getenv("RUN_RAG_EVAL", "").lower() in {"1", "true", "yes", "on"}


pytestmark = [
    pytest.mark.skipif(
        not _flag_enabled(),
        reason="RAG evaluation requires RUN_RAG_EVAL=true (live DB + LLM + Gemini keys)",
    ),
    pytest.mark.evaluation,
]


def test_run_rag_evaluation():
    """Run the full RAG evaluation and write JSON + Excel artifacts."""
    test_data = Path(__file__).parent / "test_data.json"
    output_dir = Path(__file__).resolve().parents[3] / "eval_reports"

    evaluator = RAGEvaluator(test_data_path=test_data, output_dir=output_dir)
    report = evaluator.evaluate_all()
    paths = evaluator.save_report(report)
    evaluator.print_summary(report)
    print(f"\nJSON report:  {paths['json']}")
    print(f"Excel report: {paths['xlsx']}")
    assert paths["json"].exists()
    assert paths["xlsx"].exists()
