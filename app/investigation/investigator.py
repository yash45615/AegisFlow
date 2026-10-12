from __future__ import annotations

import re
from typing import Any

from app.knowledge.retriever import search_knowledge


def _to_dict(value: Any) -> dict[str, Any]:
    """Convert a Pydantic model or mapping into a dictionary."""
    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        result = value.model_dump(mode="json")
        if isinstance(result, dict):
            return result

    if hasattr(value, "dict"):
        result = value.dict()
        if isinstance(result, dict):
            return result

    return {}


def _as_list(value: Any) -> list[Any]:
    """Normalize optional list-like incident fields."""
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return [value]


def _display(value: Any) -> str:
    """Produce a readable representation of a telemetry value."""
    if isinstance(value, dict):
        parts = [
            f"{key}={item}"
            for key, item in value.items()
            if item is not None
        ]
        return ", ".join(parts)

    if isinstance(value, list):
        return "; ".join(_display(item) for item in value)

    return str(value)


def _get_text(item: Any, *keys: str) -> str:
    """Read the first populated text field from a dictionary-like item."""
    data = _to_dict(item)

    for key in keys:
        value = data.get(key)

        if value is not None and str(value).strip():
            return str(value)

    if isinstance(item, str):
        return item

    return ""


def _incident_text(incident: dict[str, Any]) -> str:
    """Build searchable text from observed incident fields."""
    sections: list[str] = []

    for key in (
        "scenario",
        "title",
        "description",
        "service",
        "affected_service",
        "severity",
    ):
        value = incident.get(key)

        if value is not None:
            sections.append(f"{key}: {_display(value)}")

    for key in ("logs", "events", "metrics", "signals"):
        for item in _as_list(incident.get(key)):
            sections.append(f"{key}: {_display(item)}")

    return " ".join(sections)


