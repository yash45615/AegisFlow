
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


TEXT_FIELDS = (
    "source",
    "path",
    "file_path",
    "filename",
    "file_name",
    "title",
    "name",
    "id",
    "document_id",
    "content",
    "text",
    "page_content",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")

    if isinstance(value, Mapping):
        return dict(value)

    if isinstance(value, str):
        return {"text": value}

    return {}


def _result_text(result: Any) -> str:
    """Extract searchable provenance and text from common result shapes."""
    data = _as_mapping(result)
    pieces: list[str] = []

    for field in TEXT_FIELDS:
        value = data.get(field)
        if isinstance(value, (str, int, float)):
            pieces.append(str(value))

    metadata = data.get("metadata")
    if isinstance(metadata, Mapping):
        for key in TEXT_FIELDS:
            value = metadata.get(key)
            if isinstance(value, (str, int, float)):
                pieces.append(str(value))

    # Some retrievers nest the actual document in a "document" field.
    nested = data.get("document")
    if nested is not None and nested is not result:
        pieces.append(_result_text(nested))

    if not pieces and not isinstance(result, (str, Mapping)):
        pieces.append(str(result))

    return " ".join(pieces).lower()


def _matches_expected_document(
    result: Any,
    expected_document: str,
) -> bool:
    """Match an expected filename or identifier in result provenance."""
    text = _result_text(result)
    expected = expected_document.replace("\\", "/").lower()

    if expected in text:
        return True

    # Also allow a filename without its extension, e.g.
    # "database-connection-pool".
    if expected.endswith(".md"):
        stem = expected[:-3]
        return bool(stem) and stem in text

    return False


def precision_at_k(
    results: list[Any],
    relevant_documents: set[str],
    k: int = 3,
) -> float:
    """Fraction of the first K results that are relevant."""
    if k < 1:
        raise ValueError("k must be at least 1.")

    top_results = results[:k]
    if not top_results:
        return 0.0

    relevant_count = sum(
        any(
            _matches_expected_document(result, expected)
            for expected in relevant_documents
        )
        for result in top_results
    )

    return relevant_count / len(top_results)


def recall_at_k(
    results: list[Any],
    relevant_documents: set[str],
    k: int = 3,
) -> float:
    """Fraction of known relevant documents found in the first K results."""
    if k < 1:
        raise ValueError("k must be at least 1.")

    if not relevant_documents:
        return 1.0

    found = {
        expected
        for expected in relevant_documents
        if any(
            _matches_expected_document(result, expected)
            for result in results[:k]
        )
    }

    return len(found) / len(relevant_documents)


def reciprocal_rank(
    results: list[Any],
    relevant_documents: set[str],
) -> float:
    """Reciprocal rank of the first result matching any expected document."""
    for index, result in enumerate(results, start=1):
        if any(
            _matches_expected_document(result, expected)
            for expected in relevant_documents
        ):
            return 1.0 / index

    return 0.0


def evaluate_retrieval_case(
    *,
    query: str,
    results: list[Any],
    relevant_documents: set[str],
    k: int = 3,
) -> dict[str, Any]:
    """Evaluate one labeled retrieval query."""
    if not relevant_documents:
        raise ValueError(
            "Each evaluation case must specify a relevant document."
        )

    p_at_k = precision_at_k(results, relevant_documents, k)
    r_at_k = recall_at_k(results, relevant_documents, k)
    rr = reciprocal_rank(results, relevant_documents)

    return {
        "query": query,
        "expected_documents": sorted(relevant_documents),
        "retrieved_count": len(results),
        "k": k,
        "precision_at_k": round(p_at_k, 4),
        "recall_at_k": round(r_at_k, 4),
        "reciprocal_rank": round(rr, 4),
        "expected_document_found": rr > 0,
        "retrieved_sources": [
            _result_text(result)[:240]
            for result in results[:k]
        ],
    }


def evaluate_retrieval_dataset(
    cases: list[dict[str, Any]],
    *,
    k: int = 3,
) -> dict[str, Any]:
    """Run a labeled dataset and calculate mean retrieval metrics."""
    if not cases:
        raise ValueError("The evaluation dataset cannot be empty.")

    evaluations = [
        evaluate_retrieval_case(
            query=case["query"],
            results=case["results"],
            relevant_documents=set(case["relevant_documents"]),
            k=k,
        )
        for case in cases
    ]

    count = len(evaluations)

    return {
        "evaluation": "retrieval_quality",
        "k": k,
        "case_count": count,
        "mean_precision_at_k": round(
            sum(item["precision_at_k"] for item in evaluations) / count,
            4,
        ),
        "mean_recall_at_k": round(
            sum(item["recall_at_k"] for item in evaluations) / count,
            4,
        ),
        "mean_reciprocal_rank": round(
            sum(item["reciprocal_rank"] for item in evaluations) / count,
            4,
        ),
        "cases": evaluations,
    }
