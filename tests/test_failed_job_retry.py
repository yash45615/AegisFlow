
from __future__ import annotations

import app.storage.job_store as store


def configure_test_database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        store,
        "DATABASE_PATH",
        tmp_path / "test_aegisflow.db",
    )


def test_retry_failed_job_preserves_job_id_and_outputs(
    tmp_path, monkeypatch
):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="database_saturation",
        payload={"service": "payments"},
    )
    job_id = job["job_id"]

    assert store.mark_job_running(job_id)
    store.save_pipeline_stage_output(
        job_id,
        "investigation_completed",
        {"summary": "Pool exhausted"},
    )
    store.fail_job(job_id, "Temporary failure")

    assert store.retry_failed_job(job_id) is True

    retried = store.get_job(job_id)
    saved = store.get_pipeline_stage_output(
        job_id, "investigation_completed"
    )

    assert retried is not None
    assert retried["job_id"] == job_id
    assert retried["status"] == "queued"
    assert retried["error"] is None
    assert saved is not None
    assert saved["output"] == {"summary": "Pool exhausted"}


def test_retry_does_not_requeue_non_failed_jobs(
    tmp_path, monkeypatch
):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="auth_failure",
        payload={},
    )

    assert store.retry_failed_job(job["job_id"]) is False
    assert store.get_job(job["job_id"])["status"] == "queued"
