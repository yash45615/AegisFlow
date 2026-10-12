
from __future__ import annotations

import pytest

import app.storage.job_store as store


def configure_test_database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        store,
        "DATABASE_PATH",
        tmp_path / "test_aegisflow.db",
    )


def test_checkpoint_can_be_saved_and_retrieved(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="database_saturation",
        payload={"service": "payments"},
    )

    saved = store.save_pipeline_checkpoint(
        job["job_id"],
        "incident_recorded",
    )
    retrieved = store.get_pipeline_checkpoint(job["job_id"])

    assert saved["stage"] == "incident_recorded"
    assert retrieved is not None
    assert retrieved["job_id"] == job["job_id"]
    assert retrieved["stage"] == "incident_recorded"
    assert retrieved["updated_at"]


def test_checkpoint_updates_to_latest_stage(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="auth_failure",
        payload={},
    )

    store.save_pipeline_checkpoint(
        job["job_id"],
        "incident_recorded",
    )
    store.save_pipeline_checkpoint(
        job["job_id"],
        "analysis_completed",
    )

    checkpoint = store.get_pipeline_checkpoint(job["job_id"])

    assert checkpoint is not None
    assert checkpoint["stage"] == "analysis_completed"


def test_checkpoint_survives_database_reconnection(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="payment_timeout",
        payload={},
    )
    store.save_pipeline_checkpoint(
        job["job_id"],
        "lifecycle_saved",
    )

    # The getter opens a fresh SQLite connection.
    checkpoint = store.get_pipeline_checkpoint(job["job_id"])

    assert checkpoint is not None
    assert checkpoint["stage"] == "lifecycle_saved"


def test_unknown_job_cannot_be_checkpointed(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="unknown job"):
        store.save_pipeline_checkpoint(
            "missing-job",
            "incident_recorded",
        )


def test_missing_checkpoint_returns_none(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    assert store.get_pipeline_checkpoint("missing-job") is None


def test_blank_checkpoint_stage_is_rejected(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="auth_failure",
        payload={},
    )

    with pytest.raises(ValueError, match="cannot be blank"):
        store.save_pipeline_checkpoint(job["job_id"], "   ")
