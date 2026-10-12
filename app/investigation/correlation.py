
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


SIGNATURE_FIELDS = (
    "service",
    "service_name",
    "component",
    "resource",
    "endpoint",
    "error",
    "error_type",
    "error_code",
    "symptom",
)


def _normalize_value(value: Any) -> str | None:
    """Normalize a value for stable, case-insensitive comparison."""
    if value is None:
        return None

    if isinstance(value, (dict, list, tuple)):
        normalized = json.dumps(
            value,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
    else:
        normalized = str(value)

    normalized = re.sub(r"\s+", " ", normalized).strip().casefold()
    return normalized or None


def build_incident_signature(
    scenario: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Build a normalized signature from stable incident fields."""
    signature: dict[str, str] = {}

    normalized_scenario = _normalize_value(scenario)
    if normalized_scenario:
        signature["scenario"] = normalized_scenario

    for field in SIGNATURE_FIELDS:
        normalized_value = _normalize_value(payload.get(field))

        if normalized_value:
            signature[field] = normalized_value

    return signature


def build_incident_fingerprint(
    scenario: str,
    payload: dict[str, Any],
) -> tuple[str, dict[str, str]]:
    """
    Return the SHA-256 fingerprint and normalized signature.

    The tuple return format is intentional: existing AegisFlow code
    expects to unpack this function into fingerprint and signature.
    """
    signature = build_incident_signature(scenario, payload)

    serialized = json.dumps(
        signature,
        sort_keys=True,
        separators=(",", ":"),
    )

    fingerprint = hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()

    return fingerprint, signature


def compare_incident_signatures(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    """Compare two signatures without treating scenario alone as a match."""
    first_normalized = {
        str(key): normalized
        for key, value in first.items()
        if (normalized := _normalize_value(value)) is not None
    }

    second_normalized = {
        str(key): normalized
        for key, value in second.items()
        if (normalized := _normalize_value(value)) is not None
    }

    first_scenario = first_normalized.get("scenario")
    second_scenario = second_normalized.get("scenario")

    same_scenario = (
        first_scenario is not None
        and first_scenario == second_scenario
    )

    shared_keys = set(first_normalized) & set(second_normalized)

    # Scenario provides context, but isn't a stable identifier by itself.
    meaningful_shared_keys = shared_keys - {"scenario"}

    shared_fields = sorted(
        key
        for key in meaningful_shared_keys
        if first_normalized[key] == second_normalized[key]
    )

    conflicting_fields = sorted(
        key
        for key in meaningful_shared_keys
        if first_normalized[key] != second_normalized[key]
    )

    same_signature = first_normalized == second_normalized

    matching = (
        same_scenario
        and bool(shared_fields)
        and not conflicting_fields
        and same_signature
    )

    return {
        "matching": matching,
        "same_scenario": same_scenario,
        "shared_fields": shared_fields,
        "conflicting_fields": conflicting_fields,
        "same_signature": same_signature,
        "first_signature": first_normalized,
        "second_signature": second_normalized,
    }
