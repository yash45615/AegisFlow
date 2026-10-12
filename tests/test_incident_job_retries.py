
from unittest.mock import call, patch

import pytest

from app.jobs import incident_jobs


@pytest.fixture
def incident():
    return {
        "incident_id": "incident-test-001",
        "scenario": "database_saturation",
        "service": "orders-api",
    }


def test_transient_failure_retries_and_then_succeeds(incident):
    investigation = {"summary": "Database connections are saturated"}
    assessment = {"severity": "high"}
    remediation = {"action_count": 0}

    with (
        patch(
            "app.jobs.incident_jobs.investigate_incident",
            side_effect=[TimeoutError("Temporary timeout"), investigation],
        ) as investigate,
        patch(
            "app.jobs.incident_jobs.assess_incident",
            return_value=assessment,
        ) as assess,
        patch(
            "app.jobs.incident_jobs.plan_remediation",
            return_value=remediation,
        ) as plan,
        patch("app.jobs.incident_jobs.time.sleep") as sleep,
    ):
        result = incident_jobs._investigate_with_retries(incident)

    assert result == (investigation, assessment, remediation)
    assert investigate.call_count == 2
    assess.assert_called_once_with(
        incident=incident,
        investigation=investigation,
    )
    plan.assert_called_once_with(investigation)
    sleep.assert_called_once_with(1)


def test_retry_exhaustion_stops_after_three_attempts(incident):
    with (
        patch(
            "app.jobs.incident_jobs.investigate_incident",
            side_effect=TimeoutError("Service timed out"),
        ) as investigate,
        patch("app.jobs.incident_jobs.assess_incident") as assess,
        patch("app.jobs.incident_jobs.plan_remediation") as plan,
        patch("app.jobs.incident_jobs.time.sleep") as sleep,
    ):
        with pytest.raises(TimeoutError, match="Service timed out"):
            incident_jobs._investigate_with_retries(incident)

    assert investigate.call_count == 3
    assert sleep.call_args_list == [call(1), call(2)]
    assess.assert_not_called()
    plan.assert_not_called()


def test_permanent_error_is_not_retried(incident):
    with (
        patch(
            "app.jobs.incident_jobs.investigate_incident",
            side_effect=ValueError("Invalid incident data"),
        ) as investigate,
        patch("app.jobs.incident_jobs.time.sleep") as sleep,
    ):
        with pytest.raises(ValueError, match="Invalid incident data"):
            incident_jobs._investigate_with_retries(incident)

    investigate.assert_called_once_with(incident)
    sleep.assert_not_called()


def test_successful_investigation_does_not_retry(incident):
    investigation = {"summary": "Investigation completed"}
    assessment = {"severity": "medium"}
    remediation = {"action_count": 0}

    with (
        patch(
            "app.jobs.incident_jobs.investigate_incident",
            return_value=investigation,
        ) as investigate,
        patch(
            "app.jobs.incident_jobs.assess_incident",
            return_value=assessment,
        ),
        patch(
            "app.jobs.incident_jobs.plan_remediation",
            return_value=remediation,
        ),
        patch("app.jobs.incident_jobs.time.sleep") as sleep,
    ):
        result = incident_jobs._investigate_with_retries(incident)

    assert result == (investigation, assessment, remediation)
    investigate.assert_called_once_with(incident)
    sleep.assert_not_called()
