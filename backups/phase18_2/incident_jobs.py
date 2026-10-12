
from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Callable

from app.investigation.assessment import assess_incident
from app.investigation.investigator import investigate_incident
from app.remediation.planner import plan_remediation
from app.storage import audit_store, job_store


logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_DELAYS = (1, 2)

# Only these errors are considered transient.
RETRYABLE_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
    sqlite3.OperationalError,
)


def _record_audit_safely(
    event_type: str,
    details: dict[str, Any],
) -> None:
    """Record an audit event without changing the job's final status."""
    try:
        audit_store.record_audit_event(
            event_type=event_type,
            details=details,
        )
    except Exception:
        logger.exception(
            "Could not record audit event %s",
            event_type,
        )


def _save_checkpoint(job_id: str, stage: str) -> None:
    """Persist progress after a pipeline stage succeeds."""
    job_store.save_pipeline_checkpoint(job_id, stage)

    logger.debug(
        "Saved checkpoint for job %s: %s",
        job_id,
        stage,
    )


def _investigate_with_retries(
    incident: dict[str, Any],
    checkpoint_callback: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Retry transient analysis failures with bounded backoff.

    Checkpoint persistence errors are not treated as analysis retries.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            investigation = investigate_incident(incident)
        except RETRYABLE_EXCEPTIONS:
            if attempt >= MAX_ATTEMPTS:
                logger.exception(
                    "Investigation failed after %s attempts",
                    attempt,
                )
                raise

            delay = RETRY_DELAYS[attempt - 1]
            logger.warning(
                "Transient investigation failure on attempt %s/%s; "
                "retrying in %s second(s)",
                attempt,
                MAX_ATTEMPTS,
                delay,
                exc_info=True,
            )
            time.sleep(delay)
            continue

        if checkpoint_callback is not None:
            checkpoint_callback("investigation_completed")

        try:
            assessment = assess_incident(
                incident=incident,
                investigation=investigation,
            )
        except RETRYABLE_EXCEPTIONS:
            if attempt >= MAX_ATTEMPTS:
                logger.exception(
                    "Assessment failed after %s attempts",
                    attempt,
                )
                raise

            delay = RETRY_DELAYS[attempt - 1]
            logger.warning(
                "Transient assessment failure on attempt %s/%s; "
                "retrying in %s second(s)",
                attempt,
                MAX_ATTEMPTS,
                delay,
                exc_info=True,
            )
            time.sleep(delay)
            continue

        if checkpoint_callback is not None:
            checkpoint_callback("assessment_completed")

        try:
            remediation = plan_remediation(investigation)
        except RETRYABLE_EXCEPTIONS:
            if attempt >= MAX_ATTEMPTS:
                logger.exception(
                    "Remediation planning failed after %s attempts",
                    attempt,
                )
                raise

            delay = RETRY_DELAYS[attempt - 1]
            logger.warning(
                "Transient remediation-planning failure on attempt %s/%s; "
                "retrying in %s second(s)",
                attempt,
                MAX_ATTEMPTS,
                delay,
                exc_info=True,
            )
            time.sleep(delay)
            continue

        if checkpoint_callback is not None:
            checkpoint_callback("remediation_plan_completed")

        return investigation, assessment, remediation

    raise RuntimeError("Investigation retry loop exited unexpectedly.")


def process_incident_job(job_id: str) -> None:
    """Process an incident with bounded retries and durable checkpoints."""
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

    claimed = job_store.mark_job_running(job_id)

    if not claimed:
        logger.info(
            "Skipping job %s because it could not be claimed",
            job_id,
        )
        return

    try:
        scenario = job["scenario"]
        payload: dict[str, Any] = job["payload"]

        # Save the incident once, outside the analysis retry loop.
        saved_incident = audit_store.record_incident(
            scenario=scenario,
            payload=payload,
        )
        _save_checkpoint(job_id, "incident_recorded")

        incident_id = str(saved_incident["incident_id"])

        incident: dict[str, Any] = dict(payload)
        incident.setdefault("incident_id", incident_id)
        incident.setdefault("scenario", scenario)

        correlation: dict[str, Any] | None = None

        correlate = getattr(
            audit_store,
            "correlate_incident",
            None,
        )

        if callable(correlate):
            correlation = correlate(
                incident_id=incident_id,
                scenario=scenario,
                payload=payload,
            )

        _save_checkpoint(job_id, "correlation_completed")

        # Only analysis stages are retried.
        investigation, assessment, remediation = (
            _investigate_with_retries(
                incident,
                checkpoint_callback=lambda stage: _save_checkpoint(
                    job_id,
                    stage,
                ),
            )
        )

        # Save the lifecycle once after analysis succeeds.
        lifecycle = audit_store.save_lifecycle(
            incident_id=incident_id,
            scenario=scenario,
            investigation=investigation,
            remediation=remediation,
        )
        _save_checkpoint(job_id, "lifecycle_saved")

        result = {
            "job_id": job_id,
            "incident_id": incident_id,
            "scenario": scenario,
            "message": "Incident pipeline completed successfully.",
            "incident": saved_incident,
            "correlation": correlation,
            "investigation": investigation,
            "assessment": assessment,
            "remediation": remediation,
            "lifecycle": lifecycle,
            "remediation_executed": False,
        }

        _record_audit_safely(
            event_type="incident_job_completed",
            details={
                "job_id": job_id,
                "incident_id": incident_id,
                "scenario": scenario,
                "action_count": remediation.get("action_count", 0),
                "remediation_executed": False,
            },
        )

        job_store.complete_job(job_id, result)

        logger.info(
            "Incident job %s completed for incident %s",
            job_id,
            incident_id,
        )

    except Exception as exc:
        logger.exception("Incident job %s failed", job_id)

        try:
            job_store.fail_job(
                job_id,
                f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            logger.exception(
                "Could not mark incident job %s as failed",
                job_id,
            )

        _record_audit_safely(
            event_type="incident_job_failed",
            details={
                "job_id": job_id,
                "error_type": type(exc).__name__,
            },
        )
