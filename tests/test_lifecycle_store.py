
import app.storage.audit_store as store


def test_lifecycle_can_be_saved_and_retrieved(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(
        store,
        "DATABASE_PATH",
        data_dir / "aegisflow.db",
    )

    incident = store.record_incident(
        "database_saturation",
        {"severity": "high"},
    )

    lifecycle = store.save_lifecycle(
        incident_id=incident["incident_id"],
        scenario="database_saturation",
        investigation={"root_cause": "connection pool saturation"},
        remediation={"actions": ["review connection pool limits"]},
    )

    result = store.get_lifecycle(lifecycle["lifecycle_id"])

    assert result is not None
    assert result["incident_id"] == incident["incident_id"]
    assert result["scenario"] == "database_saturation"
    assert result["investigation"]["root_cause"] == (
        "connection pool saturation"
    )
    assert result["status"] == "awaiting_human_review"


def test_unknown_lifecycle_returns_none(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(
        store,
        "DATABASE_PATH",
        data_dir / "aegisflow.db",
    )

    assert store.get_lifecycle("missing-id") is None


def test_lifecycle_listing(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(
        store,
        "DATABASE_PATH",
        data_dir / "aegisflow.db",
    )

    incident = store.record_incident(
        "auth_failure",
        {"severity": "medium"},
    )

    store.save_lifecycle(
        incident_id=incident["incident_id"],
        scenario="auth_failure",
        investigation={"findings": []},
        remediation={"actions": []},
    )

    results = store.list_lifecycles()

    assert len(results) == 1
    assert results[0]["scenario"] == "auth_failure"
