# SDXL API Architecture

## Overview

This project is a **monorepo**: a local-first SDXL image generation API (Apple Silicon / MPS) plus a **Next.js** client. The system is intentionally structured with clear boundaries between:

- request validation and routing policy
- HTTP orchestration (auth, limits, jobs — future)
- inference execution
- web UI and server-side proxy
- observability and failure handling

The repository is code-only. Model weights, generated images, caches, and local virtual environments are intentionally excluded from git history.

**Companion conventions:** Repo-wide rules for monorepo layout (Next.js + FastAPI), SEO/product boundaries, contract testing, and merge checklists live in `.cursor/rules/` — start with `quality-and-contracts.mdc` and `monorepo-layout.mdc`. This document focuses on the **inference service** runtime; those rules cover full-stack and process expectations.

## Current System Shape

### `services/inference-api/schemas.py`

Defines the API contracts:

- `GenerateRequest` (includes optional `quality_tier`)
- `GenerateResponse`
- `ErrorResponse`

This layer protects the inference engine from invalid input shapes and keeps response/error formats explicit.

### `services/inference-api/router.py`

Maps `quality_tier` (`fast` | `balanced` | `quality`) to concrete `steps` and `guidance_scale` before inference. Returns `(effective_request, model_id)`; today `model_id` is always `sdxl_base`. Does not load alternate checkpoints yet.

### `services/inference-api/engine.py`

Owns the SDXL runtime:

- loads the local SDXL model from `<repo root>/models/sdxl-base` (or `SDXL_MODEL_PATH`)
- keeps the pipeline in memory
- serializes mutable pipeline access with an internal lock
- returns image bytes through `io.BytesIO`

This module is the only place that should know about model internals.

### `services/inference-api/main.py`

Owns API orchestration:

- FastAPI route definitions
- request ID middleware
- metrics collection
- backpressure control
- timeout handling
- global error handling
- offloading blocking inference with `run_in_executor`

This file should remain focused on transport, policy, and observability rather than model logic.

### `apps/web/`

Next.js product shell: public UI, `POST /api/generate` Route Handler (server-side proxy with `SDXL_API_KEY`), no torch.

### `services/inference-api/tests/`

- `test_integration_api.py` — ASGI tests with mocked GPU (auth, rate limit, backpressure, 500/504, success contract).
- `test_router.py` — unit tests for `apply_quality_tier` (no GPU).

These suites are the primary regression safety net for backend contract changes.

## Runtime Flow (inference API)

```mermaid
flowchart TD
    A["Client or Next proxy"] --> B["FastAPI Middleware"]
    B --> C["Request ID Assigned"]
    C --> D["Route Handler /generate"]
    D --> E["Pydantic Validation"]
    E --> Auth["API key + rate limit"]
    Auth --> F["Backpressure Check"]
    F -->|Rejected| G["429 capacity_reached or rate_limited"]
    F -->|Accepted| T["apply_quality_tier"]
    T --> H["run_in_executor"]
    H --> I["SDXLEngine.generate(effective)"]
    I --> K["SDXL Inference on MPS"]
    K --> L["BytesIO -> Base64 + metadata"]
    L --> M["200 Success Response"]
    H -->|Timeout| N["504 generation_timeout"]
    D -->|Unhandled error| O["500 internal_error"]
    B --> P["Metrics + Structured Logs"]
```

## Request Lifecycle

### Success path

1. Client (or Next.js proxy) sends `POST /generate`.
2. Middleware assigns `request_id` and starts timing.
3. Request body is validated by `GenerateRequest`.
4. API key and per-key rate limit are enforced.
5. API checks generation capacity via semaphore.
6. `apply_quality_tier()` may override `steps` / `guidance_scale`; `model_id` is set for metadata.
7. If capacity is available, inference is offloaded to a worker thread with the **effective** request.
8. `engine.generate()` runs scheduler configuration and MPS inference.
9. Output image is encoded in memory and returned as Base64 JSON with metadata (`model_id`, `quality_tier`, effective steps/CFG, `seed`).
10. Metrics and request logs are updated.

### Backpressure path

1. Client sends `POST /generate`.
2. Capacity check fails immediately.
3. API returns `429` with `error_code="capacity_reached"`.
4. Response includes `Retry-After` and `X-Request-ID`.

### Timeout path

1. Inference starts in a background thread.
2. API waits with `asyncio.wait_for(...)`.
3. If timeout threshold is exceeded, API returns `504` with `error_code="generation_timeout"`.
4. Inflight counters and semaphore are still released from `finally`.

### Internal error path

1. Unexpected exception occurs during request handling.
2. Global exception handler returns `500`.
3. In `dev`, response includes `details`.
4. In non-`dev`, internal details are hidden.

