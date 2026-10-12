
import pytest

from app.storage import job_store


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(job_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        job_store,
        "DATABASE_PATH",
        tmp_path / "test_aegisflow.db",
    )


@pytest.fixture
def queued_job(isolated_database):
    return job_store.create_job(
        scenario="stage_output_test",
        payload={"test": True},
    )


def test_stage_output_round_trip(queued_job):
    job_id = queued_job["job_id"]
    output = {"summary": "Investigation complete", "score": 0.95}

    saved = job_store.save_pipeline_stage_output(
        job_id,
        "investigation_completed",
        output,
    )
    loaded = job_store.get_pipeline_stage_output(
        job_id,
        "investigation_completed",
    )

    assert saved["output"] == output
    assert loaded is not None
    assert loaded["output"] == output


def test_outputs_for_different_stages_are_preserved(queued_job):
    job_id = queued_job["job_id"]

    job_store.save_pipeline_checkpoint(
        job_id,
        "investigation_completed",
        {"summary": "Investigation result"},
    )
    job_store.save_pipeline_checkpoint(
        job_id,
        "assessment_completed",
        {"severity": "high"},
    )

    investigation = job_store.get_pipeline_stage_output(
        job_id,
        "investigation_completed",
    )
    assessment = job_store.get_pipeline_stage_output(
        job_id,
        "assessment_completed",
    )

    assert investigation is not None
    assert investigation["output"]["summary"] == "Investigation result"

    assert assessment is not None
    assert assessment["output"]["severity"] == "high"


def test_saving_same_stage_updates_its_output(queued_job):
    job_id = queued_job["job_id"]

    job_store.save_pipeline_stage_output(
        job_id,
        "assessment_completed",
        {"severity": "medium"},
    )
    job_store.save_pipeline_stage_output(
        job_id,
        "assessment_completed",
        {"severity": "high"},
    )

    loaded = job_store.get_pipeline_stage_output(
        job_id,
        "assessment_completed",
    )

    assert loaded is not None
    assert loaded["output"] == {"severity": "high"}


def test_missing_stage_output_returns_none(queued_job):
    result = job_store.get_pipeline_stage_output(
        queued_job["job_id"],
        "nonexistent_stage",
    )

    assert result is None


def test_unknown_job_stage_output_is_rejected(isolated_database):
    with pytest.raises(ValueError, match="Unknown job"):
        job_store.save_pipeline_stage_output(
            "unknown-job",
            "investigation_completed",
            {"summary": "test"},
        )


def test_list_stage_outputs_returns_all_stages(queued_job):
    job_id = queued_job["job_id"]

    job_store.save_pipeline_stage_output(
        job_id,
        "investigation_completed",
        {"summary": "done"},
    )
    job_store.save_pipeline_stage_output(
        job_id,
        "assessment_completed",
        {"severity": "high"},
    )

    outputs = job_store.list_pipeline_stage_outputs(job_id)

    assert len(outputs) == 2
    assert {
        item["stage"] for item in outputs
    } == {
        "investigation_completed",
        "assessment_completed",
    }
