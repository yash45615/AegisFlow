
from __future__ import annotations
from fastapi import Query
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi import BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

class IncidentJobRequest(BaseModel):
    scenario: str = Field(
        min_length=1,
        max_length=100,
        description="Incident scenario identifier",
    )

    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Incident data to record and correlate",
    )

from app.jobs.incident_jobs import process_incident_job
from app.storage import job_store
from app.aegisflow_agent.service import ask_aegisflow
from app.investigation.assessment import assess_incident
from app.investigation.investigator import investigate_incident
from app.knowledge.retriever import search_knowledge
from app.observability import RequestObservabilityMiddleware
from app.remediation.planner import plan_remediation
from app.simulator.incident_simulator import simulate_incident
from app.storage.audit_store import (
    correlate_incident,
    get_incident_correlation,
    list_incident_correlations,
)
from app.storage.audit_store import (
    get_lifecycle,
    list_audit_events,
    list_incidents,
    list_lifecycles,
    record_audit_event,
    record_incident,
    save_lifecycle,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aegisflow.api")

app = FastAPI(
    title="AegisFlow",
    description=(
        "Evidence-grounded incident investigation and safe "
        "remediation planning platform."
    ),
    version="0.7.0",
)

app.add_middleware(RequestObservabilityMiddleware)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AIInvestigationRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)


# ---------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------

@app.get("/", tags=["Health"])
def root() -> dict[str, str]:
    return {"name": "AegisFlow", "status": "running"}


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "aegisflow-api",
    }


@app.get("/health/components", tags=["Health"])
def component_health() -> dict[str, Any]:
    runbooks_dir = PROJECT_ROOT / "data" / "runbooks"
    incidents_dir = PROJECT_ROOT / "data" / "historical_incidents"

    runbooks = (
        sorted(p.name for p in runbooks_dir.glob("*.md"))
        if runbooks_dir.is_dir()
        else []
    )
    historical_incidents = (
        sorted(p.name for p in incidents_dir.glob("*.md"))
        if incidents_dir.is_dir()
        else []
    )

    checks = {
        "runbooks": {
            "available": bool(runbooks),
            "document_count": len(runbooks),
        },
        "historical_incidents": {
            "available": bool(historical_incidents),
            "document_count": len(historical_incidents),
        },
    }

    healthy = all(item["available"] for item in checks.values())

    return {
        "status": "ok" if healthy else "degraded",
        "checks": checks,
        "external_ai_checked": False,
    }


# ---------------------------------------------------------------------
# Incident simulation and history
# ---------------------------------------------------------------------

@app.get("/incidents/simulate", tags=["Incidents"])
def simulate_incident_endpoint(
    scenario: str = Query(...),
) -> Any:
    try:
        incident = simulate_incident(scenario)
        record_incident(scenario=scenario, payload=incident)
        return incident
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/incidents/history", tags=["Incidents"])
def incident_history_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    incidents = list_incidents(limit=limit)
    return {"count": len(incidents), "incidents": incidents}


# ---------------------------------------------------------------------
# Knowledge retrieval
# ---------------------------------------------------------------------

