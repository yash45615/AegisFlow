
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.investigation.correlation import (
    build_incident_fingerprint,
    compare_incident_signatures,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "aegisflow.db"


def _connect() -> sqlite3.Connection:
    """Open a connection and ensure all application tables exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            scenario TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS incident_lifecycles (
            lifecycle_id TEXT PRIMARY KEY,
            incident_id TEXT NOT NULL,
            scenario TEXT NOT NULL,
            investigation_json TEXT NOT NULL,
            remediation_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS incident_correlations (
            incident_id TEXT PRIMARY KEY,
            correlation_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            scenario TEXT NOT NULL,
            signature_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_incidents_created_at
        ON incidents(created_at);

        CREATE INDEX IF NOT EXISTS idx_audit_events_created_at
        ON audit_events(created_at);

        CREATE INDEX IF NOT EXISTS idx_lifecycles_created_at
        ON incident_lifecycles(created_at);

        CREATE INDEX IF NOT EXISTS
            idx_incident_correlations_fingerprint
        ON incident_correlations(fingerprint, scenario, created_at);

        CREATE INDEX IF NOT EXISTS
            idx_incident_correlations_group
        ON incident_correlations(correlation_id, created_at);
        """
    )

    connection.commit()
    return connection


def _now() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> str:
    """Serialize objects that JSON cannot encode directly."""
    return str(value)


def _to_json(value: Any) -> str:
    """Convert supported Python objects into JSON."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif hasattr(value, "dict") and callable(value.dict):
        value = value.dict()

    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
    )


def record_audit_event(
    event_type: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist an auditable application event."""
    event = {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "details": details or {},
        "created_at": _now(),
    }

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO audit_events (
                event_id,
                event_type,
                details_json,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["event_type"],
                _to_json(event["details"]),
                event["created_at"],
            ),
        )

    return event


def record_incident(
    scenario: str,
    payload: Any,
) -> dict[str, Any]:
    """Save an incident snapshot and record its creation in the audit trail."""
    incident = {
        "incident_id": str(uuid4()),
        "scenario": scenario,
        "payload": payload,
        "created_at": _now(),
    }

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO incidents (
                incident_id,
                scenario,
                payload_json,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                incident["incident_id"],
                incident["scenario"],
                _to_json(incident["payload"]),
                incident["created_at"],
            ),
        )

        connection.execute(
            """
            INSERT INTO audit_events (
                event_id,
                event_type,
                details_json,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                "incident_simulated",
                _to_json(
                    {
                        "incident_id": incident["incident_id"],
                        "scenario": scenario,
                    }
                ),
                incident["created_at"],
            ),
        )

    return incident


def list_incidents(limit: int = 20) -> list[dict[str, Any]]:
    """Return the newest incident records first."""
    limit = max(1, min(limit, 100))

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT incident_id, scenario, payload_json, created_at
            FROM incidents
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "incident_id": row["incident_id"],
            "scenario": row["scenario"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def list_audit_events(limit: int = 50) -> list[dict[str, Any]]:
    """Return the newest audit events first."""
    limit = max(1, min(limit, 100))

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT event_id, event_type, details_json, created_at
            FROM audit_events
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "details": json.loads(row["details_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def initialize_lifecycle_table() -> None:
    """Ensure persistent storage exists for incident workflows."""
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS incident_lifecycles (
                lifecycle_id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                scenario TEXT NOT NULL,
                investigation_json TEXT NOT NULL,
                remediation_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lifecycles_created_at
            ON incident_lifecycles(created_at)
            """
        )


def save_lifecycle(
    incident_id: str,
    scenario: str,
    investigation: Any,
    remediation: Any,
) -> dict[str, Any]:
    """Persist an investigation and proposed remediation together."""
    initialize_lifecycle_table()

    lifecycle = {
        "lifecycle_id": str(uuid4()),
        "incident_id": incident_id,
        "scenario": scenario,
        "investigation": investigation,
        "remediation": remediation,
        "status": "awaiting_human_review",
        "created_at": _now(),
    }

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO incident_lifecycles (
                lifecycle_id,
                incident_id,
                scenario,
                investigation_json,
                remediation_json,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lifecycle["lifecycle_id"],
                lifecycle["incident_id"],
                lifecycle["scenario"],
                _to_json(lifecycle["investigation"]),
                _to_json(lifecycle["remediation"]),
                lifecycle["status"],
                lifecycle["created_at"],
            ),
        )

    record_audit_event(
        "incident_lifecycle_created",
        {
            "lifecycle_id": lifecycle["lifecycle_id"],
            "incident_id": incident_id,
            "scenario": scenario,
            "status": lifecycle["status"],
        },
    )

    return lifecycle


