
from __future__ import annotations

import json
import sqlite3
import uuid

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "aegisflow.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=30,
    )
    connection.row_factory = sqlite3.Row

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS incident_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            scenario TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            result_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_incident_jobs_created_at
        ON incident_jobs(created_at)
        """
    )

    connection.commit()
    return connection


def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None

    item = dict(row)
    item["payload"] = json.loads(item.pop("payload_json"))

    result_json = item.pop("result_json")
    item["result"] = json.loads(result_json) if result_json else None

    return item


def create_job(
    scenario: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    timestamp = _now()

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO incident_jobs (
                job_id, status, scenario, payload_json,
                result_json, error, created_at, started_at,
                completed_at, updated_at
            )
            VALUES (?, 'queued', ?, ?, NULL, NULL, ?, NULL, NULL, ?)
            """,
            (
                job_id,
                scenario,
                json.dumps(payload, default=str),
                timestamp,
                timestamp,
            ),
        )

        row = connection.execute(
            "SELECT * FROM incident_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

    result = _decode(row)
    assert result is not None
    return result


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM incident_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

    return _decode(row)


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM incident_jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_decode(row) for row in rows if row is not None]


def mark_job_running(job_id: str) -> None:
    timestamp = _now()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE incident_jobs
            SET status = 'running',
                started_at = ?,
                updated_at = ?,
                error = NULL
            WHERE job_id = ? AND status = 'queued'
            """,
            (timestamp, timestamp, job_id),
        )


def complete_job(
    job_id: str,
    result: dict[str, Any],
) -> None:
    timestamp = _now()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE incident_jobs
            SET status = 'completed',
                result_json = ?,
                error = NULL,
                completed_at = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (
                json.dumps(result, default=str),
                timestamp,
                timestamp,
                job_id,
            ),
        )


def fail_job(job_id: str, error: str) -> None:
    timestamp = _now()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE incident_jobs
            SET status = 'failed',
                error = ?,
                completed_at = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (error[:2000], timestamp, timestamp, job_id),
        )


def recover_interrupted_jobs() -> int:
    """Mark jobs interrupted by an API restart as failed."""
    timestamp = _now()

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE incident_jobs
            SET status = 'failed',
                error = 'Job interrupted by API process restart.',
                completed_at = ?,
                updated_at = ?
            WHERE status = 'running'
            """,
            (timestamp, timestamp),
        )

    return cursor.rowcount
