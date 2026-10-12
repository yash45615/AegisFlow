
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
    """Open the database and ensure job and checkpoint tables exist."""
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

    # Migrate existing job tables.
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

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_incident_jobs_idempotency_key
        ON incident_jobs(idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )

    # Store the latest checkpoint for each job.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS incident_job_checkpoints (
            job_id TEXT PRIMARY KEY,
            stage TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    # Add optional output storage to pre-existing checkpoint tables.
    checkpoint_columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(incident_job_checkpoints)"
        ).fetchall()
    }

    if "output_json" not in checkpoint_columns:
        connection.execute(
            """
            ALTER TABLE incident_job_checkpoints
            ADD COLUMN output_json TEXT
            """
        )

    # Store each stage output independently. Updating a later checkpoint
    # must not erase outputs saved for earlier stages.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS incident_job_stage_outputs (
            job_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            output_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (job_id, stage)
        )
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

    # Keep internal idempotency metadata out of ordinary job responses.
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
    key = (
        idempotency_key.strip()
        if idempotency_key is not None
        else None
    )

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
                VALUES (
                    ?, 'queued', ?, ?, NULL, NULL, ?,
                    NULL, NULL, ?, NULL, ?
                )
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

        # The unique index protects concurrent submissions with the same key.
        connection.execute(
            """
            INSERT OR IGNORE INTO incident_jobs (
                job_id, status, scenario, payload_json,
                result_json, error, created_at, started_at,
                completed_at, updated_at,
                idempotency_key, request_hash
            )
            VALUES (
                ?, 'queued', ?, ?, NULL, NULL, ?,
                NULL, NULL, ?, ?, ?
            )
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

        existing = connection.execute(
            """
            SELECT * FROM incident_jobs
            WHERE idempotency_key = ?
            """,
            (key,),
        ).fetchone()

        if existing is None:
            raise RuntimeError(
                "Job insert was ignored but no matching "
                "idempotency key exists."
            )

        if existing["request_hash"] != request_hash:
            raise IdempotencyConflict(
                "This Idempotency-Key has already been used "
                "with a different request."
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
    limit = max(1, min(limit, 100))

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM incident_jobs
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        decoded
        for row in rows
        if (decoded := _decode(row)) is not None
    ]


def mark_job_running(job_id: str) -> bool:
    """Atomically claim a queued job for one worker."""
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
    """Mark a running job as completed."""
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
    """Mark a running job as failed."""
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
    """
    Mark jobs left running after restart as failed.

    Automatic resumption remains disabled until all pipeline side effects
    can safely be resumed without creating duplicate records.
    """
    timestamp = _now()
    recovery_message = (
        "Job interrupted by API process restart; "
        "automatic retry requires safe pipeline resumption."
    )

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE incident_jobs
            SET status = 'failed',
                error = CASE
                    WHEN error IS NULL OR error = ''
                    THEN ?
                    ELSE substr(error || ' | ' || ?, 1, 2000)
                END,
                completed_at = ?,
                updated_at = ?
            WHERE status = 'running'
            """,
            (
                recovery_message,
                recovery_message,
                timestamp,
                timestamp,
            ),
        )

        return cursor.rowcount


def save_pipeline_checkpoint(
    job_id: str,
    stage: str,
    output: Any = None,
) -> dict[str, Any]:
    """
    Persist the latest stage and optional output.

    When output is provided, it is saved both as the latest checkpoint output
    and in the independent per-stage output table.
    """
    if not isinstance(stage, str) or not stage.strip():
        raise ValueError("Checkpoint stage cannot be blank")

    timestamp = _now()

    output_json = (
        json.dumps(
            output,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        if output is not None
        else None
    )

    with _connect() as connection:
        job = connection.execute(
            "SELECT job_id FROM incident_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        if job is None:
            raise ValueError(
                f"Cannot checkpoint unknown job: {job_id}"
            )

        if output is not None:
            connection.execute(
                """
                INSERT INTO incident_job_stage_outputs (
                    job_id, stage, output_json, updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(job_id, stage) DO UPDATE SET
                    output_json = excluded.output_json,
                    updated_at = excluded.updated_at
                """,
                (job_id, stage, output_json, timestamp),
            )

        connection.execute(
            """
            INSERT INTO incident_job_checkpoints (
                job_id, stage, updated_at, output_json
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                stage = excluded.stage,
                updated_at = excluded.updated_at,
                output_json = excluded.output_json
            """,
            (job_id, stage, timestamp, output_json),
        )

    return {
        "job_id": job_id,
        "stage": stage,
        "updated_at": timestamp,
        "output": output,
    }


def get_pipeline_checkpoint(
    job_id: str,
) -> dict[str, Any] | None:
    """Retrieve the latest persisted checkpoint and optional output."""
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT job_id, stage, updated_at, output_json
            FROM incident_job_checkpoints
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "job_id": row["job_id"],
        "stage": row["stage"],
        "updated_at": row["updated_at"],
        "output": (
            json.loads(row["output_json"])
            if row["output_json"] is not None
            else None
        ),
    }


def save_pipeline_stage_output(
    job_id: str,
    stage: str,
    output: Any,
) -> dict[str, Any]:
    """Persist or update the output for an individual pipeline stage."""
    if not isinstance(stage, str) or not stage.strip():
        raise ValueError("Stage name cannot be blank")

    output_json = json.dumps(
        output,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    timestamp = _now()

    with _connect() as connection:
        job = connection.execute(
            "SELECT job_id FROM incident_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        if job is None:
            raise ValueError(f"Unknown job: {job_id}")

        connection.execute(
            """
            INSERT INTO incident_job_stage_outputs (
                job_id, stage, output_json, updated_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(job_id, stage) DO UPDATE SET
                output_json = excluded.output_json,
                updated_at = excluded.updated_at
            """,
            (job_id, stage, output_json, timestamp),
        )

    return {
        "job_id": job_id,
        "stage": stage,
        "output": output,
        "updated_at": timestamp,
    }


def get_pipeline_stage_output(
    job_id: str,
    stage: str,
) -> dict[str, Any] | None:
    """Retrieve the saved output for one pipeline stage."""
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT job_id, stage, output_json, updated_at
            FROM incident_job_stage_outputs
            WHERE job_id = ? AND stage = ?
            """,
            (job_id, stage),
        ).fetchone()

    if row is None:
        return None

    return {
        "job_id": row["job_id"],
        "stage": row["stage"],
        "output": json.loads(row["output_json"]),
        "updated_at": row["updated_at"],
    }


def list_pipeline_stage_outputs(
    job_id: str,
) -> list[dict[str, Any]]:
    """Return all saved stage outputs for a job."""
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT job_id, stage, output_json, updated_at
            FROM incident_job_stage_outputs
            WHERE job_id = ?
            ORDER BY updated_at ASC, stage ASC
            """,
            (job_id,),
        ).fetchall()

    return [
        {
            "job_id": row["job_id"],
            "stage": row["stage"],
            "output": json.loads(row["output_json"]),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
