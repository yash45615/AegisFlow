import pytest

from app.investigation.investigator import investigate_incident


@pytest.fixture
def database_incident() -> dict:
    return {
        "incident_id": "TEST-DB-001",
        "title": "Database connection pool saturation",
        "severity": "high",
        "status": "investigating",
        "affected_service": "orders-api",
        "logs": [
            {
                "timestamp": "2026-10-12T10:00:00Z",
                "level": "ERROR",
                "message": "Database connection acquisition timeout",
            },
            {
                "timestamp": "2026-10-12T10:00:05Z",
                "level": "ERROR",
                "message": "Connection pool has no available connections",
            },
        ],
        "metrics": [
            {
                "name": "database_pool_waiting",
                "value": 28,
                "unit": "connections",
            },
            {
                "name": "request_error_rate",
                "value": 0.24,
                "unit": "ratio",
            },
        ],
        "suspected_root_cause": (
            "A recent deployment caused a connection leak."
        ),
    }


def test_investigation_returns_report(database_incident: dict) -> None:
    report = investigate_incident(database_incident)

    assert report["incident_id"] == "TEST-DB-001"
    assert report["affected_service"] == "orders-api"
    assert report["investigation_type"] == "deterministic_local"
    assert report["observed_facts"]
    assert report["hypotheses"]
    assert report["recommended_next_steps"]


def test_report_contains_observed_telemetry(
    database_incident: dict,
) -> None:
    report = investigate_incident(database_incident)

    combined_facts = " ".join(report["observed_facts"]).lower()

    assert "connection acquisition timeout" in combined_facts
    assert "database_pool_waiting" in combined_facts


def test_database_signal_generates_unconfirmed_hypothesis(
    database_incident: dict,
) -> None:
    report = investigate_incident(database_incident)

    assert any(
        "connection-pool saturation" in item["hypothesis"].lower()
        and item["status"] == "unconfirmed"
        for item in report["hypotheses"]
    )


def test_evidence_has_source_references(
    database_incident: dict,
) -> None:
    report = investigate_incident(database_incident)

    for evidence in report["evidence"]:
        assert evidence["evidence_id"]
        assert evidence["document_id"]
        assert evidence["source"].endswith(".md")
        assert isinstance(evidence["matched_terms"], list)


def test_suspected_root_cause_is_not_proven(
    database_incident: dict,
) -> None:
    report = investigate_incident(database_incident)

    assert all(
        hypothesis["status"] == "unconfirmed"
        for hypothesis in report["hypotheses"]
    )

    assert "root cause remains unconfirmed" in report["summary"].lower()


def test_report_does_not_execute_remediation(
    database_incident: dict,
) -> None:
    report = investigate_incident(database_incident)

    assert any(
        "no remediation action is executed" in limitation.lower()
        for limitation in report["limitations"]
    )


def test_no_signal_produces_general_hypothesis() -> None:
    report = investigate_incident(
        {
            "incident_id": "TEST-UNKNOWN-001",
            "title": "Unexpected service behavior",
            "severity": "medium",
            "status": "investigating",
            "affected_service": "unknown-service",
        }
    )

    assert report["observed_facts"]
    assert report["hypotheses"]
    assert report["hypotheses"][0]["status"] == "unconfirmed"


def test_evidence_limit_must_be_between_one_and_ten() -> None:
    incident = {
        "incident_id": "TEST-001",
        "title": "Test incident",
    }

    with pytest.raises(ValueError):
        investigate_incident(incident, evidence_limit=0)

    with pytest.raises(ValueError):
        investigate_incident(incident, evidence_limit=11)


def test_empty_incident_is_rejected() -> None:
    with pytest.raises(ValueError):
        investigate_incident({})
