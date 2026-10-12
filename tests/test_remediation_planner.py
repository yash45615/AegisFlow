import pytest

from app.investigation.investigator import investigate_incident
from app.remediation.planner import plan_remediation


@pytest.fixture
def database_report() -> dict:
    return {
        "incident_id": "TEST-DB-001",
        "affected_service": "orders-api",
        "title": "Database connection pool saturation",
        "observed_facts": [
            "Log/event: Database connection acquisition timeout",
            "Metric/signal: database_pool_waiting=28 connections",
        ],
        "hypotheses": [
            {
                "hypothesis": (
                    "Database connection-pool saturation may be "
                    "contributing to service degradation."
                ),
                "status": "unconfirmed",
                "supporting_sources": [
                    {
                        "document_id": "database-connection-pool",
                        "source": (
                            "data/runbooks/database-connection-pool.md"
                        ),
                    }
                ],
            }
        ],
    }


@pytest.fixture
def auth_report() -> dict:
    return {
        "incident_id": "TEST-AUTH-001",
        "affected_service": "auth-api",
        "title": "Authentication token validation failures",
        "observed_facts": [
            "Log/event: Authentication token validation failed",
        ],
        "hypotheses": [
            {
                "hypothesis": (
                    "An authentication or token-validation failure "
                    "may be contributing to request errors."
                ),
                "status": "unconfirmed",
                "supporting_sources": [],
            }
        ],
    }


@pytest.fixture
def payment_report() -> dict:
    return {
        "incident_id": "TEST-PAY-001",
        "affected_service": "payments-api",
        "title": "Payment provider timeout",
        "observed_facts": [
            "Log/event: Payment provider timeout",
        ],
        "hypotheses": [
            {
                "hypothesis": (
                    "A slow downstream payment provider may be "
                    "contributing to request timeouts."
                ),
                "status": "unconfirmed",
                "supporting_sources": [],
            }
        ],
    }


def test_database_report_generates_database_actions(
    database_report: dict,
) -> None:
    plan = plan_remediation(database_report)

    assert plan["incident_id"] == "TEST-DB-001"
    assert plan["actions"]
    assert any(
        "connection-pool" in action["title"].lower()
        for action in plan["actions"]
    )


def test_auth_report_generates_authentication_actions(
    auth_report: dict,
) -> None:
    plan = plan_remediation(auth_report)

    assert any(
        "authentication" in action["title"].lower()
        for action in plan["actions"]
    )


def test_payment_report_generates_payment_actions(
    payment_report: dict,
) -> None:
    plan = plan_remediation(payment_report)

    assert any(
        "payment" in action["title"].lower()
        for action in plan["actions"]
    )


def test_every_action_requires_approval(
    database_report: dict,
) -> None:
    plan = plan_remediation(database_report)

    assert plan["approval_policy"]["required"] is True
    assert plan["approval_policy"]["approval_granted"] is False

    for action in plan["actions"]:
        assert action["approval_required"] is True
        assert action["execution_status"] == "not_executed"


def test_plan_does_not_enable_automatic_execution(
    database_report: dict,
) -> None:
    plan = plan_remediation(database_report)

    assert plan["automatic_execution_enabled"] is False
    assert plan["plan_status"] == "proposed_pending_human_review"


def test_actions_include_safety_details(
    database_report: dict,
) -> None:
    plan = plan_remediation(database_report)

    for action in plan["actions"]:
        assert action["risk_level"] in {"low", "medium", "high"}
        assert action["preconditions"]
        assert action["steps"]
        assert action["expected_outcome"]
        assert action["rollback"]


def test_plan_preserves_evidence_source_references(
    database_report: dict,
) -> None:
    plan = plan_remediation(database_report)

    first_action = plan["actions"][0]

    assert (
        "data/runbooks/database-connection-pool.md"
        in first_action["evidence_references"]
    )


def test_max_actions_is_respected(
    database_report: dict,
) -> None:
    plan = plan_remediation(database_report, max_actions=1)

    assert plan["action_count"] == 1
    assert len(plan["actions"]) == 1


def test_invalid_max_actions_is_rejected(
    database_report: dict,
) -> None:
    with pytest.raises(ValueError):
        plan_remediation(database_report, max_actions=0)

    with pytest.raises(ValueError):
        plan_remediation(database_report, max_actions=6)


def test_empty_report_is_rejected() -> None:
    with pytest.raises(ValueError):
        plan_remediation({})


def test_unknown_incident_gets_general_plan() -> None:
    report = {
        "incident_id": "TEST-UNKNOWN-001",
        "affected_service": "unknown-service",
        "title": "Unexpected service behavior",
        "observed_facts": ["No recognized failure signal."],
        "hypotheses": [
            {
                "hypothesis": "The failure mechanism is unknown.",
                "status": "unconfirmed",
                "supporting_sources": [],
            }
        ],
    }

    plan = plan_remediation(report)

    assert plan["actions"]
    assert plan["actions"][0]["action_id"] == "GEN-PLAN-001"
