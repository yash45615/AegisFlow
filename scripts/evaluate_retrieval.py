
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.retrieval_evaluator import evaluate_retrieval_dataset
from app.knowledge.retriever import search_knowledge


# These labels are our initial expected-answer dataset.
# Review them against the actual contents of your knowledge base.
EVALUATION_CASES = [
    {
        "query": "database connection pool saturation and timeout errors",
        "relevant_documents": ["database-connection-pool.md"],
    },
    {
        "query": "authentication failures and users unable to log in",
        "relevant_documents": ["authentication-failures.md"],
    },
    {
        "query": "payment provider timeout and slow payment responses",
        "relevant_documents": ["payment-provider-timeouts.md"],
    },
]


def main() -> int:
    cases = []

    for case in EVALUATION_CASES:
        query = case["query"]
        results = search_knowledge(query, limit=5)

        if hasattr(results, "model_dump"):
            results = results.model_dump(mode="json")

        if not isinstance(results, list):
            raise TypeError(
                "search_knowledge() must return a list for this evaluation. "
                f"Received: {type(results).__name__}"
            )

        cases.append(
            {
                "query": query,
                "results": results,
                "relevant_documents": case["relevant_documents"],
            }
        )

    report = evaluate_retrieval_dataset(cases, k=3)
    report["project"] = "AegisFlow"
    report["report_type"] = "local_retrieval_evaluation"
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["note"] = (
        "Initial labeled evaluation set. Scores measure filename-based "
        "retrieval against expected documents, not factual correctness. "
        "Confirm expected labels against the source documents."
    )

    output_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "retrieval_evaluation.json"
    output_file.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nAegisFlow retrieval evaluation")
    print("-" * 36)
    print(f"Queries: {report['case_count']}")
    print(f"Mean Precision@3: {report['mean_precision_at_k']:.2%}")
    print(f"Mean Recall@3: {report['mean_recall_at_k']:.2%}")
    print(f"Mean Reciprocal Rank: {report['mean_reciprocal_rank']:.4f}")

    for item in report["cases"]:
        status = (
            "FOUND"
            if item["expected_document_found"]
            else "NOT FOUND"
        )
        print(f"\n[{status}] {item['query']}")
        print(f"  Expected: {', '.join(item['expected_documents'])}")
        print(f"  Reciprocal rank: {item['reciprocal_rank']}")

    print(f"\nReport saved to: {output_file}")

    # A retrieval miss is a signal to investigate, not a reason to
    # suppress or rewrite the evaluation results.
    return 0 if all(
        item["expected_document_found"] for item in report["cases"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
