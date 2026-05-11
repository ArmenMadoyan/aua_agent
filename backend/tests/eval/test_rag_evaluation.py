"""Pytest wrapper for the RAG evaluation. Skipped unless RUN_RAG_EVAL=true.

The wrapper always passes — the evaluation is informational and produces an
artifact report, not a pass/fail signal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.config import RUN_RAG_EVAL
from backend.tests.eval.evaluator import RAGEvaluator

pytestmark = [
    pytest.mark.skipif(
        not RUN_RAG_EVAL,
        reason="RAG evaluation disabled — set RUN_RAG_EVAL=True in backend/config.py or RUN_RAG_EVAL=true env var",
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