## Reliability Controls

### Non-blocking I/O

The web server does not run PyTorch inference directly in the event loop. Inference is offloaded with:

- `asyncio.get_running_loop()`
- `loop.run_in_executor(...)`

This keeps the FastAPI server responsive under blocking GPU work.

### Backpressure

Generation concurrency is explicitly bounded with:

- `MAX_INFLIGHT_GENERATIONS`
- a semaphore guarding `/generate`

This prevents unbounded pile-up of expensive inference requests.

### Timeout policy

Generation is bounded by:

- `GENERATION_TIMEOUT_SECONDS`

This prevents a single slow request from holding API capacity forever.

### Thread safety

The engine uses a lock around mutable pipeline operations:

- scheduler changes
- clip-skip related text encoder mutation

This is necessary because the diffusers pipeline is stateful.

## Observability

Current observability features:

- `X-Request-ID` on all responses
- structured log messages with request ID
- `/metrics` endpoint with request/generation counters
- explicit counters for:
  - total requests
  - inflight requests
  - accepted/rejected generation requests
  - timeout count
  - latency totals and averages

## Repository Rules

These are intentional product and collaboration decisions:

- `models/` is not tracked in git
- `generated/` is not tracked in git
- `__pycache__/` is not tracked in git
- collaborators must fetch model assets separately

Git is used for source, tests, and documentation. Large model binaries are outside repo scope.

## Current Product Stage

The backend is currently in the “reliable inference service” stage.

Completed capabilities:

- local SDXL inference
- validation contracts
- static API key authentication for `/generate` and `/metrics`
- backpressure
- timeout handling
- typed error responses
- integration tests

Completed since initial milestone list:

- per-key rate limiting
- `quality_tier` routing (`router.py`) with metadata (`model_id`, effective steps/CFG)
- Next.js web app with Route Handler proxy (`apps/web`)

Next planned milestones:

1. integration test for `quality_tier` end-to-end
2. lazy-loaded engine manager (one active model in RAM)
3. async job API (`POST /jobs`, `GET /jobs/{id}`) for multi-step flows
4. orchestration layer (agent/planner above inference; tool calls into engines)
5. production deploy on GPU cloud (e.g. Spheron) with CUDA backend abstraction

## End-to-end architecture (current vs target)

### Today (M3 Pro MVP — synchronous)

```mermaid
flowchart TB
    subgraph Client
        U[User / Browser]
        WEB[Next.js apps/web]
    end

    subgraph Edge
        RH[Route Handler POST /api/generate]
    end

    subgraph Inference["services/inference-api"]
        MW[Middleware: X-Request-ID + metrics]
        AUTH[API key + rate limit]
        VAL[Pydantic GenerateRequest]
        RT[router.apply_quality_tier]
        BP[Semaphore: MAX_INFLIGHT=1]
        EX[run_in_executor]
        ENG[SDXLEngine singleton]
        MPS[PyTorch diffusers on MPS]
    end

    subgraph Local["MacBook M3 Pro"]
        RAM[(Unified memory)]
        WEIGHTS[(models/sdxl-base on disk)]
    end

    U --> WEB
    WEB --> RH
    RH -->|HTTP + X-API-Key server-side| MW
    MW --> AUTH --> VAL --> RT --> BP
    BP -->|accepted| EX --> ENG
    ENG --> MPS
    MPS --> RAM
    ENG -.->|load at startup| WEIGHTS
    MPS -->|JPEG base64 JSON| WEB
```

### Target (M3 Pro learning path → Spheron-ready)

```mermaid
flowchart TB
    subgraph Client
        U[User]
        WEB[Next.js]
    end

    subgraph Orchestration["Future: agent / planner (not in repo yet)"]
        PLAN[Planner: decompose prompt]
        POL[Policy: pick model + pipeline steps]
    end

    subgraph API["FastAPI inference-api"]
        SYNC[POST /generate sync — keep for simple calls]
        JOBS[POST /jobs async — multi-step / long runs]
        Q[Job queue + worker loop]
        ADM[RAM / inflight admission]
        REG[Engine registry]
        RT[quality_tier + model_id router]
    end

    subgraph Engines["Lazy-loaded engines (one hot at a time on Mac)"]
        E1[sdxl_base]
        E2[sdxl_lightning / future]
        E3[flux / inpaint — future]
    end

    subgraph Runtime
        MAC[M3 Pro: MPS + local weights]
        CLOUD[Spheron: CUDA GPU VM + object storage for weights]
    end

    U --> WEB --> API
    PLAN --> POL
    POL -->|tool: generate / inpaint / segment| JOBS
    POL -->|single-shot| SYNC
    JOBS --> Q --> ADM --> REG
    SYNC --> ADM --> REG
    RT --> REG
    REG -->|load on demand; unload previous| E1
    REG --> E2
    REG --> E3
    E1 --> MAC
    E2 --> MAC
    E1 --> CLOUD
    E2 --> CLOUD
```

