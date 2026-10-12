from __future__ import annotations

from typing import Any


MAX_ACTIONS = 5

RISK_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


def _as_dict(value: Any) -> dict[str, Any]:
    """Normalize a dictionary or Pydantic model."""
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
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return [value]


def _text(value: Any) -> str:
    """Flatten text fields for deterministic signal matching."""
    if isinstance(value, str):
        return value.lower()

    if isinstance(value, dict):
        return " ".join(
            f"{key} {_text(item)}"
            for key, item in value.items()
            if item is not None
        )

    if isinstance(value, (list, tuple)):
        return " ".join(_text(item) for item in value)

    return str(value).lower()


def _evidence_references(
    hypothesis: dict[str, Any],
) -> list[str]:
    """Collect source paths referenced by an investigation hypothesis."""
    references: list[str] = []

    for source in _as_list(hypothesis.get("supporting_sources")):
        source_dict = _as_dict(source)
        path = source_dict.get("source")

        if path and path not in references:
            references.append(str(path))

    return references


def _action(
    *,
    action_id: str,
    title: str,
    purpose: str,
    risk_level: str,
    preconditions: list[str],
    steps: list[str],
    expected_outcome: str,
    rollback: list[str],
    evidence_references: list[str],
) -> dict[str, Any]:
    """Create a consistent, reviewable remediation action."""
    return {
        "action_id": action_id,
        "title": title,
        "purpose": purpose,
        "risk_level": risk_level,
        "preconditions": preconditions,
        "steps": steps,
        "expected_outcome": expected_outcome,
        "rollback": rollback,
        "evidence_references": evidence_references,
        "approval_required": True,
        "execution_status": "not_executed",
    }


def _database_actions(
    references: list[str],
) -> list[dict[str, Any]]:
    return [
        _action(
            action_id="DB-PLAN-001",
            title="Inspect database connection-pool pressure",
            purpose=(
                "Determine whether pool exhaustion correlates with "
                "the observed request failures."
            ),
            risk_level="low",
            preconditions=[
                "Read-only access to application and database metrics.",
                "Incident timestamps and affected service are available.",
            ],
            steps=[
                "Capture active, idle, and waiting connection counts.",
                "Compare pool acquisition latency with request error timestamps.",
                "Inspect database CPU, query latency, locks, and connection limits.",
                "Record the observations and compare them with the investigation evidence.",
            ],
            expected_outcome=(
                "Evidence showing whether connection-pool pressure "
                "is associated with the incident."
            ),
            rollback=[
                "No configuration changes are made by this action.",
                "Close the read-only investigation session when complete.",
            ],
            evidence_references=references,
        ),
        _action(
            action_id="DB-PLAN-002",
            title="Review connection-pool configuration",
            purpose=(
                "Assess whether pool size, acquisition timeout, or "
                "connection lifecycle settings need a controlled change."
            ),
            risk_level="medium",
            preconditions=[
                "DB-PLAN-001 findings have been reviewed.",
                "Database capacity and connection limits are documented.",
                "A tested configuration change and maintenance window are available.",
                "An authorized service owner approves the proposed change.",
            ],
            steps=[
                "Compare current pool settings with workload and database limits.",
                "Prepare a minimal configuration change in a non-production environment.",
                "Run load tests and verify that database capacity is not exceeded.",
                "Submit the change for separate human approval before production use.",
            ],
            expected_outcome=(
                "A validated configuration proposal with measured "
                "capacity and performance impact."
            ),
            rollback=[
                "Record the current configuration before any approved change.",
                "Prepare a tested restoration of the previous configuration.",
                "Define rollback thresholds and the responsible operator before deployment.",
            ],
            evidence_references=references,
        ),
    ]


