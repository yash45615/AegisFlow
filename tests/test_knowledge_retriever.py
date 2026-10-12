from app.knowledge.retriever import load_documents, search_knowledge, tokenize


def test_load_documents_returns_knowledge_files() -> None:
    documents = load_documents()

    assert len(documents) >= 5
    assert all(document["content"] for document in documents)


def test_tokenize_normalizes_text() -> None:
    tokens = tokenize("Database CONNECTIONS and HTTP-503")

    assert "database" in tokens
    assert "connections" in tokens
    assert "http-503" in tokens
    assert "and" not in tokens


def test_database_query_finds_database_runbook() -> None:
    results = search_knowledge(
        "database connection pool saturation",
        limit=5,
    )

    document_ids = [result["document_id"] for result in results]

    assert "database-connection-pool" in document_ids


def test_authentication_query_finds_authentication_runbook() -> None:
    results = search_knowledge(
        "authentication token validation HTTP 503",
        limit=5,
    )

    document_ids = [result["document_id"] for result in results]

    assert "authentication-failures" in document_ids


def test_payment_query_finds_payment_runbook() -> None:
    results = search_knowledge(
        "payment provider timeout",
        limit=5,
    )

    document_ids = [result["document_id"] for result in results]

    assert "payment-provider-timeouts" in document_ids


def test_empty_query_returns_no_results() -> None:
    assert search_knowledge("the and is") == []
    assert search_knowledge("") == []


def test_results_respect_limit() -> None:
    results = search_knowledge(
        "authentication database payment",
        limit=2,
    )

    assert len(results) <= 2


def test_results_include_evidence_metadata() -> None:
    results = search_knowledge(
        "database connection pool",
        limit=3,
    )

    assert results

    result = results[0]

    assert result["document_id"]
    assert result["source"].endswith(".md")
    assert 0 <= result["score"] <= 1
    assert isinstance(result["matched_terms"], list)
    assert result["content"]


def test_guidance_query_prioritizes_runbook() -> None:
    results = search_knowledge(
        "steps to resolve authentication failures",
        limit=5,
    )

    assert results
    assert results[0]["source"].startswith("data/runbooks/")


def test_limit_must_be_positive() -> None:
    import pytest

    with pytest.raises(ValueError):
        search_knowledge("database", limit=0)
