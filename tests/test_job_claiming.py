
from app.storage import job_store


def test_queued_job_can_be_claimed_once():
    job = job_store.create_job(
        scenario="database_saturation",
        payload={"service": "orders-api"},
    )

    first_claim = job_store.mark_job_running(job["job_id"])
    second_claim = job_store.mark_job_running(job["job_id"])

    assert first_claim is True
    assert second_claim is False

    saved_job = job_store.get_job(job["job_id"])
    assert saved_job is not None
    assert saved_job["status"] == "running"


def test_completed_job_cannot_be_claimed_again():
    job = job_store.create_job(
        scenario="database_saturation",
        payload={"service": "orders-api"},
    )

    assert job_store.mark_job_running(job["job_id"]) is True

    job_store.complete_job(
        job["job_id"],
        {"message": "completed"},
    )

    assert job_store.mark_job_running(job["job_id"]) is False

    saved_job = job_store.get_job(job["job_id"])
    assert saved_job is not None
    assert saved_job["status"] == "completed"