def _authentication_actions(
    references: list[str],
) -> list[dict[str, Any]]:
    return [
        _action(
            action_id="AUTH-PLAN-001",
            title="Validate authentication failure signals",
            purpose=(
                "Distinguish token-validation problems from authentication "
                "service outages or unrelated HTTP errors."
            ),
            risk_level="low",
            preconditions=[
                "Read-only access to authentication logs and service health.",
                "Sensitive tokens and secrets are redacted from diagnostic output.",
            ],
            steps=[
                "Group errors by endpoint, HTTP status, and timestamp.",
                "Check token expiry, issuer, audience, signing-key identifiers, and clock skew.",
                "Compare authentication-service health with application error rates.",
                "Review recent deployments and configuration changes.",
            ],
            expected_outcome=(
                "A more specific, evidence-backed classification of "
                "the authentication failure."
            ),
            rollback=[
                "No authentication settings are changed.",
                "Remove any temporary diagnostic artifacts containing sensitive metadata.",
            ],
            evidence_references=references,
        ),
        _action(
            action_id="AUTH-PLAN-002",
            title="Prepare a controlled authentication configuration review",
            purpose=(
                "Identify configuration drift and prepare a reviewed correction "
                "if the investigation confirms a configuration problem."
            ),
            risk_level="high",
            preconditions=[
                "Authentication failure evidence has been reviewed by the service owner.",
                "The intended issuer, audience, key configuration, and identity-provider settings are verified.",
                "A tested previous configuration is available.",
                "An authorized security or service owner approves any proposed change.",
            ],
            steps=[
                "Compare the deployed configuration with the approved reference.",
                "Document the exact difference and affected services.",
                "Test the proposed correction in a non-production environment.",
                "Prepare a change and rollback plan for human review.",
                "Do not modify signing keys, disable validation, or weaken authentication controls as a workaround.",
            ],
            expected_outcome=(
                "A reviewed configuration-change proposal that preserves "
                "existing authentication security requirements."
            ),
            rollback=[
                "Retain the verified previous configuration.",
                "Document restoration steps and validation checks.",
                "Require an authorized operator to perform any rollback.",
            ],
            evidence_references=references,
        ),
    ]


def _payment_actions(
    references: list[str],
) -> list[dict[str, Any]]:
    return [
        _action(
            action_id="PAY-PLAN-001",
            title="Measure downstream payment-provider latency",
            purpose=(
                "Determine whether provider latency, connectivity, or "
                "timeouts correlate with the incident."
            ),
            risk_level="low",
            preconditions=[
                "Read-only access to application and provider health metrics.",
                "Payment identifiers and customer-sensitive information are redacted.",
            ],
            steps=[
                "Compare provider latency percentiles with application timeout timestamps.",
                "Review connection errors, timeout counts, and provider status.",
                "Inspect retry counts and circuit-breaker events.",
                "Separate failed, successful, and unknown payment outcomes before recommending retries.",
            ],
            expected_outcome=(
                "Evidence identifying whether downstream latency or "
                "connectivity is associated with payment failures."
            ),
            rollback=[
                "No payment requests or provider settings are changed.",
                "Close the read-only diagnostic session after recording findings.",
            ],
            evidence_references=references,
        ),
        _action(
            action_id="PAY-PLAN-002",
            title="Review retry and circuit-breaker policy",
            purpose=(
                "Assess whether timeout and retry behavior is amplifying "
                "provider degradation."
            ),
            risk_level="medium",
            preconditions=[
                "PAY-PLAN-001 findings are available.",
                "Payment idempotency behavior and reconciliation procedures are documented.",
                "A test environment and an approved change process are available.",
            ],
            steps=[
                "Inspect timeout, retry, backoff, and circuit-breaker settings.",
                "Verify that retry behavior cannot create duplicate payment operations.",
                "Test a proposed policy against simulated provider latency and failures.",
                "Document expected behavior and rollback criteria for review.",
            ],
            expected_outcome=(
                "A validated proposal for handling provider degradation "
                "without unsafe duplicate payment attempts."
            ),
            rollback=[
                "Record the current retry and circuit-breaker configuration.",
                "Prepare restoration of the previous tested configuration.",
                "Define payment reconciliation and monitoring checks before any approved rollout.",
            ],
            evidence_references=references,
        ),
    ]