def _collect_observations(
    incident: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Extract logs and metric snapshots without interpreting them as causes."""
    observations: list[str] = []
    search_fragments: list[str] = []

    for key in ("logs", "events"):
        for item in _as_list(incident.get(key)):
            if isinstance(item, str):
                message = item.strip()
            else:
                message = _get_text(
                    item,
                    "message",
                    "log",
                    "event",
                    "description",
                    "detail",
                )

                if not message:
                    message = _display(_to_dict(item))

            if message:
                observations.append(f"Log/event: {message}")
                search_fragments.append(message)

    for key in ("metrics", "signals"):
        for item in _as_list(incident.get(key)):
            if isinstance(item, dict) or hasattr(item, "model_dump"):
                metric = _to_dict(item)
                metric_name = _get_text(
                    metric,
                    "name",
                    "metric",
                    "metric_name",
                )
                metric_value = metric.get(
                    "value",
                    metric.get("current_value"),
                )
                unit = metric.get("unit", "")
                baseline = metric.get("baseline")

                if metric_name and metric_value is not None:
                    detail = f"{metric_name}={metric_value}"

                    if unit:
                        detail += f" {unit}"

                    if baseline is not None:
                        detail += f" (baseline={baseline})"
                else:
                    detail = _display(metric)

            else:
                detail = _display(item)

            if detail:
                observations.append(f"Metric/signal: {detail}")
                search_fragments.append(detail)

    if not observations:
        observations.append(
            "No structured log or metric observations were available."
        )

    return observations, search_fragments


def _build_hypotheses(
    incident: dict[str, Any],
    observations: list[str],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Build conservative hypotheses from observable signals.

    The simulator's suspected_root_cause field is deliberately not used
    as proof. Each hypothesis is labeled as unconfirmed.
    """
    text = " ".join(
        [
            _incident_text(incident),
            " ".join(observations),
            " ".join(
                str(item.get("content", ""))
                for item in evidence
            ),
        ]
    ).lower()

    hypotheses: list[dict[str, Any]] = []

    def add_hypothesis(
        hypothesis: str,
        rationale: str,
        checks: list[str],
        related_terms: set[str],
    ) -> None:
        matched_sources = [
            {
                "document_id": item["document_id"],
                "source": item["source"],
            }
            for item in evidence
            if related_terms
            & {
                term.lower()
                for term in item.get("matched_terms", [])
            }
        ]

        hypotheses.append(
            {
                "hypothesis": hypothesis,
                "status": "unconfirmed",
                "rationale": rationale,
                "supporting_sources": matched_sources,
                "checks_to_validate": checks,
            }
        )

    if any(
        term in text
        for term in (
            "connection pool",
            "pool saturation",
            "database saturation",
            "database connection",
            "connection timeout",
        )
    ):
        add_hypothesis(
            hypothesis=(
                "Database connection-pool saturation may be "
                "contributing to service degradation."
            ),
            rationale=(
                "Incident text contains database or connection-pool "
                "signals. This does not establish the underlying cause."
            ),
            checks=[
                "Inspect active, idle, and waiting database connections.",
                "Compare connection acquisition latency with the incident timeline.",
                "Check database CPU, query latency, locks, and recent traffic changes.",
            ],
            related_terms={
                "database",
                "connection",
                "pool",
                "saturation",
            },
        )

    if any(
        term in text
        for term in (
            "authentication",
            "token validation",
            "invalid token",
            "unauthorized",
            "http 401",
            "http 403",
            "http 503",
        )
    ):
        add_hypothesis(
            hypothesis=(
                "An authentication or token-validation failure may "
                "be contributing to request errors."
            ),
            rationale=(
                "Incident text contains authentication, token, or "
                "HTTP error signals. The failing component is not yet confirmed."
            ),
            checks=[
                "Compare error rates by endpoint and HTTP status code.",
                "Check token expiry, issuer, audience, signing keys, and clock skew.",
                "Inspect authentication-service health and recent configuration changes.",
            ],
            related_terms={
                "authentication",
                "token",
                "validation",
                "http",
                "503",
            },
        )

    if any(
        term in text
        for term in (
            "payment",
            "provider timeout",
            "gateway timeout",
            "http 504",
            "timeout",
        )
    ):
        add_hypothesis(
            hypothesis=(
                "A slow or unavailable downstream payment provider "
                "may be contributing to request timeouts."
            ),
            rationale=(
                "Incident text contains payment or timeout signals. "
                "Downstream failure has not been independently verified."
            ),
            checks=[
                "Measure downstream provider latency and timeout rates.",
                "Check retry counts, circuit-breaker state, and connection errors.",
                "Compare provider health with application error timestamps.",
            ],
            related_terms={
                "payment",
                "provider",
                "timeout",
                "latency",
            },
        )

    if not hypotheses:
        hypotheses.append(
            {
                "hypothesis": (
                    "The available evidence is insufficient to identify "
                    "a specific failure mechanism."
                ),
                "status": "unconfirmed",
                "rationale": (
                    "No recognized signal pattern was found in the "
                    "incident fields and retrieved documents."
                ),
                "supporting_sources": [],
                "checks_to_validate": [
                    "Collect timestamps, affected endpoints, and representative error logs.",
                    "Compare affected and healthy service metrics.",
                    "Review recent deployments and dependency health.",
                ],
            }
        )

    return hypotheses


def investigate_incident(
    incident_input: Any,
    evidence_limit: int = 5,
) -> dict[str, Any]:
    """
    Create an evidence-linked investigation report for an incident.

    This is a deterministic local baseline, not an LLM-generated diagnosis.
    It does not execute remediation or claim that a hypothesis is proven.
    """
    if evidence_limit < 1 or evidence_limit > 10:
        raise ValueError("evidence_limit must be between 1 and 10")

    incident = _to_dict(incident_input)

    if not incident:
        raise ValueError("incident_input must be a non-empty incident object")

    incident_id = (
        incident.get("incident_id")
        or incident.get("id")
        or incident.get("incident_number")
        or "unknown"
    )

    title = (
        incident.get("title")
        or incident.get("name")
        or "Incident investigation"
    )

    severity = incident.get("severity", "unknown")
    status = incident.get("status", "unknown")
    service = (
        incident.get("affected_service")
        or incident.get("service")
        or "unknown"
    )

    observations, observation_text = _collect_observations(incident)

    query = " ".join(
        [
            str(title),
            str(service),
            str(severity),
            _incident_text(incident),
            " ".join(observation_text),
        ]
    )

    retrieved = search_knowledge(query, limit=evidence_limit)

    evidence = [
        {
            "evidence_id": f"E{index:02d}",
            "document_id": item["document_id"],
            "source": item["source"],
            "relevance_score": item["score"],
            "matched_terms": item["matched_terms"],
            "excerpt": re.sub(
                r"\s+",
                " ",
                str(item["content"]),
            )[:500],
        }
        for index, item in enumerate(retrieved, start=1)
    ]

    hypotheses = _build_hypotheses(
        incident=incident,
        observations=observations,
        evidence=retrieved,
    )

    if evidence:
        evidence_status = "local_documents_found"
    else:
        evidence_status = "no_matching_local_documents"

    return {
        "incident_id": str(incident_id),
        "title": str(title),
        "severity": str(severity),
        "status": str(status),
        "affected_service": str(service),
        "investigation_type": "deterministic_local",
        "summary": (
            f"Investigated incident {incident_id} affecting {service}. "
            f"Extracted {len(observations)} observation(s) and "
            f"retrieved {len(evidence)} local evidence document(s). "
            "Root cause remains unconfirmed."
        ),
        "observed_facts": observations,
        "hypotheses": hypotheses,
        "evidence_status": evidence_status,
        "evidence": evidence,
        "recommended_next_steps": [
            "Validate each hypothesis against live telemetry and timestamps.",
            "Review the referenced runbooks before taking operational action.",
            "Record additional evidence that supports or contradicts each hypothesis.",
            "Require authorized human approval before executing any remediation.",
        ],
        "limitations": [
            "This investigator uses deterministic rules and lexical retrieval, not an LLM.",
            "Retrieved document relevance does not prove that a document describes this incident.",
            "A hypothesis is not a confirmed root cause.",
            "Simulator-supplied suspected root cause fields are not treated as proof.",
            "No remediation action is executed.",
        ],
    }
