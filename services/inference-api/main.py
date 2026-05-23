"""
FastAPI entrypoint: HTTP routes, middleware, metrics, and GPU backpressure.

Business logic lives in generation_service, jobs, router, and engine.
See services/inference-api/README.md and docs/CODEBASE.md.
"""

from __future__ import annotations

import asyncio
import base64
import traceback
import threading
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api_auth import require_api_key
from api_config import (
    API_KEY_HEADER,
    APP_ENV,
    CHAT_TIMEOUT_SECONDS,
    EXPECTED_API_KEY,
    GENERATION_TIMEOUT_SECONDS,
    INPAINT_STRENGTH,
    MAX_INFLIGHT_GENERATIONS,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    SDXL_MODEL_PATH,
)
from chat_service import chat_completion, load_chat_model
from api_logging import configure_logging, log_error, log_info
from model_catalog import get_chat_model, list_capabilities, list_models_payload
from device import get_runtime_device
from generation_service import generate_image_bytes, inpaint_image_bytes
import jobs as jobs_module
from rate_limit import check_and_record_rate_limit
from registry import EngineRegistry
from router import apply_quality_tier
from schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    GenerateRequest,
    GenerateResponse,
    InpaintRequest,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
)
from sdxl_adapter import build_metadata, effective_inpaint_request

app = FastAPI(
    title="SDXL Image Generation API",
    description="Stateless SDXL REST API (generate, inpaint, async jobs).",
)

registry = EngineRegistry(default_model_path=SDXL_MODEL_PATH)
logger = configure_logging()

_metrics_lock = threading.Lock()
_generate_semaphore = threading.Semaphore(MAX_INFLIGHT_GENERATIONS)
jobs_module.configure(
    registry,
    GENERATION_TIMEOUT_SECONDS,
    _generate_semaphore,
    inpaint_strength=INPAINT_STRENGTH,
)

_metrics: dict[str, int | float] = {
    "requests_total": 0,
    "requests_inflight": 0,
    "requests_success_total": 0,
    "requests_error_total": 0,
    "generate_requests_total": 0,
    "generate_success_total": 0,
    "generate_error_total": 0,
    "generate_latency_ms_total": 0.0,
    "generate_inflight": 0,
    "generate_rejected_total": 0,
    "generate_accepted_total": 0,
    "generate_timeout_total": 0,
}


def _rate_limited_response(request_id: str) -> JSONResponse:
    log_error(logger, "request rejected reason=rate_limited", request_id)
    response = JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "error_code": "rate_limited",
            "message": "Rate limit exceeded",
            "request_id": request_id,
        },
    )
    response.headers["Retry-After"] = str(RATE_LIMIT_WINDOW_SECONDS)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.perf_counter()

    with _metrics_lock:
        _metrics["requests_total"] += 1
        _metrics["requests_inflight"] += 1

    log_info(logger, f"{request.method} {request.url.path} started", request_id)
    try:
        response = await call_next(request)
    except Exception:
        with _metrics_lock:
            _metrics["requests_error_total"] += 1
            _metrics["requests_inflight"] -= 1
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    with _metrics_lock:
        _metrics["requests_inflight"] -= 1
        if response.status_code >= 400:
            _metrics["requests_error_total"] += 1
        else:
            _metrics["requests_success_total"] += 1

    response.headers["X-Request-ID"] = request_id
    log_info(
        logger,
        f"{request.method} {request.url.path} completed status={response.status_code} duration_ms={duration_ms:.2f}",
        request_id,
    )
    return response

# --- Global Error Management ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Unified error response for production safety."""
    request_id = getattr(request.state, "request_id", "unknown")
    log_error(logger, f"{type(exc).__name__}: {exc}", request_id)

    content: dict[str, str] = {
        "status": "error",
        "message": "Internal GPU Inference Error",
        "request_id": request_id,
        "error_code": "internal_error",
    }
    if APP_ENV == "dev":
        content["details"] = str(exc)
        traceback.print_exc()

    response = JSONResponse(status_code=500, content=content)
    response.headers["X-Request-ID"] = request_id
    return response

