
from app.investigation.assessment import assess_incident


def test_assessment_normalizes_severity():
    result = assess_incident(
        {"severity": "critical"},
        {"root_cause": "Database connection pool exhaustion"},
    )

    assert result["severity"] == "SEV-1"
    assert result["severity_source"] == "incident_or_investigation_input"


def test_assessment_includes_evidence_citations():
    result = assess_incident(
        {"severity": "high"},
        {
            "root_cause": "Database connection pool exhaustion",
            "evidence": [
                {
                    "source": "database_runbook.md",
                    "text": "Connection pool utilization reached its limit.",
                }
            ],
        },
    )

    assert result["root_cause_hypothesis"] == (
        "Database connection pool exhaustion"
    )
    assert len(result["evidence_citations"]) == 1
    assert result["evidence_citations"][0]["source"] == (
        "database_runbook.md"
    )


def test_assessment_does_not_invent_root_cause():
    result = assess_incident({}, {"evidence": []})

    assert result["root_cause_hypothesis"] is None
    assert result["severity"] == "SEV-3"
    assert result["severity_source"] == "provisional_default"
    assert result["limitations"]


def test_confidence_is_bounded_and_disclosed():
    result = assess_incident(
        {"severity": "medium"},
        {
            "root_cause": "Authentication service unavailable",
            "evidence": [
                {"source": "auth_runbook.md", "text": "Auth timeout"},
                {"source": "incident-001.md", "text": "Timeout spike"},
                {"source": "incident-002.md", "text": "Service errors"},
                {"source": "incident-003.md", "text": "More evidence"},
            ],
        },
    )

    confidence = result["confidence"]

    assert 0.0 <= confidence["score"] <= 1.0
    assert confidence["method"] == (
        "heuristic_not_calibrated_probability"
    )
    assert result["human_review_required"] is True


def test_severity_aliases():
    cases = {
        "P1": "SEV-1",
        "HIGH": "SEV-2",
        "MEDIUM": "SEV-3",
        "LOW": "SEV-4",
    }

    for raw, expected in cases.items():
        result = assess_incident({"severity": raw}, {})
        assert result["severity"] == expected


def test_wrapped_investigation_response():
    result = assess_incident(
        {"incident": {"severity": "P2"}},
        {
            "investigation": {
                "root_cause": "Payment service timeout",
                "evidence": [
                    {
                        "id": "E-101",
                        "source": "payments.md",
                        "excerpt": "Timeout errors increased.",
                    }
                ],
            }
        },
    )

    assert result["severity"] == "SEV-2"
    assert result["root_cause_hypothesis"] == "Payment service timeout"
    assert result["evidence_citations"][0]["evidence_id"] == "E-101"