def get_lifecycle(lifecycle_id: str) -> dict[str, Any] | None:
    """Retrieve a saved incident lifecycle by ID."""
    initialize_lifecycle_table()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM incident_lifecycles
            WHERE lifecycle_id = ?
            """,
            (lifecycle_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "lifecycle_id": row["lifecycle_id"],
        "incident_id": row["incident_id"],
        "scenario": row["scenario"],
        "investigation": json.loads(row["investigation_json"]),
        "remediation": json.loads(row["remediation_json"]),
        "status": row["status"],
        "created_at": row["created_at"],
    }


def list_lifecycles(limit: int = 20) -> list[dict[str, Any]]:
    """List recent incident workflow records."""
    initialize_lifecycle_table()
    limit = max(1, min(limit, 100))

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT lifecycle_id
            FROM incident_lifecycles
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    results = []

    for row in rows:
        lifecycle = get_lifecycle(row["lifecycle_id"])
        if lifecycle is not None:
            results.append(lifecycle)

    return results



def correlate_incident(
    incident_id: str,
    scenario: str,
    payload: Any,
) -> dict[str, Any]:
    """Persist an incident's correlation group and return related incidents."""
    fingerprint, signature = build_incident_fingerprint(
        scenario,
        payload,
    )

    meaningful_fields = set(signature.keys()) - {"scenario"}
    can_correlate = bool(meaningful_fields)

    with _connect() as connection:
        existing = connection.execute(
            """
            SELECT incident_id, correlation_id, fingerprint,
                   scenario, signature_json, created_at
            FROM incident_correlations
            WHERE incident_id = ?
            """,
            (incident_id,),
        ).fetchone()

        if existing is not None:
            result = dict(existing)
            result["signature"] = json.loads(
                result.pop("signature_json")
            )

            related_rows = connection.execute(
                """
                SELECT incident_id
                FROM incident_correlations
                WHERE correlation_id = ?
                  AND incident_id != ?
                ORDER BY created_at, incident_id
                """,
                (result["correlation_id"], incident_id),
            ).fetchall()

            result["related_incident_ids"] = [
                row["incident_id"] for row in related_rows
            ]
            result["is_correlated"] = bool(
                result["related_incident_ids"]
            )
            return result

        matching_groups = []

        if can_correlate:
            candidates = connection.execute(
                """
                SELECT incident_id, correlation_id, fingerprint,
                       scenario, signature_json, created_at
                FROM incident_correlations
                WHERE fingerprint = ?
                  AND scenario = ?
                ORDER BY created_at ASC, incident_id ASC
                """,
                (fingerprint, scenario),
            ).fetchall()

            for candidate in candidates:
                candidate_signature = json.loads(
                    candidate["signature_json"]
                )
                comparison = compare_incident_signatures(
                    signature,
                    candidate_signature,
                )

                if comparison["matching"]:
                    matching_groups.append(candidate)

        is_correlated = bool(matching_groups)

        if is_correlated:
            correlation_id = matching_groups[0]["correlation_id"]
        else:
            correlation_id = str(uuid4())

        created_at = _now()

        connection.execute(
            """
            INSERT INTO incident_correlations (
                incident_id,
                correlation_id,
                fingerprint,
                scenario,
                signature_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                correlation_id,
                fingerprint,
                scenario,
                json.dumps(signature, sort_keys=True),
                created_at,
            ),
        )

        related_rows = connection.execute(
            """
            SELECT incident_id
            FROM incident_correlations
            WHERE correlation_id = ?
              AND incident_id != ?
            ORDER BY created_at, incident_id
            """,
            (correlation_id, incident_id),
        ).fetchall()

    related_incident_ids = [
        row["incident_id"] for row in related_rows
    ]

    result = {
        "incident_id": incident_id,
        "correlation_id": correlation_id,
        "fingerprint": fingerprint,
        "scenario": scenario,
        "signature": signature,
        "created_at": created_at,
        "is_correlated": bool(related_incident_ids),
        "related_incident_ids": related_incident_ids,
    }

    try:
        record_audit_event(
            event_type="incident_correlated",
            details={
                "incident_id": incident_id,
                "correlation_id": correlation_id,
                "scenario": scenario,
                "is_correlated": result["is_correlated"],
                "related_incident_ids": related_incident_ids,
                "correlation_evidence_available": can_correlate,
            },
        )
    except Exception:
        pass

    return result


def get_incident_correlation(
    incident_id: str,
) -> dict[str, Any] | None:
    """Retrieve the correlation group for a known incident."""
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT correlation_id
            FROM incident_correlations
            WHERE incident_id = ?
            """,
            (incident_id,),
        ).fetchone()

        if row is None:
            return None

        group_id = row["correlation_id"]

        members = connection.execute(
            """
            SELECT incident_id, scenario, fingerprint,
                   signature_json, created_at
            FROM incident_correlations
            WHERE correlation_id = ?
            ORDER BY created_at, incident_id
            """,
            (group_id,),
        ).fetchall()

    return {
        "correlation_id": group_id,
        "group_size": len(members),
        "incidents": [
            {
                "incident_id": member["incident_id"],
                "scenario": member["scenario"],
                "fingerprint": member["fingerprint"],
                "signature": json.loads(member["signature_json"]),
                "created_at": member["created_at"],
            }
            for member in members
        ],
    }


def list_incident_correlations(
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return the most recently seen correlation groups."""
    limit = max(1, min(limit, 100))

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT correlation_id,
                   COUNT(*) AS group_size,
                   MAX(created_at) AS last_seen
            FROM incident_correlations
            GROUP BY correlation_id
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "correlation_id": row["correlation_id"],
            "group_size": row["group_size"],
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]
