"""
Persist job records (SQLite) and final images (files on disk).

Why this exists (MVP platform lesson):
  Before: jobs lived only in a Python dict (_jobs in jobs.py). Restart the API →
  every in-flight or finished job vanished.

  After: every status change is written to a small SQLite database. Final images
  are saved as JPEG files under generated/jobs/<job_id>/ so responses stay small
  (use image_url instead of megabytes of base64 in JSON).

SQLite is a single file on disk — no separate database server to install.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from schemas import JobStatusResponse

logger = logging.getLogger("sdxl_api")

# Module-level paths set once by init_job_store().
_db_path: Path | None = None
_artifacts_root: Path | None = None
_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

# Relative URL path returned in JobStatusResponse.image_url (FastAPI route in main.py).
ARTIFACT_URL_PREFIX = "/jobs"


def init_job_store(*, db_path: Path, artifacts_root: Path) -> None:
    """Open (or create) the SQLite file and ensure artifact directories exist."""
    global _db_path, _artifacts_root, _conn
    _db_path = db_path
    _artifacts_root = artifacts_root
    _artifacts_root.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # check_same_thread=False: worker threads in jobs.py may write status updates.
    _conn = sqlite3.connect(str(db_path), check_same_thread=False)
    _conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            record_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    _conn.commit()
    logger.info("job store ready db=%s artifacts=%s", db_path, artifacts_root)


def _require_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("job_store not initialized — call init_job_store() at startup")
    return _conn


def save_job(record: JobStatusResponse) -> None:
    """Upsert the full job status snapshot (iterations, errors, metadata, URLs)."""
    # Exclude image_base64 from SQLite — images live on disk (see save_artifact).
    payload: dict[str, Any] = record.model_dump(mode="json")
    payload.pop("image_base64", None)

    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _require_conn()
        conn.execute(
            """
            INSERT INTO jobs (job_id, record_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                record_json = excluded.record_json,
                updated_at = excluded.updated_at
            """,
            (record.job_id, json.dumps(payload), now),
        )
        conn.commit()


def load_job(job_id: str) -> JobStatusResponse | None:
    """Read one job from SQLite. Returns None if the id was never stored."""
    with _lock:
        conn = _require_conn()
        row = conn.execute(
            "SELECT record_json FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if row is None:
        return None
    return JobStatusResponse.model_validate(json.loads(row[0]))


def save_artifact(job_id: str, image_bytes: bytes) -> str:
    """
    Write final JPEG bytes to disk and return the API path clients can fetch.

    Layout: <artifacts_root>/jobs/<job_id>/output.jpg
    URL:    /jobs/<job_id>/artifact  (served by main.py)
    """
    if _artifacts_root is None:
        raise RuntimeError("job_store not initialized")
    job_dir = _artifacts_root / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    out_path = job_dir / "output.jpg"
    out_path.write_bytes(image_bytes)
    logger.info("saved artifact job_id=%s path=%s bytes=%s", job_id, out_path, len(image_bytes))
    return f"{ARTIFACT_URL_PREFIX}/{job_id}/artifact"


def artifact_file_path(job_id: str) -> Path | None:
    """Filesystem path for GET /jobs/{id}/artifact, or None if not written yet."""
    if _artifacts_root is None:
        return None
    path = _artifacts_root / "jobs" / job_id / "output.jpg"
    return path if path.is_file() else None


def recover_interrupted_jobs() -> int:
    """
    On API startup: jobs stuck in queued/running cannot finish (worker died).
    Mark them error so clients see a clear message instead of polling forever.
    """
    with _lock:
        conn = _require_conn()
        rows = conn.execute("SELECT job_id, record_json FROM jobs").fetchall()

    recovered = 0
    for job_id, record_json in rows:
        record = JobStatusResponse.model_validate(json.loads(record_json))
        if record.status not in ("queued", "running"):
            continue
        record.status = "error"
        record.error_code = "server_restarted"
        record.message = "Job interrupted when the API restarted"
        save_job(record)
        recovered += 1
        logger.warning("recovered interrupted job_id=%s", job_id)
    return recovered


def reset_job_store_for_tests() -> None:
    """Wipe DB rows and artifact files between integration tests."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.execute("DELETE FROM jobs")
            _conn.commit()
    if _artifacts_root is not None:
        jobs_dir = _artifacts_root / "jobs"
        if jobs_dir.is_dir():
            for child in jobs_dir.iterdir():
                if child.is_dir():
                    for f in child.iterdir():
                        f.unlink(missing_ok=True)
                    child.rmdir()
