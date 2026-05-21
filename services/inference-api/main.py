import asyncio
import base64
import os
import traceback
import time
import uuid
import threading
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from schemas import (
    ErrorResponse,
    GenerateRequest,
    GenerateResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
)
from registry import EngineRegistry
from router import apply_quality_tier
import jobs as jobs_module
from generation_service import generate_image_bytes
from sdxl_adapter import build_metadata

# Repo root: .../image-sd (models live at <repo>/models/sdxl-base)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MODEL = _REPO_ROOT / "models" / "sdxl-base"
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW_SECONDS = 60


# --- Modern API Initialization ---
app = FastAPI(
    title="SDXL Image Generation API",
    description="Stateless SDXL-Lightning REST API optimized for M3 Pro."
)

# Lazy engine cache; first /generate loads weights (see registry.get_engine).
registry = EngineRegistry(
    default_model_path=os.environ.get("SDXL_MODEL_PATH", str(_DEFAULT_MODEL)),
)
logger = logging.getLogger("sdxl_api")


class RequestIdFilter(logging.Filter):
    """
    Logging filter that guarantees `request_id` exists on every log record.

    Why this exists:
    - Our logging formatter expects `%(request_id)s`.
    - Third-party logs (or logs outside middleware context) may not set it.
    - Without this filter, formatting can raise KeyError.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        # If request_id was not injected by middleware, add a safe fallback.
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        # Returning True tells logging to emit the record.
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
)
for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIdFilter())

APP_ENV = os.getenv("APP_ENV", "dev").lower()
API_KEY_HEADER = "X-API-Key"
EXPECTED_API_KEY = os.getenv("SDXL_API_KEY", "dev-local-key")

_metrics_lock = threading.Lock()

MAX_INFLIGHT_GENERATIONS = 1
GENERATION_TIMEOUT_SECONDS = int(os.getenv("GENERATION_TIMEOUT_SECONDS", "90"))
_generate_semaphore = threading.Semaphore(MAX_INFLIGHT_GENERATIONS)
jobs_module.configure(registry, GENERATION_TIMEOUT_SECONDS, _generate_semaphore)

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


def _log_info(message: str, request_id: str) -> None:
    logger.info(message, extra={"request_id": request_id})


def _log_error(message: str, request_id: str) -> None:
    logger.error(message, extra={"request_id": request_id})


def _auth_error_response(request_id: str) -> JSONResponse:
    response = JSONResponse(
        status_code=401,
        content={
            "status": "error",
            "error_code": "unauthorized",
            "message": "Invalid or missing API key",
            "request_id": request_id,
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


def _require_api_key(http_request: Request) -> JSONResponse | None:
    request_id = getattr(http_request.state, "request_id", "unknown")
    provided_api_key = http_request.headers.get(API_KEY_HEADER)
    if provided_api_key != EXPECTED_API_KEY:
        _log_error("request rejected reason=invalid_api_key", request_id)
        return _auth_error_response(request_id)
    return None


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
    unauthorized = _require_api_key(http_request)
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

    if not _check_and_record_rate_limit(provided_api_key):
        _log_error("POST /generate rejected reason=rate_limited", request_id)
        response = JSONResponse(
            status_code=429,
            content={
                "status":"error",
                "error_code":"rate_limited",
                "message":"Rate limit exceeded",
                "request_id":request_id,
            },
        )
        response.headers["Retry-After"] = str(RATE_LIMIT_WINDOW_SECONDS)
        response.headers["X-Request-ID"] = request_id
        return response

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

    _effective, model_id = apply_quality_tier(payload)
    try:
        registry.get_engine(model_id)
    except ValueError as exc:
        _log_error("POST /generate rejected reason=unsupported_model_id", request_id)
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
        metadata=build_metadata(effective, payload, model_id, used_seed),
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
    unauthorized = _require_api_key(http_request)
    if unauthorized is not None:
        return unauthorized

    request_id = getattr(http_request.state, "request_id", "unknown")
    provided_api_key = http_request.headers.get(API_KEY_HEADER, "")
    if not _check_and_record_rate_limit(provided_api_key):
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
    unauthorized = _require_api_key(http_request)
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
    unauthorized = _require_api_key(http_request)
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

@app.get("/health")
async def health_check() -> dict[str, str]:
    """Engine and hardware status check."""
    return {
        "status": "healthy", 
        "engine": "mps", 
        "backend": "diffusers",
        "optimization": "lightning"
    }

from collections import deque
from dataclasses import dataclass
import time

@dataclass
class KeyRateState:
    """
    Per-API-key rate limit state.

    Attributes:
        request_timestamps:
            A deque storing timestamps of recent requests.
            The deque is maintained in chronological order.

    Invariant:
        All timestamps in this deque are within the active
        rate limit window after cleanup.
    """
    # Ordered timestamps (oldest on the left, newest on the right).
    # We pop from the left when entries age out of the time window.
    request_timestamps: deque[float]

# Global synchronization primitive protecting shared rate limit state.
# Ensures correctness under concurrent request handling.
_rate_limit_lock = threading.Lock()

# In-memory storage mapping API keys to their rate limit state.
#
# Example:
#
# {
#     "key1": KeyRateState([...timestamps...]),
#     "key2": KeyRateState([...timestamps...])
# }
#
# Lifetime:
# - Exists for the duration of the process
# - Cleared on service restart
_rate_limit_by_key: dict[str, KeyRateState] = {}

def _check_and_record_rate_limit(api_key: str) -> bool:
    """
    Check whether a request is allowed under the configured rate limit
    and record the request timestamp if allowed.

    This function performs three operations atomically:
    1) Removes timestamps outside the sliding window
    2) Evaluates current request count
    3) Records the new request if permitted

    Args:
        api_key:
            The API key associated with the incoming request.

    Returns:
        bool:
            True  -> request is allowed
            False -> rate limit exceeded

    Thread Safety:
        Protected by a global lock to prevent race conditions
        when multiple requests for the same key arrive concurrently.

    Time Complexity:
        O(k) where k is number of requests in the current window.
        Typically small due to bounded request rate.

    Failure Mode:
        If the limit is exceeded, the caller should return:
            HTTP 429
            error_code="rate_limited"
    """

    # Use monotonic clock to avoid issues if system time changes.
    # This guarantees timestamps always move forward.
    now =time.monotonic()

    # Critical section:
    # Protect shared dictionary and per-key state.
    with _rate_limit_lock:

        # Initialize state for new API key.
        if api_key not in _rate_limit_by_key:
            _rate_limit_by_key[api_key] = KeyRateState(request_timestamps=deque())

        state = _rate_limit_by_key[api_key]

        # Determine start of the active rate limit window.
        window_start = now - RATE_LIMIT_WINDOW_SECONDS

        # ------------------------------------------------------------------
        # Cleanup Phase
        # ------------------------------------------------------------------
        # Remove timestamps that fall outside the current window.
        # Because deque is ordered, we only check from the left.
        #
        # Example:
        # window = last 60 seconds
        #
        # Before:
        # [t-120, t-90, t-10]
        #
        # After cleanup:
        # [t-10]
        # ------------------------------------------------------------------
        while state.request_timestamps and state.request_timestamps[0] < window_start:
            state.request_timestamps.popleft()
            
        # ------------------------------------------------------------------
        # Limit Check
        # ------------------------------------------------------------------
        # If the number of remaining timestamps equals or exceeds
        # the configured request limit, reject the request.
        # ------------------------------------------------------------------
        if len(state.request_timestamps) >= RATE_LIMIT_REQUESTS:
            return False
        
        # ------------------------------------------------------------------
        # Record Request
        # ------------------------------------------------------------------
        # Append current timestamp to track this request.
        # ------------------------------------------------------------------
        state.request_timestamps.append(now)

        return True