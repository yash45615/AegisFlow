from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IncidentSeverity(str, Enum):
    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"


class ServiceName(str, Enum):
    CHECKOUT = "checkout"
    AUTH = "auth"
    PAYMENT = "payment"
    DATABASE = "database"


class MetricSnapshot(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    request_rate_rps: float = Field(ge=0)
    error_rate_percent: float = Field(ge=0, le=100)
    latency_p95_ms: float = Field(ge=0)
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)


class ServiceLog(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    service: ServiceName
    level: str
    message: str
    trace_id: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class Incident(BaseModel):
    incident_id: str
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus = IncidentStatus.DETECTED
    affected_services: list[ServiceName]
    started_at: datetime = Field(default_factory=utc_now)
    metrics: dict[str, MetricSnapshot]
    logs: list[ServiceLog] = Field(default_factory=list)
    suspected_root_cause: str | None = None
    evidence: list[str] = Field(default_factory=list)


class RemediationAction(BaseModel):
    action_id: str
    incident_id: str
    action_type: str
    description: str
    requires_approval: bool = True
    approved: bool = False
    executed: bool = False
    verification_passed: bool | None = None
    created_at: datetime = Field(default_factory=utc_now)