@app.get("/knowledge/search", tags=["Knowledge"])
def knowledge_search_endpoint(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(default=3, ge=1, le=10),
) -> Any:
    try:
        return search_knowledge(q, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------
# Investigation
# ---------------------------------------------------------------------

@app.get("/incidents/investigate", tags=["Incidents"])
def investigate_incident_endpoint(
    scenario: str = Query(...),
    evidence_limit: int = Query(default=5, ge=1, le=10),
) -> Any:
    try:
        incident = simulate_incident(scenario)
        return investigate_incident(
            incident,
            evidence_limit=evidence_limit,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------
# Remediation proposals
# ---------------------------------------------------------------------

@app.get("/incidents/plan-remediation", tags=["Remediation"])
def plan_remediation_endpoint(
    scenario: str = Query(...),
    evidence_limit: int = Query(default=5, ge=1, le=10),
    max_actions: int = Query(default=5, ge=1, le=10),
) -> Any:
    try:
        incident = simulate_incident(scenario)
        investigation = investigate_incident(
            incident,
            evidence_limit=evidence_limit,
        )
        plan = plan_remediation(
            investigation,
            max_actions=max_actions,
        )

        record_audit_event(
            event_type="remediation_plan_created",
            details={
                "scenario": scenario,
                "max_actions": max_actions,
                "execution_performed": False,
            },
        )

        return plan
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------
# AI investigation
# ---------------------------------------------------------------------

@app.post("/ai/investigate", tags=["AI Agent"])
async def ai_investigation_endpoint(
    request: AIInvestigationRequest,
) -> dict[str, Any]:
    try:
        return await ask_aegisflow(request.prompt)
    except Exception as exc:
        logger.exception("AegisFlow AI investigation failed")
        raise HTTPException(
            status_code=502,
            detail=(
                "The AegisFlow AI agent could not complete this request. "
                "Check the server logs."
            ),
        ) from exc


# ---------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------

@app.get("/audit/events", tags=["Audit"])
def audit_events_endpoint(
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    events = list_audit_events(limit=limit)
    return {"count": len(events), "events": events}


# ---------------------------------------------------------------------
# Complete incident lifecycle and assessment
# ---------------------------------------------------------------------

@app.post("/incidents/lifecycle", tags=["Incident Lifecycle"])
def create_incident_lifecycle(
    scenario: str = Query(...),
) -> dict[str, Any]:
    try:
        incident = simulate_incident(scenario)

        saved_incident = record_incident(
        scenario=scenario,
        payload=incident,
        )
        correlation = correlate_incident(
        incident_id=saved_incident["incident_id"],
        scenario=scenario,
        payload=incident,
        )

        correlation = correlate_incident(
        incident_id=saved_incident["incident_id"],
        scenario=scenario,
        payload=incident,
        )

        investigation = investigate_incident(incident)
        remediation = plan_remediation(investigation)

        assessment = assess_incident(
            incident=incident,
            investigation=investigation,
        )

        lifecycle = save_lifecycle(
            incident_id=saved_incident["incident_id"],
            scenario=scenario,
            investigation=investigation,
            remediation=remediation,
        )

        record_audit_event(
            event_type="incident_assessment_created",
            details={
                "lifecycle_id": lifecycle["lifecycle_id"],
                "incident_id": saved_incident["incident_id"],
                "assessment": assessment,
            },
        )

        return {
        **lifecycle,
        "assessment": assessment,
        "correlation": correlation,
        "approval_required": True,
            "execution_performed": False,
}

    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Incident lifecycle failed")
        raise HTTPException(
            status_code=500,
            detail="Incident lifecycle processing failed.",
        ) from exc


@app.get("/incidents/lifecycle", tags=["Incident Lifecycle"])
def list_incident_lifecycles(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    lifecycles = list_lifecycles(limit=limit)
    return {
        "count": len(lifecycles),
        "lifecycles": lifecycles,
    }


@app.get(
    "/incidents/lifecycle/{lifecycle_id}",
    tags=["Incident Lifecycle"],
)
def get_incident_lifecycle(lifecycle_id: str) -> dict[str, Any]:
    lifecycle = get_lifecycle(lifecycle_id)

    if lifecycle is None:
        raise HTTPException(
            status_code=404,
            detail="Incident lifecycle not found",
        )

    return {
        **lifecycle,
        "approval_required": True,
        "execution_performed": False,
    }


@app.get("/incidents/correlations", tags=["Incident Correlation"])
def list_correlations_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List recently active incident correlation groups."""
    groups = list_incident_correlations(limit=limit)

    return {
        "count": len(groups),
        "groups": groups,
    }


@app.get(
    "/incidents/correlations/{incident_id}",
    tags=["Incident Correlation"],
)
def incident_correlation_endpoint(
    incident_id: str,
) -> dict[str, Any]:
    """Retrieve the correlation group for an incident."""
    result = get_incident_correlation(incident_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No correlation record found for this incident.",
        )

    return result


@app.on_event("startup")
def recover_jobs_after_restart() -> None:
    recovered = job_store.recover_interrupted_jobs()

    if recovered:
        logging.getLogger(__name__).warning(
            "Marked %s interrupted incident job(s) as failed",
            recovered,
        )


@app.post(
    "/incidents/jobs",
    status_code=202,
    tags=["Incident Jobs"],
)
def submit_incident_job(
    request: IncidentJobRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Queue an incident for background processing."""

    scenario = request.scenario.strip()

    if not scenario:
        raise HTTPException(
            status_code=422,
            detail="Scenario cannot be blank.",
        )

    job = job_store.create_job(
        scenario=scenario,
        payload=request.payload,
    )

    background_tasks.add_task(
        process_incident_job,
        job["job_id"],
    )

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "status_url": f"/incidents/jobs/{job['job_id']}",
        "message": "Incident job accepted for background processing.",
    }


@app.get(
    "/incidents/jobs/{job_id}",
    tags=["Incident Jobs"],
)
def get_incident_job(job_id: str) -> dict[str, Any]:
    """Retrieve a job's status, result, and error details."""

    job = job_store.get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Incident job not found.",
        )

    return job


@app.get(
    "/incidents/jobs",
    tags=["Incident Jobs"],
)
def list_incident_jobs(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List recent incident jobs."""

    jobs = job_store.list_jobs(limit=limit)

    return {
        "count": len(jobs),
        "jobs": jobs,
    }
