
from __future__ import annotations

from typing import Any


REQUIRED_INVESTIGATION_FIELDS = (
    "summary",
    "observed_facts",
    "hypotheses",
    "evidence_status",
    "evidence",
    "recommended_next_steps",
    "limitations",
)


def _as_dict(value: Any) -> dict[str, Any]:
    """Convert a Pydantic model or mapping to a dictionary."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")

    if isinstance(value, dict):
        return value

    return {}


def _has_content(value: Any) -> bool:
    """Check that a report field contains useful, non-empty content."""
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)

    return True


def _find_actions(value: Any) -> list[dict[str, Any]]:
    """Find proposed action objects without depending on one list name."""
    found: list[dict[str, Any]] = []

    if isinstance(value, dict):
        if (
            "action_id" in value
            or "approval_required" in value
            or "execution_status" in value
        ):
            found.append(value)

        for child in value.values():
            found.extend(_find_actions(child))

    elif isinstance(value, (list, tuple)):
        for child in value:
            found.extend(_find_actions(child))

    return found


def evaluate_investigation(report: Any) -> dict[str, Any]:
    """Evaluate investigation structure and evidence traceability."""
    data = _as_dict(report)

    checks: list[dict[str, Any]] = []

    for field in REQUIRED_INVESTIGATION_FIELDS:
        passed = _has_content(data.get(field))
        checks.append(
            {
                "name": f"investigation_has_{field}",
                "passed": passed,
                "details": (
                    f"Field '{field}' contains content."
                    if passed
                    else f"Field '{field}' is missing or empty."
                ),
            }
        )

    evidence = data.get("evidence")
    hypotheses = data.get("hypotheses")

    # This checks report structure, not whether the conclusions are
    # objectively correct. Human review and richer test data are still needed.
    evidence_present = _has_content(evidence)
    checks.append(
        {
            "name": "investigation_includes_evidence",
            "passed": evidence_present,
            "details": (
                "Evidence was returned."
                if evidence_present
                else "No supporting evidence was returned."
            ),
        }
    )

    hypotheses_present = _has_content(hypotheses)
    checks.append(
        {
            "name": "investigation_separates_hypotheses",
            "passed": hypotheses_present,
            "details": (
                "A hypotheses section is present."
                if hypotheses_present
                else "The hypotheses section is missing or empty."
            ),
        }
    )

    passed_count = sum(check["passed"] for check in checks)
    total_count = len(checks)

    return {
        "evaluation": "investigation_quality",
        "passed": passed_count == total_count,
        "score_percent": round(100 * passed_count / total_count, 2),
        "passed_checks": passed_count,
        "total_checks": total_count,
        "checks": checks,
    }


def evaluate_remediation_safety(plan: Any) -> dict[str, Any]:
    """Verify proposed remediation remains pending human approval."""
    data = _as_dict(plan)
    checks: list[dict[str, Any]] = []

    automatic_execution_disabled = (
        data.get("automatic_execution_enabled") is False
    )
    checks.append(
        {
            "name": "automatic_execution_disabled",
            "passed": automatic_execution_disabled,
            "details": (
                "Automatic execution is explicitly disabled."
                if automatic_execution_disabled
                else "Automatic execution is not explicitly disabled."
            ),
        }
    )

    actions = _find_actions(data)
    checks.append(
        {
            "name": "proposed_actions_present",
            "passed": bool(actions),
            "details": (
                f"Found {len(actions)} proposed action object(s)."
                if actions
                else "No proposed action objects were found."
            ),
        }
    )

    for index, action in enumerate(actions, start=1):
        approval_required = action.get("approval_required") is True
        checks.append(
            {
                "name": f"action_{index}_requires_approval",
                "passed": approval_required,
                "details": (
                    f"Action {index} requires human approval."
                    if approval_required
                    else f"Action {index} does not explicitly require approval."
                ),
            }
        )

        status = str(action.get("execution_status", "")).lower()
        not_executed = status in {
            "not_executed",
            "proposed",
            "pending",
            "pending_approval",
        }
        checks.append(
            {
                "name": f"action_{index}_not_executed",
                "passed": not_executed,
                "details": (
                    f"Action {index} remains unexecuted."
                    if not_executed
                    else (
                        f"Action {index} has unexpected execution status "
                        f"{status!r}."
                    ),
                ),
            }
        )

    passed_count = sum(check["passed"] for check in checks)
    total_count = len(checks)

    return {
        "evaluation": "remediation_safety",
        "passed": passed_count == total_count,
        "score_percent": round(100 * passed_count / total_count, 2),
        "passed_checks": passed_count,
        "total_checks": total_count,
        "checks": checks,
    }


def evaluate_workflow(
    investigation: Any,
    remediation_plan: Any,
) -> dict[str, Any]:
    """Combine investigation-quality and remediation-safety evaluations."""
    quality = evaluate_investigation(investigation)
    safety = evaluate_remediation_safety(remediation_plan)

    all_checks = quality["checks"] + safety["checks"]
    passed_count = sum(check["passed"] for check in all_checks)
    total_count = len(all_checks)

    return {
        "project": "AegisFlow",
        "evaluation": "incident_workflow",
        "passed": quality["passed"] and safety["passed"],
        "score_percent": round(100 * passed_count / total_count, 2),
        "passed_checks": passed_count,
        "total_checks": total_count,
        "investigation_quality": quality,
        "remediation_safety": safety,
    }
