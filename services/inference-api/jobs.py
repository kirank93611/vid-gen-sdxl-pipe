"""Correction jobs: generate → evaluate → correct (bounded iterations).

Persistence: status snapshots go to SQLite (job_store.py); final images to disk.
An in-memory cache (_jobs) keeps reads fast; every mutation writes through to disk.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import threading
import uuid
from typing import TYPE_CHECKING, Any, Literal

from correction import resolve_correction
from evaluator import decode_reference, evaluate_output
from generation_service import generate_image_bytes, inpaint_image_bytes
import job_store
from image_utils import (
    decode_image_bytes,
    decode_mask_base64,
    default_center_mask,
    mask_to_bytes,
)
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
_inpaint_strength: float = 0.85
_semaphore: threading.Semaphore | None = None


def init_persistence() -> None:
    """Call once at API startup (see main.py)."""
    from api_config import ARTIFACTS_DIR, JOB_DB_PATH

    job_store.init_job_store(db_path=JOB_DB_PATH, artifacts_root=ARTIFACTS_DIR)
    recovered = job_store.recover_interrupted_jobs()
    if recovered:
        logger.info("marked %s interrupted jobs as error after restart", recovered)


def configure(
    registry: EngineRegistry,
    timeout_seconds: float,
    semaphore: threading.Semaphore,
    *,
    inpaint_strength: float = 0.85,
) -> None:
    global _registry, _timeout_seconds, _semaphore, _inpaint_strength
    _registry = registry
    _timeout_seconds = timeout_seconds
    _semaphore = semaphore
    _inpaint_strength = inpaint_strength


def _update_job(record: JobStatusResponse) -> None:
    """Memory cache + SQLite — single place for all job state writes."""
    with _store_lock:
        _jobs[record.job_id] = record
    job_store.save_job(record)


def create_job(payload: JobCreateRequest) -> JobStatusResponse:
    job_id = str(uuid.uuid4())
    record = JobStatusResponse(
        job_id=job_id,
        status="queued",
        goal=payload.goal,
        iterations=[],
    )
    _update_job(record)
    return record


def get_job(job_id: str) -> JobStatusResponse | None:
    with _store_lock:
        cached = _jobs.get(job_id)
    if cached is not None:
        return cached
    record = job_store.load_job(job_id)
    if record is None:
        return None
    with _store_lock:
        _jobs[job_id] = record
    return record


def reset_store_for_tests() -> None:
    """Clear in-memory jobs and on-disk test store between integration tests."""
    with _store_lock:
        _jobs.clear()
        _tasks.clear()
    job_store.reset_job_store_for_tests()


def clear_memory_cache_for_tests() -> None:
    """Simulate API restart: memory empty, SQLite + files still on disk."""
    with _store_lock:
        _jobs.clear()


def _to_generate_request(payload: JobCreateRequest) -> GenerateRequest:
    fields: dict[str, object] = {
        "prompt": payload.prompt,
        "negative_prompt": payload.negative_prompt,
        "quality_tier": payload.quality_tier,
        "seed": payload.seed,
        "width": payload.width,
        "height": payload.height,
        "lora_name": payload.lora_name,
        "lora_weight": payload.lora_weight,
        "model_id": payload.model_id,
        "generation_profile": payload.generation_profile,
    }
    if payload.steps is not None:
        fields["steps"] = payload.steps
    if payload.guidance_scale is not None:
        fields["guidance_scale"] = payload.guidance_scale
    if payload.scheduler is not None:
        fields["scheduler"] = payload.scheduler
    if payload.clip_skip is not None:
        fields["clip_skip"] = payload.clip_skip
    return GenerateRequest(**fields)  # type: ignore[arg-type]


def _resolve_mask_bytes(payload: JobCreateRequest, image_bytes: bytes | None) -> bytes | None:
    if payload.mask_base64:
        return base64.b64decode(payload.mask_base64, validate=True)
    if payload.goal.use_inpaint_correction and image_bytes:
        image = decode_image_bytes(image_bytes)
        mask = default_center_mask(image.width, image.height)
        return mask_to_bytes(mask)
    return None


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
    last_image: bytes | None = None
    mask_bytes: bytes | None = None
    final_meta: dict[str, Any] | None = None
    inpaint_next = False

    try:
        reference_bytes = decode_reference(payload.reference_image_base64)
    except ValueError as exc:
        _set_error(job_id, "invalid_request", str(exc))
        return

    if payload.mask_base64:
        try:
            mask_bytes = base64.b64decode(payload.mask_base64, validate=True)
            decode_mask_base64(payload.mask_base64)
        except Exception as exc:
            _set_error(job_id, "invalid_request", f"Invalid mask_base64: {exc}")
            return

    acquired = _semaphore.acquire(blocking=False)
    if not acquired:
        _set_error(job_id, "capacity_reached", "GPU busy, retry later")
        return

    try:
        for attempt in range(1, payload.max_iterations + 1):
            step: Literal["generate", "inpaint"] = "inpaint" if inpaint_next else "generate"
            inpaint_next = False

            try:
                if step == "inpaint":
                    if last_image is None or mask_bytes is None:
                        _set_error(job_id, "internal_error", "Inpaint requested without image/mask")
                        return
                    image_bytes, used_seed, effective, model_id = await inpaint_image_bytes(
                        current,
                        init_image_bytes=last_image,
                        mask_bytes=mask_bytes,
                        strength=_inpaint_strength,
                        registry=_registry,
                        timeout_seconds=_timeout_seconds,
                    )
                else:
                    image_bytes, used_seed, effective, model_id = await generate_image_bytes(
                        current,
                        registry=_registry,
                        timeout_seconds=_timeout_seconds,
                    )
            except asyncio.TimeoutError:
                _set_error(
                    job_id,
                    "generation_timeout",
                    f"{'Inpaint' if step == 'inpaint' else 'Generation'} timed out on attempt {attempt}",
                )
                return
            except Exception as exc:
                logger.exception("job_id=%s attempt=%s failed", job_id, attempt)
                _set_error(job_id, "internal_error", str(exc))
                return

            last_image = image_bytes
            if mask_bytes is None:
                mask_bytes = _resolve_mask_bytes(payload, last_image)

            evaluation = evaluate_output(
                goal,
                effective,
                attempt=attempt,
                output_image=image_bytes,
                reference_image=reference_bytes,
            )
            _append_iteration(job_id, evaluation, effective, used_seed, correction=step)

            if evaluation.passed:
                final_meta = build_metadata(
                    effective,
                    current,
                    model_id,
                    used_seed,
                )
                _set_converged(job_id, image_bytes, final_meta)
                return

            action, patched = resolve_correction(current, evaluation, payload, attempt=attempt)
            if action.kind == "tier_bump" and patched is not None:
                current = patched
            elif action.kind == "inpaint":
                if mask_bytes is None:
                    break
                inpaint_next = True
            else:
                break

        _set_failed(job_id, last_image, final_meta)
    finally:
        _semaphore.release()


def _append_iteration(
    job_id: str,
    evaluation: EvalResult,
    effective: GenerateRequest,
    used_seed: int,
    *,
    correction: Literal["generate", "inpaint", "tier_bump"] | None = None,
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
                correction=correction,
            )
        )
    _update_job(record)


def _set_status(job_id: str, status: str) -> None:
    with _store_lock:
        record = _jobs[job_id]
        record.status = status  # type: ignore[assignment]
    _update_job(record)


def _attach_image(record: JobStatusResponse, image_bytes: bytes) -> None:
    record.image_url = job_store.save_artifact(record.job_id, image_bytes)
    # Keep base64 for older clients; new clients should prefer image_url.
    record.image_base64 = base64.b64encode(image_bytes).decode("utf-8")


def _set_converged(job_id: str, image_bytes: bytes, metadata: dict[str, Any]) -> None:
    with _store_lock:
        record = _jobs[job_id]
        record.status = "converged"
        record.metadata = metadata
        record.message = "Goal criteria met"
        _attach_image(record, image_bytes)
    _update_job(record)


def _set_failed(job_id: str, image_bytes: bytes | None, metadata: dict[str, Any] | None) -> None:
    with _store_lock:
        record = _jobs[job_id]
        record.status = "failed"
        record.error_code = "convergence_failed"
        record.message = "Max iterations reached without passing evaluation"
        if image_bytes is not None:
            _attach_image(record, image_bytes)
        if metadata is not None:
            record.metadata = metadata
    _update_job(record)


def _set_error(job_id: str, error_code: str, message: str) -> None:
    with _store_lock:
        record = _jobs[job_id]
        record.status = "error"
        record.error_code = error_code
        record.message = message
    _update_job(record)
