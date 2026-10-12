from __future__ import annotations

import app.jobs.incident_jobs as jobs
import app.storage.job_store as store


def configure_test_database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        store,
        "DATABASE_PATH",
        tmp_path / "test_aegisflow.db",
    )


def test_stage_output_survives_reconnection(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="database_saturation",
        payload={"service": "payments"},
    )
    output = {"summary": "Database connections exhausted"}

    store.save_pipeline_stage_output(
        job["job_id"],
        "investigation_completed",
        output,
    )

    retrieved = store.get_pipeline_stage_output(
        job["job_id"],
        "investigation_completed",
    )

    assert retrieved is not None
    assert retrieved["output"] == output
    assert retrieved["job_id"] == job["job_id"]


def test_pipeline_reuses_saved_stage_outputs(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="database_saturation",
        payload={"service": "payments"},
    )
    job_id = job["job_id"]

    investigation = {"summary": "Pool exhausted"}
    assessment = {"severity": "high"}
    remediation = {"action_count": 2, "actions": []}

    store.save_pipeline_stage_output(
        job_id, jobs.INVESTIGATION_STAGE, investigation
    )
    store.save_pipeline_stage_output(
        job_id, jobs.ASSESSMENT_STAGE, assessment
    )
    store.save_pipeline_stage_output(
        job_id, jobs.REMEDIATION_STAGE, remediation
    )

    def unexpected_call(*args, **kwargs):
        raise AssertionError("A saved stage was executed again")

    monkeypatch.setattr(jobs, "investigate_incident", unexpected_call)
    monkeypatch.setattr(jobs, "assess_incident", unexpected_call)
    monkeypatch.setattr(jobs, "plan_remediation", unexpected_call)

    result = jobs._investigate_with_retries(
        incident={"scenario": "database_saturation"},
        job_id=job_id,
    )

    assert result == (investigation, assessment, remediation)


def test_pipeline_saves_each_successful_stage(tmp_path, monkeypatch):
    configure_test_database(tmp_path, monkeypatch)

    job = store.create_job(
        scenario="auth_failure",
        payload={"service": "identity"},
    )
    job_id = job["job_id"]

    investigation = {"summary": "Repeated login failures"}
    assessment = {"severity": "medium"}
    remediation = {"action_count": 1, "actions": []}

    monkeypatch.setattr(
        jobs,
        "investigate_incident",
        lambda incident: investigation,
    )
    monkeypatch.setattr(
        jobs,
        "assess_incident",
        lambda incident, investigation: assessment,
    )
    monkeypatch.setattr(
        jobs,
        "plan_remediation",
        lambda investigation: remediation,
    )

    result = jobs._investigate_with_retries(
        incident={"scenario": "auth_failure"},
        job_id=job_id,
    )

    assert result == (investigation, assessment, remediation)

    assert store.get_pipeline_stage_output(
        job_id, jobs.INVESTIGATION_STAGE
    )["output"] == investigation

    assert store.get_pipeline_stage_output(
        job_id, jobs.ASSESSMENT_STAGE
    )["output"] == assessment

    assert store.get_pipeline_stage_output(
        job_id, jobs.REMEDIATION_STAGE
    )["output"] == remediation
