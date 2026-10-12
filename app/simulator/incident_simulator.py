from uuid import uuid4

from app.models.incident import (
    Incident,
    IncidentSeverity,
    MetricSnapshot,
    ServiceLog,
    ServiceName,
)


def simulate_incident(scenario: str = "database_saturation") -> Incident:
    """Generate deterministic incident evidence for local agent testing."""

    incident_id = f"INC-{uuid4().hex[:8].upper()}"
    trace_id = f"trace-{uuid4().hex[:12]}"

    scenarios = {
        "database_saturation": {
            "title": "Checkout latency caused by database connection saturation",
            "description": (
                "Checkout latency and errors increased after the database "
                "connection pool reached capacity."
            ),
            "severity": IncidentSeverity.SEV2,
            "services": [ServiceName.CHECKOUT, ServiceName.DATABASE],
            "cause": "Database connection pool saturation",
            "metrics": {
                "checkout": MetricSnapshot(
                    request_rate_rps=120,
                    error_rate_percent=18.5,
                    latency_p95_ms=4200,
                    cpu_percent=72,
                    memory_percent=78,
                ),
                "database": MetricSnapshot(
                    request_rate_rps=310,
                    error_rate_percent=4.2,
                    latency_p95_ms=1800,
                    cpu_percent=94,
                    memory_percent=89,
                ),
            },
            "logs": [
                (
                    ServiceName.CHECKOUT,
                    "ERROR",
                    "Checkout request timed out waiting for database connection",
                    {"timeout_ms": 3000},
                ),
                (
                    ServiceName.DATABASE,
                    "WARN",
                    "Connection pool utilization exceeded 95%",
                    {"pool_utilization_percent": 98},
                ),
                (
                    ServiceName.DATABASE,
                    "ERROR",
                    "Connection acquisition timeout",
                    {"active_connections": 100, "max_connections": 100},
                ),
            ],
        },
        "auth_failure": {
            "title": "Elevated authentication failures",
            "description": (
                "Authentication requests are failing because the token "
                "validation dependency is returning errors."
            ),
            "severity": IncidentSeverity.SEV2,
            "services": [ServiceName.AUTH, ServiceName.CHECKOUT],
            "cause": "Token validation dependency failure",
            "metrics": {
                "auth": MetricSnapshot(
                    request_rate_rps=200,
                    error_rate_percent=32,
                    latency_p95_ms=1400,
                    cpu_percent=55,
                    memory_percent=63,
                ),
                "checkout": MetricSnapshot(
                    request_rate_rps=90,
                    error_rate_percent=12,
                    latency_p95_ms=1700,
                    cpu_percent=48,
                    memory_percent=59,
                ),
            },
            "logs": [
                (
                    ServiceName.AUTH,
                    "ERROR",
                    "Token validation dependency returned HTTP 503",
                    {"dependency_status": 503},
                ),
                (
                    ServiceName.AUTH,
                    "WARN",
                    "Authentication failure rate exceeded alert threshold",
                    {"threshold_percent": 10},
                ),
                (
                    ServiceName.CHECKOUT,
                    "ERROR",
                    "Request rejected because authentication could not complete",
                    {"upstream": "auth"},
                ),
            ],
        },
        "payment_timeout": {
            "title": "Payment provider timeout affecting checkout",
            "description": (
                "Checkout requests are timing out while waiting for the "
                "external payment provider."
            ),
            "severity": IncidentSeverity.SEV2,
            "services": [ServiceName.PAYMENT, ServiceName.CHECKOUT],
            "cause": "External payment provider latency",
            "metrics": {
                "payment": MetricSnapshot(
                    request_rate_rps=85,
                    error_rate_percent=24,
                    latency_p95_ms=5100,
                    cpu_percent=42,
                    memory_percent=51,
                ),
                "checkout": MetricSnapshot(
                    request_rate_rps=100,
                    error_rate_percent=16,
                    latency_p95_ms=4800,
                    cpu_percent=62,
                    memory_percent=67,
                ),
            },
            "logs": [
                (
                    ServiceName.PAYMENT,
                    "ERROR",
                    "Payment provider request exceeded timeout",
                    {"timeout_ms": 5000},
                ),
                (
                    ServiceName.PAYMENT,
                    "WARN",
                    "Payment provider latency above normal baseline",
                    {"provider_latency_ms": 5200},
                ),
                (
                    ServiceName.CHECKOUT,
                    "ERROR",
                    "Checkout failed while awaiting payment authorization",
                    {"upstream": "payment"},
                ),
            ],
        },
    }

    if scenario not in scenarios:
        available = ", ".join(sorted(scenarios))
        raise ValueError(f"Unknown scenario '{scenario}'. Choose: {available}")

    config = scenarios[scenario]
    logs = [
        ServiceLog(
            service=service,
            level=level,
            message=message,
            trace_id=trace_id,
            attributes=attributes,
        )
        for service, level, message, attributes in config["logs"]
    ]

    return Incident(
        incident_id=incident_id,
        title=config["title"],
        description=config["description"],
        severity=config["severity"],
        affected_services=config["services"],
        metrics=config["metrics"],
        logs=logs,
        suspected_root_cause=config["cause"],
        evidence=[
            f"{log.service.value}: {log.message}"
            for log in logs
        ],
    )