# --- Endpoints ---
@app.post("/generate", response_model=GenerateResponse, responses={
    429: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
})

async def generate(payload: GenerateRequest, http_request: Request) -> GenerateResponse | JSONResponse:
    """
    Primary inference endpoint.
    Uses asyncio.run_in_executor to offload PyTorch to background threads.
    """
    unauthorized = require_api_key(http_request)
    if unauthorized is not None:
        return unauthorized

    # ------------------------------------------------------------
    # Rate-limit gate (per API key, sliding time window)
    # ------------------------------------------------------------
    # Why this is here:
    # - Auth tells us WHO is calling.
    # - Rate limiting controls HOW OFTEN they can call.
    # - We do this before expensive GPU work to fail fast and protect capacity.
    #
    # Behavior:
    # - If key exceeded allowed requests in the window:
    #     -> return HTTP 429
    #     -> error_code="rate_limited"
    #     -> include Retry-After header
    # - Otherwise continue normal generation flow.
    request_id = getattr(http_request.state, "request_id", "unknown")
    provided_api_key = http_request.headers.get(API_KEY_HEADER, "")

    if not check_and_record_rate_limit(provided_api_key):
        return _rate_limited_response(request_id)

    # 1. Count every attempt first
    with _metrics_lock:
        _metrics["generate_requests_total"] += 1

    # 2. Capacity gate
    # Capacity gate controls concurrent in-flight work (different from per-key rate limiting).
    acquired = _generate_semaphore.acquire(blocking=False)
    if not acquired:
        with _metrics_lock:
            _metrics["generate_rejected_total"] += 1
        request_id = getattr(http_request.state, "request_id", "unknown")
        log_error(logger, "POST /generate rejected reason=capacity_reached", request_id)

        response = JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "error_code": "capacity_reached",
                "message": "GPU busy, retry later",
                "request_id": request_id,
            },
        )
        response.headers["Retry-After"] = "5"
        response.headers["X-Request-ID"] = request_id
        return response

    # 3. Accepted path
    with _metrics_lock:
        _metrics["generate_accepted_total"] += 1
        _metrics["generate_inflight"] += 1

    _effective, model_id = apply_quality_tier(payload)
    try:
        registry.get_engine(model_id)
    except ValueError as exc:
        log_error(logger, "POST /generate rejected reason=unsupported_model_id", request_id)
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "error_code": "unsupported_model_id",
                "message": str(exc),
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    start = time.perf_counter()
    try:
        image_bytes, used_seed, effective, model_id = await generate_image_bytes(
            payload,
            registry=registry,
            timeout_seconds=GENERATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        with _metrics_lock:
            _metrics["generate_timeout_total"] += 1
        request_id = getattr(http_request.state, "request_id", "unknown")
        log_error(logger, "POST /generate timed out", request_id)
        response = JSONResponse(
            status_code=504,
            content={
                "status": "error",
                "error_code": "generation_timeout",
                "message": "Generation timed out",
                "request_id": request_id,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        with _metrics_lock:
            _metrics["generate_error_total"] += 1
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        with _metrics_lock:
            _metrics["generate_latency_ms_total"] += duration_ms
            _metrics["generate_inflight"] -= 1
        _generate_semaphore.release()

    with _metrics_lock:
        _metrics["generate_success_total"] += 1


    

    # Encode raw bytes to Base64 (Stateless Delivery)
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    return GenerateResponse(
        status="success",
        image_base64=image_base64,
        metadata=build_metadata(effective, payload, model_id, used_seed),
    )


@app.post("/inpaint", response_model=GenerateResponse, responses={
    429: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
})
async def inpaint(
    payload: InpaintRequest,
    http_request: Request,
) -> GenerateResponse | JSONResponse:
    """Repaint masked region of an existing image (SDXL inpaint pipeline)."""
    unauthorized = require_api_key(http_request)
    if unauthorized is not None:
        return unauthorized

    request_id = getattr(http_request.state, "request_id", "unknown")
    provided_api_key = http_request.headers.get(API_KEY_HEADER, "")
    if not check_and_record_rate_limit(provided_api_key):
        return _rate_limited_response(request_id)

    acquired = _generate_semaphore.acquire(blocking=False)
    if not acquired:
        response = JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "error_code": "capacity_reached",
                "message": "GPU busy, retry later",
                "request_id": request_id,
            },
        )
        response.headers["Retry-After"] = "5"
        response.headers["X-Request-ID"] = request_id
        return response

    effective, model_id = effective_inpaint_request(payload)
    gen_payload = effective
    try:
        registry.get_engine(model_id)
    except ValueError as exc:
        _generate_semaphore.release()
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "error_code": "unsupported_model_id",
                "message": str(exc),
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    try:
        init_bytes = base64.b64decode(payload.image_base64, validate=True)
        mask_bytes = base64.b64decode(payload.mask_base64, validate=True)
    except Exception:
        _generate_semaphore.release()
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "error_code": "invalid_request",
                "message": "Invalid image_base64 or mask_base64",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    start = time.perf_counter()
    try:
        image_bytes, used_seed, effective, model_id = await inpaint_image_bytes(
            gen_payload,
            init_image_bytes=init_bytes,
            mask_bytes=mask_bytes,
            strength=payload.strength,
            registry=registry,
            timeout_seconds=GENERATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        response = JSONResponse(
            status_code=504,
            content={
                "status": "error",
                "error_code": "generation_timeout",
                "message": "Inpaint timed out",
                "request_id": request_id,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        raise
    finally:
        _generate_semaphore.release()

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    meta = build_metadata(effective, gen_payload, model_id, used_seed)
    meta["inpaint_strength"] = payload.strength
    return GenerateResponse(
        status="success",
        image_base64=image_base64,
        metadata=meta,
    )


@app.post(
    "/jobs",
    response_model=JobCreateResponse,
    status_code=202,
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
async def create_job(
    payload: JobCreateRequest,
    http_request: Request,
) -> JobCreateResponse | JSONResponse:
    """Start async generate → evaluate → correct loop (in-process worker)."""
    unauthorized = require_api_key(http_request)
    if unauthorized is not None:
        return unauthorized

    request_id = getattr(http_request.state, "request_id", "unknown")
    provided_api_key = http_request.headers.get(API_KEY_HEADER, "")
    if not check_and_record_rate_limit(provided_api_key):
        return _rate_limited_response(request_id)

    record = jobs_module.create_job(payload)
    jobs_module.schedule_job(record.job_id, payload)
    return JobCreateResponse(job_id=record.job_id, status="queued")


@app.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_job_status(
    job_id: str,
    http_request: Request,
) -> JobStatusResponse | JSONResponse:
    unauthorized = require_api_key(http_request)
    if unauthorized is not None:
        return unauthorized

    record = jobs_module.get_job(job_id)
    if record is None:
        request_id = getattr(http_request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error_code": "job_not_found",
                "message": f"Unknown job_id: {job_id}",
                "request_id": request_id,
            },
        )
    return record


@app.get("/metrics", response_model=None)
async def metrics(http_request: Request) -> dict[str, int | float] | JSONResponse:
    unauthorized = require_api_key(http_request)
    if unauthorized is not None:
        return unauthorized

        

    with _metrics_lock:
        generate_accepted_total = int(_metrics["generate_accepted_total"])
        avg_generate_latency_ms = (
            float(_metrics["generate_latency_ms_total"]) / generate_accepted_total
            if generate_accepted_total > 0
            else 0.0
        )
        return {
            "requests_total": int(_metrics["requests_total"]),
            "requests_inflight": int(_metrics["requests_inflight"]),
            "requests_success_total": int(_metrics["requests_success_total"]),
            "requests_error_total": int(_metrics["requests_error_total"]),
            "generate_requests_total": int(_metrics["generate_requests_total"]),
            "generate_success_total": int(_metrics["generate_success_total"]),
            "generate_error_total": int(_metrics["generate_error_total"]),
            "generate_latency_ms_total": round(float(_metrics["generate_latency_ms_total"]), 3),
            "generate_latency_ms_avg": round(avg_generate_latency_ms, 3),
            "generate_inflight": int(_metrics["generate_inflight"]),
            "generate_rejected_total": int(_metrics["generate_rejected_total"]),
            "generate_accepted_total": generate_accepted_total,
            "generate_timeout_total": int(_metrics["generate_timeout_total"]),
        }

@app.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def chat(
    payload: ChatRequest,
    http_request: Request,
) -> ChatResponse | JSONResponse:
    """
    Text completion via catalog GGUF models (llama.cpp).

    Not for images — use POST /generate. See GET /models for model_id values.
    """
    unauthorized = require_api_key(http_request)
    if unauthorized is not None:
        return unauthorized

    request_id = getattr(http_request.state, "request_id", "unknown")
    provided_api_key = http_request.headers.get(API_KEY_HEADER, "")
    if not check_and_record_rate_limit(provided_api_key):
        return _rate_limited_response(request_id)

    try:
        spec = get_chat_model(payload.model_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "error_code": "unsupported_model_id",
                "message": str(exc),
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    if not spec.is_on_disk():
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error_code": "model_not_available",
                "message": (
                    f"GGUF not on disk for {payload.model_id}. On GPU VM run: "
                    f"python scripts/download_gguf_model.py {payload.model_id}"
                ),
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    acquired = _generate_semaphore.acquire(blocking=False)
    if not acquired:
        return JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "error_code": "capacity_reached",
                "message": "GPU busy, retry later",
                "request_id": request_id,
            },
            headers={"Retry-After": "5", "X-Request-ID": request_id},
        )

    try:
        text, meta = await chat_completion(
            payload,
            registry=registry,
            timeout_seconds=CHAT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={
                "status": "error",
                "error_code": "chat_timeout",
                "message": "Chat completion timed out",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )
    except FileNotFoundError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error_code": "model_not_available",
                "message": f"GGUF missing for {payload.model_id}",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )
    except RuntimeError as exc:
        log_error(logger, f"POST /chat failed: {exc}", request_id)
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error_code": "model_load_failed",
                "message": str(exc),
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )
    finally:
        _generate_semaphore.release()

    return ChatResponse(status="success", text=text, metadata=meta)


@app.post("/models/{model_id}/load")
async def load_chat_model_endpoint(
    model_id: str,
    http_request: Request,
) -> JSONResponse:
    """Load a chat GGUF into VRAM (unloads SDXL). Call when user picks a model in the UI."""
    unauthorized = require_api_key(http_request)
    if unauthorized is not None:
        return unauthorized

    request_id = getattr(http_request.state, "request_id", "unknown")
    provided_api_key = http_request.headers.get(API_KEY_HEADER, "")
    if not check_and_record_rate_limit(provided_api_key):
        return _rate_limited_response(request_id)

    try:
        spec = get_chat_model(model_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "error_code": "unsupported_model_id",
                "message": str(exc),
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    if not spec.is_on_disk():
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error_code": "model_not_available",
                "message": (
                    f"GGUF not on disk for {model_id}. On GPU VM run: "
                    f"python scripts/download_gguf_model.py {model_id}"
                ),
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    acquired = _generate_semaphore.acquire(blocking=True)
    try:
        meta = await load_chat_model(
            model_id,
            registry=registry,
            timeout_seconds=CHAT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={
                "status": "error",
                "error_code": "model_load_timeout",
                "message": "Model load timed out",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )
    except RuntimeError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error_code": "model_load_failed",
                "message": str(exc),
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )
    finally:
        _generate_semaphore.release()

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "model_id": meta["model_id"],
            "message": "Model loaded into VRAM",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


@app.get("/models")
async def list_models() -> dict[str, list]:
    """Dynamic model catalog (image + chat), including on_disk status."""
    return {"models": list_models_payload()}


@app.get("/capabilities")
async def capabilities() -> dict[str, list]:
    """Model capability manifest for planners and clients (no auth)."""
    return {"models": list_capabilities()}


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Engine and hardware status check."""
    return {
        "status": "healthy",
        "engine": get_runtime_device(),
        "backend": "diffusers",
        "optimization": "lightning",
    }