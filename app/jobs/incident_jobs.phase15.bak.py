
from __future__ import annotations

import logging
from typing import Any

from app.storage import audit_store, job_store


logger = logging.getLogger(__name__)


def process_incident_job(job_id: str) -> None:
    """Process one incident job in the FastAPI background worker."""

    job = job_store.get_job(job_id)

    if job is None:
        logger.error("Cannot process missing job %s", job_id)
        return

    if job["status"] != "queued":
        logger.info(
            "Skipping job %s because its status is %s",
            job_id,
            job["status"],
        )
        return

    job_store.mark_job_running(job_id)

    try:
        scenario = job["scenario"]
        payload: dict[str, Any] = job["payload"]

        saved_incident = audit_store.record_incident(
            scenario=scenario,
            payload=payload,
        )

        incident_id = saved_incident["incident_id"]
        correlation: dict[str, Any] | None = None

        # Correlation is optional, so jobs still complete if the
        # correlation feature has not been installed yet.
        correlate = getattr(audit_store, "correlate_incident", None)

        if callable(correlate):
            correlation = correlate(
                incident_id=incident_id,
                scenario=scenario,
                payload=payload,
            )

        result = {
            "job_id": job_id,
            "incident_id": incident_id,
            "scenario": scenario,
            "message": "Incident accepted and recorded.",
            "correlation": correlation,
            "remediation_executed": False,
        }

        job_store.complete_job(job_id, result)

        audit_store.record_audit_event(
            event_type="incident_job_completed",
            details={
                "job_id": job_id,
                "incident_id": incident_id,
                "scenario": scenario,
            },
        )

    except Exception as exc:
        logger.exception("Incident job %s failed", job_id)

        job_store.fail_job(
            job_id,
            f"{type(exc).__name__}: {exc}",
        )

        try:
            audit_store.record_audit_event(
                event_type="incident_job_failed",
                details={
                    "job_id": job_id,
                    "error_type": type(exc).__name__,
                },
            )
        except Exception:
            logger.exception("Could not record failure audit event")