def _general_actions(
    references: list[str],
) -> list[dict[str, Any]]:
    return [
        _action(
            action_id="GEN-PLAN-001",
            title="Collect additional incident evidence",
            purpose=(
                "Reduce uncertainty before selecting a service-specific remediation."
            ),
            risk_level="low",
            preconditions=[
                "The affected service and incident time window are identified where possible.",
                "Read-only telemetry access is available.",
            ],
            steps=[
                "Collect representative error logs and request timestamps.",
                "Compare affected and healthy service metrics.",
                "Review recent deployments and dependency health.",
                "Record which hypotheses are supported, contradicted, or still unknown.",
            ],
            expected_outcome=(
                "A stronger evidence base for selecting a targeted remediation plan."
            ),
            rollback=[
                "No production configuration is changed.",
                "Follow retention and redaction requirements for collected evidence.",
            ],
            evidence_references=references,
        )
    ]


def _select_actions(
    investigation: dict[str, Any],
) -> list[dict[str, Any]]:
    combined_text = _text(
        {
            "title": investigation.get("title"),
            "service": investigation.get("affected_service"),
            "observed_facts": investigation.get("observed_facts"),
            "hypotheses": investigation.get("hypotheses"),
        }
    )

    references: list[str] = []

    for hypothesis in _as_list(investigation.get("hypotheses")):
        for reference in _evidence_references(_as_dict(hypothesis)):
            if reference not in references:
                references.append(reference)

    if any(
        term in combined_text
        for term in (
            "database",
            "connection-pool",
            "connection pool",
            "connection acquisition",
            "pool saturation",
        )
    ):
        return _database_actions(references)

    if any(
        term in combined_text
        for term in (
            "authentication",
            "token validation",
            "token-validation",
            "unauthorized",
            "http 401",
            "http 403",
        )
    ):
        return _authentication_actions(references)

    if any(
        term in combined_text
        for term in (
            "payment",
            "payment provider",
            "downstream provider",
        )
    ):
        return _payment_actions(references)

    return _general_actions(references)


def plan_remediation(
    investigation_report: Any,
    max_actions: int = MAX_ACTIONS,
) -> dict[str, Any]:
    """
    Create a remediation proposal from an investigation report.

    No action is executed or approved by this function.
    """
    investigation = _as_dict(investigation_report)

    if not investigation:
        raise ValueError(
            "investigation_report must be a non-empty report"
        )

    if not 1 <= max_actions <= MAX_ACTIONS:
        raise ValueError(
            f"max_actions must be between 1 and {MAX_ACTIONS}"
        )

    hypotheses = _as_list(investigation.get("hypotheses"))
    all_confirmed = bool(hypotheses) and all(
        _as_dict(hypothesis).get("status") == "confirmed"
        for hypothesis in hypotheses
    )

    actions = _select_actions(investigation)[:max_actions]

    for action in actions:
        action["approval_required"] = True
        action["execution_status"] = "not_executed"

    return {
        "incident_id": str(
            investigation.get("incident_id", "unknown")
        ),
        "affected_service": str(
            investigation.get("affected_service", "unknown")
        ),
        "plan_status": "proposed_pending_human_review",
        "investigation_confidence": (
            "review_required" if not all_confirmed else "hypotheses_confirmed"
        ),
        "automatic_execution_enabled": False,
        "approval_policy": {
            "required": True,
            "approval_granted": False,
            "approver": None,
            "approved_at": None,
            "note": (
                "This endpoint only creates a plan. It does not provide "
                "an approval mechanism or execute actions."
            ),
        },
        "action_count": len(actions),
        "actions": actions,
        "safety_notes": [
            "Treat recommendations as proposals, not commands to execute.",
            "Unconfirmed hypotheses must be validated before corrective changes.",
            "High-risk actions require explicit review by an authorized owner.",
            "Verify backups, capacity, monitoring, and rollback readiness where applicable.",
            "Never expose secrets, tokens, or customer-sensitive information in evidence.",
        ],
    }
