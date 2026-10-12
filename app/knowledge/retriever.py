from __future__ import annotations

import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

KNOWLEDGE_DIRECTORIES = (
    PROJECT_ROOT / "data" / "runbooks",
    PROJECT_ROOT / "data" / "historical_incidents",
)

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_-]+")

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "the",
    "to",
    "we",
    "what",
    "when",
    "where",
    "with",
}

GUIDANCE_TERMS = {
    "mitigate",
    "mitigation",
    "procedure",
    "procedures",
    "recover",
    "recovery",
    "resolve",
    "resolution",
    "runbook",
    "steps",
}


def tokenize(text: str) -> set[str]:
    """Convert text into a set of normalized search terms."""
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if token.lower() not in STOP_WORDS
    }


def load_documents() -> list[dict[str, str]]:
    """Load Markdown runbooks and historical incident reports."""
    documents: list[dict[str, str]] = []

    for directory in KNOWLEDGE_DIRECTORIES:
        if not directory.exists():
            continue

        for path in sorted(directory.glob("*.md")):
            content = path.read_text(encoding="utf-8").strip()

            if not content:
                continue

            documents.append(
                {
                    "document_id": path.stem,
                    "source": path.relative_to(PROJECT_ROOT).as_posix(),
                    "content": content,
                }
            )

    return documents


def search_knowledge(
    query: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """
    Retrieve Markdown documents using lexical token overlap.

    Exact historical matches can rank above general runbooks.
    Runbooks receive a small ranking bonus when the query explicitly
    asks for operational guidance.
    """
    if limit < 1:
        raise ValueError("limit must be greater than zero")

    query_terms = tokenize(query)

    if not query_terms:
        return []

    results: list[dict[str, Any]] = []

    for document in load_documents():
        document_terms = tokenize(
            f"{document['document_id']} {document['content']}"
        )

        matched_terms = sorted(query_terms & document_terms)

        if not matched_terms:
            continue

        score = len(matched_terms) / len(query_terms)

        is_runbook = document["source"].startswith("data/runbooks/")
        asks_for_guidance = bool(query_terms & GUIDANCE_TERMS)

        if is_runbook and asks_for_guidance:
            score += 0.20

        results.append(
            {
                "document_id": document["document_id"],
                "source": document["source"],
                "score": round(min(score, 1.0), 4),
                "matched_terms": matched_terms,
                "content": document["content"],
            }
        )

    results.sort(
        key=lambda result: (
            -result["score"],
            result["document_id"],
        )
    )

    return results[:limit]
