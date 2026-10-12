
from __future__ import annotations

from typing import Any


def _to_dict(value: Any) -> dict[str, Any]:
    """Convert common model outputs into dictionaries."""
    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        result = value.model_dump(mode="json")
        return result if isinstance(result, dict) else {}

    if hasattr(value, "dict") and callable(value.dict):
        result = value.dict()
        return result if isinstance(result, dict) else {}

    return {}


def _first_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return None


def _severity(value: Any) -> str:
    if value is None:
        return "SEV-3"

    normalized = str(value).strip().upper().replace("_", "-")

    aliases = {
        "SEV-1": "SEV-1",
        "P1": "SEV-1",
        "CRITICAL": "SEV-1",
        "SEV-2": "SEV-2",
        "P2": "SEV-2",
        "HIGH": "SEV-2",
        "SEV-3": "SEV-3",
        "P3": "SEV-3",
        "MEDIUM": "SEV-3",
        "MODERATE": "SEV-3",
        "SEV-4": "SEV-4",
        "P4": "SEV-4",
        "LOW": "SEV-4",
        "INFO": "SEV-4",
        "INFORMATIONAL": "SEV-4",
    }

    return aliases.get(normalized, "SEV-3")


def _evidence_items(investigation: dict[str, Any]) -> list[Any]:
    """Find evidence using common investigation response field names."""
    for key in (
        "evidence",
        "supporting_evidence",
        "sources",
        "documents",
        "retrieved_documents",
        "citations",
    ):
        value = investigation.get(key)
        if isinstance(value, list):
            return value

    findings = investigation.get("findings")
    if isinstance(findings, list):
        return findings

    return []


def _citation(item: Any, index: int) -> dict[str, Any]:
    """Normalize a real evidence item without inventing a source."""
    if isinstance(item, str):
        return {
            "evidence_id": f"E{index}",
            "source": None,
            "excerpt": item[:500],
        }

    item = _to_dict(item)

    source = _first_value(
        item,
        "source",
        "path",
        "file",
        "document",
        "title",
        "filename",
        "source_file",
    )

    evidence_id = _first_value(
        item,
        "evidence_id",
        "id",
        "chunk_id",
    )

    excerpt = _first_value(
        item,
        "excerpt",
        "text",
        "content",
        "snippet",
        "summary",
    )

    return {
        "evidence_id": str(evidence_id or f"E{index}"),
        "source": str(source) if source else None,
        "excerpt": str(excerpt)[:500] if excerpt is not None else None,
    }


def assess_incident(
    incident: Any,
    investigation: Any,
) -> dict[str, Any]:
    """
    Produce an explainable incident assessment.

    The confidence score is heuristic, not a calibrated probability.
    Missing severity defaults provisionally to SEV-3.
    """
    incident_data = _to_dict(incident)
    investigation_data = _to_dict(investigation)

    # Support common wrapped response formats.
    for key in ("incident", "data", "result"):
        nested = incident_data.get(key)
        if isinstance(nested, dict):
            incident_data = {**incident_data, **nested}

    for key in ("investigation", "result", "analysis"):
        nested = investigation_data.get(key)
        if isinstance(nested, dict):
            investigation_data = {**investigation_data, **nested}

    severity_value = _first_value(
        incident_data,
        "severity",
        "priority",
        "incident_severity",
    )

    if severity_value is None:
        severity_value = _first_value(
            investigation_data,
            "severity",
            "priority",
        )

    severity = _severity(severity_value)

    root_cause = _first_value(
        investigation_data,
        "root_cause",
        "likely_root_cause",
        "probable_cause",
        "likely_cause",
        "hypothesis",
    )

    if root_cause is None:
        root_cause = _first_value(
            investigation_data,
            "summary",
            "conclusion",
        )

    evidence = [
        _citation(item, index)
        for index, item in enumerate(
            _evidence_items(investigation_data),
            start=1,
        )
    ]

    usable_evidence = [
        item
        for item in evidence
        if item["source"] or item["excerpt"]
    ]

    confidence_score = 0.20

    if root_cause:
        confidence_score += 0.25

    confidence_score += min(len(usable_evidence), 3) * 0.15

    if any(item["source"] for item in usable_evidence):
        confidence_score += 0.10

    confidence_score = round(min(confidence_score, 0.85), 2)

    if confidence_score >= 0.70:
        confidence_label = "stronger_support"
    elif confidence_score >= 0.45:
        confidence_label = "moderate_support"
    else:
        confidence_label = "limited_support"

    limitations = []

    if not root_cause:
        limitations.append(
            "No explicit root-cause hypothesis was provided."
        )

    if not usable_evidence:
        limitations.append(
            "No usable supporting evidence was found."
        )

    if severity_value is None:
        limitations.append(
            "Severity was not supplied; SEV-3 is a provisional default."
        )

    return {
        "severity": severity,
        "severity_source": (
            "incident_or_investigation_input"
            if severity_value is not None
            else "provisional_default"
        ),
        "root_cause_hypothesis": (
            str(root_cause) if root_cause else None
        ),
        "confidence": {
            "score": confidence_score,
            "label": confidence_label,
            "method": "heuristic_not_calibrated_probability",
        },
        "evidence_citations": usable_evidence,
        "limitations": limitations,
        "human_review_required": True,
    }
