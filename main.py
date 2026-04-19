import asyncio
import base64
import os
import traceback
import time
import uuid
import threading
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from schemas import GenerateRequest, GenerateResponse, ErrorResponse
from engine import SDXLEngine

# --- Modern API Initialization ---
app = FastAPI(
    title="SDXL Image Generation API",
    description="Stateless SDXL-Lightning REST API optimized for M3 Pro."
)

# Shared global engine instance
# Initialized at startup for Apple Silicon memory stability
engine = SDXLEngine(model_path="./models/sdxl-base")
logger = logging.getLogger("sdxl_api")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
)
for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIdFilter())

APP_ENV = os.getenv("APP_ENV", "dev").lower()

_metrics_lock = threading.Lock()

MAX_INFLIGHT_GENERATIONS = 1
GENERATION_TIMEOUT_SECONDS = 45
_generate_semaphore = threading.Semaphore(MAX_INFLIGHT_GENERATIONS)

_metrics: dict[str, int | float] = {
    "requests_total": 0,
    "requests_inflight": 0,
    "requests_success_total": 0,
    "requests_error_total": 0,
    "generate_requests_total": 0,
    "generate_success_total": 0,
    "generate_error_total": 0,
    "generate_latency_ms_total": 0.0,
    "generate_inflight":0,
    "generate_rejected_total":0,
    "generate_accepted_total":0,
    "generate_timeout_total": 0,
}


def _log_info(message: str, request_id: str) -> None:
    logger.info(message, extra={"request_id": request_id})


def _log_error(message: str, request_id: str) -> None:
    logger.error(message, extra={"request_id": request_id})


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.perf_counter()

    with _metrics_lock:
        _metrics["requests_total"] += 1
        _metrics["requests_inflight"] += 1

    _log_info(f"{request.method} {request.url.path} started", request_id)
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
    _log_info(
        f"{request.method} {request.url.path} completed status={response.status_code} duration_ms={duration_ms:.2f}",
        request_id,
    )
    return response

# --- Global Error Management ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Unified error response for production safety."""
    request_id = getattr(request.state, "request_id", "unknown")
    _log_error(f"{type(exc).__name__}: {exc}", request_id)

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
    loop = asyncio.get_running_loop()

    # 1. Count every attempt first
    with _metrics_lock:
        _metrics["generate_requests_total"] += 1

    # 2. Capacity gate
    acquired = _generate_semaphore.acquire(blocking=False)
    if not acquired:
        with _metrics_lock:
            _metrics["generate_rejected_total"] += 1
        request_id = getattr(http_request.state, "request_id", "unknown")
        _log_error("POST /generate rejected reason=capacity_reached", request_id)

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

    
    # Offload the blocking CPU/GPU bound task
    start = time.perf_counter()
    try:
        image_bytes, used_seed = await asyncio.wait_for(
            loop.run_in_executor(None, engine.generate, payload),
            timeout=GENERATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        with _metrics_lock:
            _metrics["generate_timeout_total"] += 1
        request_id = getattr(http_request.state, "request_id", "unknown")
        _log_error("POST /generate timed out", request_id)
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
        metadata={
            "prompt": payload.prompt,
            "width": payload.width,
            "height": payload.height,
            "steps": payload.steps,
            "guidance_scale": payload.guidance_scale,
            "clip_skip": payload.clip_skip,
            "scheduler": payload.scheduler,
            "seed": used_seed,
        }
    )

@app.get("/metrics")
async def metrics() -> dict[str, int | float]:
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

@app.get("/health")
async def health_check() -> dict[str, str]:
    """Engine and hardware status check."""
    return {
        "status": "healthy", 
        "engine": "mps", 
        "backend": "diffusers",
        "optimization": "lightning"
    }
