"""Standalone CLI for running the RAG evaluation.

Usage:
    python -m backend.tests.eval.run_evaluation [--output-dir DIR] [--max-queries N]

Required env vars:
    DATABASE_URL          PostgreSQL with pgvector
    OPENAI_API_KEY        embeddings
    ANTHROPIC_API_KEY     KB agent LLM (model from ANTHROPIC_MODEL env)
    GEMINI_API_KEY        judge LLM
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from backend.tests.eval.evaluator import RAGEvaluator

DEFAULT_TEST_DATA = Path(__file__).parent / "test_data.json"
DEFAULT_OUTPUT_DIR = "eval_reports"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AUA RAG evaluation suite")
    parser.add_argument(
        "--test-data",
        default=str(DEFAULT_TEST_DATA),
        help="Path to test_data.json (default: alongside this script)",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for JSON + Excel reports (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=None,
        help="Limit to first N queries (useful for quick local runs)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    evaluator = RAGEvaluator(
        test_data_path=args.test_data,
        output_dir=args.output_dir,
    )
    report = evaluator.evaluate_all(max_queries=args.max_queries)
    paths = evaluator.save_report(report)
    evaluator.print_summary(report)
    print(f"JSON report:  {paths['json']}")
    print(f"Excel report: {paths['xlsx']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
