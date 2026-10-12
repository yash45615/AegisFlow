
import json
import sqlite3

import pytest

import app.storage.audit_store as store


@pytest.fixture
def temporary_database(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    database_path = data_dir / "aegisflow.db"

    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(store, "DATABASE_PATH", database_path)

    return database_path


def test_record_and_retrieve_incident(temporary_database):
    saved = store.record_incident(
        scenario="database_saturation",
        payload={"severity": "high", "source": "test"},
    )

    results = store.list_incidents(limit=10)

    assert len(results) == 1
    assert results[0]["incident_id"] == saved["incident_id"]
    assert results[0]["scenario"] == "database_saturation"
    assert results[0]["payload"]["severity"] == "high"


def test_recording_incident_creates_audit_event(temporary_database):
    store.record_incident(
        scenario="auth_failure",
        payload={"severity": "medium"},
    )

    events = store.list_audit_events()

    assert len(events) == 1
    assert events[0]["event_type"] == "incident_simulated"
    assert events[0]["details"]["scenario"] == "auth_failure"


def test_record_custom_audit_event(temporary_database):
    event = store.record_audit_event(
        "remediation_plan_created",
        {"execution_performed": False},
    )

    events = store.list_audit_events()

    assert len(events) == 1
    assert events[0]["event_id"] == event["event_id"]
    assert events[0]["details"]["execution_performed"] is False


def test_incident_history_limit(temporary_database):
    for _ in range(3):
        store.record_incident(
            scenario="payment_timeout",
            payload={"status": "simulated"},
        )

    assert len(store.list_incidents(limit=2)) == 2


def test_records_survive_reopening_database(temporary_database):
    store.record_incident(
        scenario="database_saturation",
        payload={"persistent": True},
    )

    # A fresh connection reads the same database file.
    with sqlite3.connect(temporary_database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM incidents"
        ).fetchone()

    assert json.loads(row[0])["persistent"] is True


def test_empty_database_returns_empty_lists(temporary_database):
    assert store.list_incidents() == []
    assert store.list_audit_events() == []
