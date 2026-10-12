from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "aegisflow.db"


class IdempotencyConflict(Exception):
    """Raised when an idempotency key is reused for a different request."""


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
            updated_at TEXT NOT NULL,
            idempotency_key TEXT,
            request_hash TEXT
        )
        """
    )

    # Migrate databases created before Phase 17.1.
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(incident_jobs)"
        ).fetchall()
    }

    if "idempotency_key" not in columns:
        connection.execute(
            "ALTER TABLE incident_jobs ADD COLUMN idempotency_key TEXT"
        )

    if "request_hash" not in columns:
        connection.execute(
            "ALTER TABLE incident_jobs ADD COLUMN request_hash TEXT"
        )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_incident_jobs_created_at
        ON incident_jobs(created_at)
        """
    )

    # Multiple NULL keys are allowed; every actual key must be unique.
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_incident_jobs_idempotency_key
        ON incident_jobs(idempotency_key)
        WHERE idempotency_key IS NOT NULL
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

    # Internal idempotency metadata is not exposed in ordinary job responses.
    item.pop("idempotency_key", None)
    item.pop("request_hash", None)

    return item


def _request_hash(
    scenario: str,
    payload: dict[str, Any],
) -> str:
    canonical_request = json.dumps(
        {
            "scenario": scenario,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        canonical_request.encode("utf-8")
    ).hexdigest()


def create_job(
    scenario: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    key = idempotency_key.strip() if idempotency_key is not None else None

    if key == "":
        raise ValueError("idempotency_key cannot be blank")

    job_id = str(uuid.uuid4())
    timestamp = _now()
    payload_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    request_hash = _request_hash(scenario, payload)

    with _connect() as connection:
        if key is None:
            connection.execute(
                """
                INSERT INTO incident_jobs (
                    job_id, status, scenario, payload_json,
                    result_json, error, created_at, started_at,
                    completed_at, updated_at,
                    idempotency_key, request_hash
                )
                VALUES (?, 'queued', ?, ?, NULL, NULL, ?, NULL, NULL, ?, NULL, ?)
                """,
                (
                    job_id,
                    scenario,
                    payload_json,
                    timestamp,
                    timestamp,
                    request_hash,
                ),
            )

            row = connection.execute(
                "SELECT * FROM incident_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()

            result = _decode(row)
            assert result is not None
            result["_idempotency_replayed"] = False
            return result

        # INSERT OR IGNORE plus the unique index makes duplicate handling
        # safe when concurrent requests use the same key.
        connection.execute(
            """
            INSERT OR IGNORE INTO incident_jobs (
                job_id, status, scenario, payload_json,
                result_json, error, created_at, started_at,
                completed_at, updated_at,
                idempotency_key, request_hash
            )
            VALUES (?, 'queued', ?, ?, NULL, NULL, ?, NULL, NULL, ?, ?, ?)
            """,
            (
                job_id,
                scenario,
                payload_json,
                timestamp,
                timestamp,
                key,
                request_hash,
            ),
        )

        row = connection.execute(
            "SELECT * FROM incident_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        if row is not None:
            result = _decode(row)
            assert result is not None
            result["_idempotency_replayed"] = False
            return result

        # The key already existed, so load the original job.
        existing = connection.execute(
            """
            SELECT * FROM incident_jobs
            WHERE idempotency_key = ?
            """,
            (key,),
        ).fetchone()

        if existing is None:
            raise RuntimeError(
                "Job insert was ignored but no matching idempotency key exists."
            )

        if existing["request_hash"] != request_hash:
            raise IdempotencyConflict(
                "This Idempotency-Key has already been used with a different request."
            )

        result = _decode(existing)
        assert result is not None
        result["_idempotency_replayed"] = True
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



def mark_job_running(job_id: str) -> bool:
    """Atomically claim a queued job for one worker.

    Returns True only when this call successfully claims the job.
    """
    timestamp = _now()

    with _connect() as connection:
        cursor = connection.execute(
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

        return cursor.rowcount == 1

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
            WHERE job_id = ? AND status = 'running'
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
            WHERE job_id = ? AND status = 'running'
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
