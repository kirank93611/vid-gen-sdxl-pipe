"""In-memory correction jobs: generate → evaluate → correct (bounded iterations)."""

from __future__ import annotations

import asyncio
import base64
import logging
import threading
import uuid
from typing import TYPE_CHECKING, Any

from correction import apply_corrections
from evaluator import _decode_reference, evaluate_output
from generation_service import generate_image_bytes
from schemas import (
    EvalResult,
    GenerateRequest,
    JobCreateRequest,
    JobIterationRecord,
    JobStatusResponse,
)
from sdxl_adapter import build_metadata

if TYPE_CHECKING:
    from registry import EngineRegistry

logger = logging.getLogger("sdxl_api")

_store_lock = threading.Lock()
_jobs: dict[str, JobStatusResponse] = {}
_tasks: dict[str, asyncio.Task[None]] = {}

_registry: EngineRegistry | None = None
_timeout_seconds: float = 90.0
_semaphore: threading.Semaphore | None = None


def configure(
    registry: EngineRegistry,
    timeout_seconds: float,
    semaphore: threading.Semaphore,
) -> None:
    global _registry, _timeout_seconds, _semaphore
    _registry = registry
    _timeout_seconds = timeout_seconds
    _semaphore = semaphore


def create_job(payload: JobCreateRequest) -> JobStatusResponse:
    job_id = str(uuid.uuid4())
    record = JobStatusResponse(
        job_id=job_id,
        status="queued",
        goal=payload.goal,
        iterations=[],
    )
    with _store_lock:
        _jobs[job_id] = record
    return record


def get_job(job_id: str) -> JobStatusResponse | None:
    with _store_lock:
        return _jobs.get(job_id)


def reset_store_for_tests() -> None:
    """Clear in-memory jobs between integration tests."""
    with _store_lock:
        _jobs.clear()
        _tasks.clear()


def _to_generate_request(payload: JobCreateRequest) -> GenerateRequest:
    return GenerateRequest(
        prompt=payload.prompt,
        negative_prompt=payload.negative_prompt,
        quality_tier=payload.quality_tier,
        seed=payload.seed,
        width=payload.width,
        height=payload.height,
    )


def schedule_job(job_id: str, payload: JobCreateRequest) -> None:
    task = asyncio.create_task(_run_job(job_id, payload), name=f"job-{job_id}")
    with _store_lock:
        _tasks[job_id] = task


async def _run_job(job_id: str, payload: JobCreateRequest) -> None:
    if _registry is None or _semaphore is None:
        _set_error(job_id, "internal_error", "Job runtime not configured")
        return

    _set_status(job_id, "running")
    current = _to_generate_request(payload)
    goal = payload.goal
    image_bytes: bytes | None = None
    final_meta: dict[str, Any] | None = None
    try:
        reference_bytes = _decode_reference(payload.reference_image_base64)
    except ValueError as exc:
        _set_error(job_id, "invalid_request", str(exc))
        return

    acquired = _semaphore.acquire(blocking=False)
    if not acquired:
        _set_error(job_id, "capacity_reached", "GPU busy, retry later")
        return

    try:
        for attempt in range(1, payload.max_iterations + 1):
            try:
                image_bytes, used_seed, effective, model_id = await generate_image_bytes(
                    current,
                    registry=_registry,
                    timeout_seconds=_timeout_seconds,
                )
            except asyncio.TimeoutError:
                _set_error(
                    job_id,
                    "generation_timeout",
                    f"Generation timed out on attempt {attempt}",
                )
                return
            except Exception as exc:
                logger.exception("job_id=%s attempt=%s failed", job_id, attempt)
                _set_error(job_id, "internal_error", str(exc))
                return

            evaluation = evaluate_output(
                goal,
                effective,
                attempt=attempt,
                output_image=image_bytes,
                reference_image=reference_bytes,
            )
            _append_iteration(job_id, evaluation, effective, used_seed)

            if evaluation.passed:
                final_meta = build_metadata(
                    effective,
                    current,
                    model_id,
                    used_seed,
                )
                _set_converged(job_id, image_bytes, final_meta)
                return

            patched = apply_corrections(current, evaluation)
            if patched is None:
                break
            current = patched

        _set_failed(job_id, image_bytes, final_meta)
    finally:
        _semaphore.release()


def _append_iteration(
    job_id: str,
    evaluation: EvalResult,
    effective: GenerateRequest,
    used_seed: int,
) -> None:
    with _store_lock:
        record = _jobs[job_id]
        record.iterations.append(
            JobIterationRecord(
                attempt=evaluation.attempt,
                passed=evaluation.passed,
                issues=list(evaluation.issues),
                quality_tier=effective.quality_tier,
                steps=effective.steps,
                guidance_scale=effective.guidance_scale,
                seed=used_seed,
                clip_similarity=evaluation.metrics.get("clip_similarity"),
            )
        )


def _set_status(job_id: str, status: str) -> None:
    with _store_lock:
        _jobs[job_id].status = status  # type: ignore[assignment]


def _set_converged(job_id: str, image_bytes: bytes, metadata: dict[str, Any]) -> None:
    with _store_lock:
        record = _jobs[job_id]
        record.status = "converged"
        record.image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        record.metadata = metadata
        record.message = "Goal criteria met"


def _set_failed(job_id: str, image_bytes: bytes | None, metadata: dict[str, Any] | None) -> None:
    with _store_lock:
        record = _jobs[job_id]
        record.status = "failed"
        record.error_code = "convergence_failed"
        record.message = "Max iterations reached without passing evaluation"
        if image_bytes is not None:
            record.image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        if metadata is not None:
            record.metadata = metadata


def _set_error(job_id: str, error_code: str, message: str) -> None:
    with _store_lock:
        record = _jobs[job_id]
        record.status = "error"
        record.error_code = error_code
        record.message = message
