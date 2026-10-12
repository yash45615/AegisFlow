
import app.storage.audit_store as store
from app.investigation.correlation import (
    build_incident_fingerprint,
    compare_incident_signatures,
)


def configure_database(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"

    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(
        store,
        "DATABASE_PATH",
        data_dir / "aegisflow.db",
    )


def test_identical_signatures_have_same_fingerprint():
    first, _ = build_incident_fingerprint(
        "database_saturation",
        {
            "service": "checkout",
            "error_code": "DB_POOL_EXHAUSTED",
            "timestamp": "2026-10-12T10:00:00Z",
        },
    )

    second, _ = build_incident_fingerprint(
        "database_saturation",
        {
            "service": "CHECKOUT",
            "error_code": "db_pool_exhausted",
            "timestamp": "2026-10-12T10:05:00Z",
        },
    )

    assert first == second


def test_different_error_signatures_do_not_match():
    _, first = build_incident_fingerprint(
        "database_saturation",
        {"service": "checkout", "error_code": "POOL_EXHAUSTED"},
    )

    _, second = build_incident_fingerprint(
        "database_saturation",
        {"service": "checkout", "error_code": "CONNECTION_REFUSED"},
    )

    result = compare_incident_signatures(first, second)

    assert result["matching"] is False
    assert result["conflicting_fields"] == ["error_code"]


def test_matching_incidents_share_a_correlation_group(
    tmp_path,
    monkeypatch,
):
    configure_database(tmp_path, monkeypatch)

    payload = {
        "service": "checkout",
        "error_code": "DB_POOL_EXHAUSTED",
    }

    first_incident = store.record_incident(
        "database_saturation",
        payload,
    )
    first = store.correlate_incident(
        first_incident["incident_id"],
        "database_saturation",
        payload,
    )

    second_incident = store.record_incident(
        "database_saturation",
        payload,
    )
    second = store.correlate_incident(
        second_incident["incident_id"],
        "database_saturation",
        payload,
    )

    assert first["correlation_id"] == second["correlation_id"]
    assert second["is_correlated"] is True
    assert first_incident["incident_id"] in (
        second["related_incident_ids"]
    )


def test_different_errors_get_separate_groups(tmp_path, monkeypatch):
    configure_database(tmp_path, monkeypatch)

    first_payload = {
        "service": "checkout",
        "error_code": "DB_POOL_EXHAUSTED",
    }
    second_payload = {
        "service": "checkout",
        "error_code": "CONNECTION_REFUSED",
    }

    first_incident = store.record_incident(
        "database_saturation",
        first_payload,
    )
    first = store.correlate_incident(
        first_incident["incident_id"],
        "database_saturation",
        first_payload,
    )

    second_incident = store.record_incident(
        "database_saturation",
        second_payload,
    )
    second = store.correlate_incident(
        second_incident["incident_id"],
        "database_saturation",
        second_payload,
    )

    assert first["correlation_id"] != second["correlation_id"]
    assert second["is_correlated"] is False


def test_scenario_alone_does_not_create_duplicate_group(
    tmp_path,
    monkeypatch,
):
    configure_database(tmp_path, monkeypatch)

    first_incident = store.record_incident(
        "auth_failure",
        {"scenario": "auth_failure"},
    )
    first = store.correlate_incident(
        first_incident["incident_id"],
        "auth_failure",
        {"scenario": "auth_failure"},
    )

    second_incident = store.record_incident(
        "auth_failure",
        {"scenario": "auth_failure"},
    )
    second = store.correlate_incident(
        second_incident["incident_id"],
        "auth_failure",
        {"scenario": "auth_failure"},
    )

    assert first["correlation_id"] != second["correlation_id"]
    assert second["is_correlated"] is False