### Request lifecycle (target async + lazy load)

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant Q as Job queue
    participant W as Worker
    participant R as Engine registry
    participant G as GPU engine

    C->>API: POST /jobs {prompt, quality_tier, plan?}
    API->>API: auth, validate, enqueue
    API-->>C: 202 {job_id, status: queued}

    W->>Q: claim next job
    W->>W: check RAM / inflight policy
    alt need different model
        W->>R: unload current / load model_id
        R->>G: load weights from disk or volume
    end
    W->>G: generate(effective_request)
  G-->>W: image bytes + metadata
    W->>Q: status succeeded + artifact ref

    C->>API: GET /jobs/{job_id}
    API-->>C: status + image_base64 or URL
```

## Tech debt (explicit)

| Area | What we have now | Debt if we rush multi-model / agents | Mitigation (do early) |
|------|------------------|--------------------------------------|------------------------|
| **Device** | Hard-coded `mps` in `engine.py` | Spheron uses **CUDA**; code paths diverge | `DEVICE` env (`mps` / `cuda` / `cpu`); single factory |
| **Model loading** | **Eager** singleton at import/startup | OOM if multiple pipelines; slow cold switch | `EngineRegistry` with `load(model_id)` / `unload()`; max one resident on Mac |
| **Routing** | `quality_tier` → steps/CFG only; always `sdxl_base` weights | “fast tier” without Lightning weights is misleading | Separate `model_id` from tier; honest 503 if weights missing |
| **API shape** | Sync `POST /generate` only | Long agent chains hit **timeouts** (90s) | Add **jobs** contract; keep `/generate` for single step |
| **Orchestration** | None (client → API) | Agent logic inside `main.py` | New module `orchestrator/` or external service; **tools** call inference API |
| **Artifacts** | Base64 in JSON | Huge payloads; bad for multi-step | Job result: file URL / object storage key on cloud |
| **Metrics** | Global counters | Cannot compare models/tiers | Label metrics by `model_id`, `quality_tier`, job status |
| **Health** | `optimization: lightning` vs **base** weights on disk | Ops confusion | Health reports `model_id`, `device`, `loaded_models` |
| **Deploy** | `make run` on laptop | No image, no GPU provider config | Dockerfile + `DEVICE=cuda` + model volume; Spheron deploy API for VM |
| **Tests** | Mocked engine | Registry/lazy load untested | Unit tests for router + registry; job state machine tests |

## MacBook M3 Pro (MVP) vs Spheron (production)

| Dimension | M3 Pro now | Spheron / GPU cloud later |
|-----------|------------|---------------------------|
| **Accelerator** | Apple **MPS** (unified memory) | NVIDIA **CUDA** (dedicated VRAM) |
| **Memory** | RAM shared with OS; easy **OOM** / swap | VRAM sized per instance (e.g. 24–80 GB); still need one-model discipline at first |
| **Concurrency** | Practically **1** heavy generation | Can raise inflight with bigger GPU; still queue for fairness |
| **Model storage** | `models/sdxl-base` local path | Download to volume on boot or pull from S3/R2; bake into image only if size acceptable |
| **Latency** | Cold MPS warmup; 20–60s+ for quality tiers | Often faster per step; pay for GPU minute |
| **Cost model** | CapEx (your machine) | Per-minute GPU; **lazy load** saves $ if instances stay up |
| **Agents** | Can run **locally** (small LLM) calling localhost API | Planner on CPU instance; inference on GPU instance (split services) |
| **Spheron fit** | N/A | Rent GPU VM, SSH or API deploy; optional Triton for multi-model serving at scale |

**Portable design rule:** keep **HTTP JSON contract** (`GenerateRequest`, `ErrorResponse`, job schemas) stable; swap **engine backend** and **storage** via env, not forks of `main.py`.

## How To Work On This Project

### Backend changes

Prefer editing:

- `services/inference-api/schemas.py` for API contract changes
- `services/inference-api/router.py` for tier → steps/CFG (and future model selection)
- `services/inference-api/main.py` for routing, policy, and metrics
- `services/inference-api/engine.py` for inference/runtime behavior
- `apps/web/src/app/api/generate/route.ts` and UI components for client/proxy changes

### Before pushing

Run:

```bash
make test-integration
```

### When changing contracts

If you modify:

- error payload shape
- `/generate` success fields
- backpressure behavior
- timeout behavior
- metrics keys

then update:

- integration tests
- `README.md`
- this architecture document if the design meaning changed
