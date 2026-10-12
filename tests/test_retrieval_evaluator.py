
import pytest

from app.evaluation.retrieval_evaluator import (
    evaluate_retrieval_case,
    evaluate_retrieval_dataset,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def sample_results():
    return [
        {
            "source": "data/runbooks/database-connection-pool.md",
            "content": "Inspect connection pool saturation and timeouts.",
        },
        {
            "source": "data/runbooks/authentication-failures.md",
            "content": "Check authentication service logs.",
        },
        {
            "source": "data/runbooks/payment-provider-timeouts.md",
            "content": "Inspect payment provider latency.",
        },
    ]


def test_precision_at_k():
    results = sample_results()
    relevant = {"database-connection-pool.md"}

    assert precision_at_k(results, relevant, k=3) == pytest.approx(1 / 3)


def test_recall_at_k_when_relevant_document_is_found():
    results = sample_results()
    relevant = {"database-connection-pool.md"}

    assert recall_at_k(results, relevant, k=3) == 1.0


def test_reciprocal_rank_for_first_result():
    results = sample_results()
    relevant = {"database-connection-pool.md"}

    assert reciprocal_rank(results, relevant) == 1.0


def test_reciprocal_rank_for_second_result():
    results = sample_results()
    relevant = {"authentication-failures.md"}

    assert reciprocal_rank(results, relevant) == 0.5


def test_missing_relevant_document_returns_zero():
    results = sample_results()
    relevant = {"missing-runbook.md"}

    assert recall_at_k(results, relevant, k=3) == 0.0
    assert reciprocal_rank(results, relevant) == 0.0


def test_case_evaluation_reports_retrieval_success():
    result = evaluate_retrieval_case(
        query="database connection pool saturation",
        results=sample_results(),
        relevant_documents={"database-connection-pool.md"},
        k=3,
    )

    assert result["expected_document_found"] is True
    assert result["precision_at_k"] == 0.3333
    assert result["reciprocal_rank"] == 1.0


def test_dataset_evaluation_aggregates_metrics():
    results = sample_results()

    report = evaluate_retrieval_dataset(
        [
            {
                "query": "database pool saturation",
                "results": results,
                "relevant_documents": {"database-connection-pool.md"},
            },
            {
                "query": "authentication login failure",
                "results": results,
                "relevant_documents": {"authentication-failures.md"},
            },
        ],
        k=3,
    )

    assert report["case_count"] == 2
    assert report["mean_precision_at_k"] == 0.3333
    assert report["mean_reciprocal_rank"] == pytest.approx(0.75)


def test_invalid_k_is_rejected():
    with pytest.raises(ValueError):
        precision_at_k(sample_results(), {"database-connection-pool.md"}, 0)
