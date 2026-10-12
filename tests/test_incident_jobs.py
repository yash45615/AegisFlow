
from __future__ import annotations

import app.storage.job_store as store


def configure_test_database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        store,
        "DATABASE_PATH",
        tmp_path / "test_aegisflow.db",
    )


def test_create_job_starts_queued(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="database_saturation",
        payload={"service": "payments"},
    )

    assert job["job_id"]
    assert job["status"] == "queued"
    assert job["scenario"] == "database_saturation"
    assert job["payload"] == {"service": "payments"}
    assert job["result"] is None


def test_job_can_complete(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="payment_timeout",
        payload={"service": "payments"},
    )

    store.mark_job_running(job["job_id"])
    store.complete_job(
        job["job_id"],
        {"incident_id": "incident-123"},
    )

    saved = store.get_job(job["job_id"])

    assert saved is not None
    assert saved["status"] == "completed"
    assert saved["result"]["incident_id"] == "incident-123"
    assert saved["started_at"] is not None
    assert saved["completed_at"] is not None


def test_job_can_fail(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="auth_failure",
        payload={},
    )

    store.mark_job_running(job["job_id"])
    store.fail_job(job["job_id"], "Example processing failure")

    saved = store.get_job(job["job_id"])

    assert saved is not None
    assert saved["status"] == "failed"
    assert "Example processing failure" in saved["error"]


def test_missing_job_returns_none(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    assert store.get_job("missing-job-id") is None


def test_interrupted_jobs_are_recovered(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="database_saturation",
        payload={},
    )
    store.mark_job_running(job["job_id"])

    recovered = store.recover_interrupted_jobs()
    saved = store.get_job(job["job_id"])

    assert recovered == 1
    assert saved is not None
    assert saved["status"] == "failed"
    assert "restart" in saved["error"].lower()
