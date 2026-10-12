import pytest

from app.simulator.incident_simulator import simulate_incident


@pytest.mark.parametrize(
    "scenario,expected_service",
    [
        ("database_saturation", "database"),
        ("auth_failure", "auth"),
        ("payment_timeout", "payment"),
    ],
)
def test_scenario_has_expected_service(
    scenario: str,
    expected_service: str,
) -> None:
    incident = simulate_incident(scenario)

    assert expected_service in [
        service.value for service in incident.affected_services
    ]
    assert incident.incident_id.startswith("INC-")
    assert incident.logs
    assert incident.metrics


def test_database_saturation_contains_connection_evidence() -> None:
    incident = simulate_incident("database_saturation")
    messages = " ".join(log.message.lower() for log in incident.logs)

    assert "connection" in messages
    assert "timeout" in messages


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown scenario"):
        simulate_incident("unknown_scenario")
