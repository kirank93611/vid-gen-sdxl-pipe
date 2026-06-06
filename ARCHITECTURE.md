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

**Low-level detail (classes, HTTP tables, sequences):** [LLD.md](./LLD.md).

## Current System Shape

### `services/inference-api/schemas.py`

Defines the API contracts:

- `GenerateRequest` (includes optional `quality_tier`)
- `GenerateResponse`
- `ErrorResponse`

This layer protects the inference engine from invalid input shapes and keeps response/error formats explicit.

### `services/inference-api/router.py` / `generation_profiles.py`

Maps `generation_profile` (and legacy `quality_tier`) to concrete `steps`, `guidance_scale`, `scheduler`, etc. Returns `(effective_request, model_id)`. Supports `sdxl_base`, `ckpt_*` checkpoints, and LoRA fields on SDXL.

### Plug-and-play assets

| Module | Role |
|--------|------|
| `model_catalog.py` | Registered SDXL + GGUF chat models |
| `checkpoint_utils.py` | Filesystem SD 1.5 checkpoints → `ckpt_<stem>` |
| `lora_utils.py` | Filesystem LoRAs → `lora_name` |
| `model_registry.py` | Unified `GET /models` payload |
| `registry.py` | Lazy engine load, VRAM eviction on switch |

See [docs/MODELS.md](./docs/MODELS.md) for drop-in paths and ops.

### `services/inference-api/engine.py` / `sd15_engine.py`

Own SDXL and SD 1.5 runtimes (diffusers). SDXL supports LoRA fuse/unfuse and inpaint. Checkpoints use `StableDiffusionPipeline.from_single_file`.

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

### `services/inference-api/job_store.py`

Persists correction jobs across API restarts:

- **SQLite** at `generated/jobs.db` (`JOB_DB_PATH`) — full `JobStatusResponse` snapshots (without inline image bytes)
- **JPEG artifacts** at `generated/jobs/<job_id>/output.jpg` (`ARTIFACTS_DIR`)
- **`recover_interrupted_jobs()`** on startup — `queued` / `running` jobs become `error` with `error_code=server_restarted`

`jobs.py` writes through on every status change; `GET /jobs/{id}/artifact` serves the file.

### `apps/web/`

Next.js **Visual Studio**: `/` editor, `/chat` GGUF chat, `/explore` marketing. Server proxies under `src/app/api/` forward to inference (generate, jobs, models, loras, generation-profiles, chat).

Layout:

```text
apps/web/src/
├── app/                 Routes + BFF proxies
├── components/studio/   Editor UI (dock/, canvas, chat)
├── components/ui/       shadcn
└── lib/
    ├── api/             Catalog + generate clients, errors, inference config
    └── studio/          UI defaults, model helpers, profile utils
```

Secrets: `.env.local` (`SDXL_API_KEY`, `SDXL_INFERENCE_BASE`). No torch in the browser.

**Deploy:** `scripts/spheron_deploy_web.sh` on GPU VM; `make spheron-deploy` from Mac. See [README.md](./README.md).

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
    F -->|Accepted| T["apply_generation_policy"]
    T --> H["run_in_executor"]
    H --> I["EngineRegistry → SDXL or SD15"]
    I --> K["Inference on CUDA/MPS"]
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

1. Inference runs on a **single-worker** GPU executor (one diffusion at a time).
2. API waits with `asyncio.wait_for(...)`.
3. On timeout, a cooperative **cancel flag** is set; `SDXLEngine` stops between diffusion steps via `callback_on_step_end`.
4. The API **awaits executor shutdown** (up to `GENERATION_CANCEL_GRACE_SECONDS`) before releasing the capacity semaphore, so the next request does not overlap on MPS.
5. Client receives `504` with `error_code="generation_timeout"`.

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

- `GENERATION_TIMEOUT_SECONDS` (env, default `90`)

This prevents a single slow request from holding API capacity forever.

**Important:** `asyncio.wait_for` stops the HTTP wait; it does **not** cancel the GPU thread. See [Correction jobs](#correction-loop-first-mvp) and tech debt table.

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
- lazy-loaded `EngineRegistry` (`registry.py`)
- integration test for `quality_tier` metadata
- **Correction loop MVP** — `POST /jobs`, `GET /jobs/{job_id}` (see below)
- **SDXL inpaint** — `POST /inpaint`, job-step inpaint via `goal.use_inpaint_correction` + optional `mask_base64` / auto center mask (`image_utils.py`)
- **`DEVICE` env** — `cuda` / `mps` / `cpu` (`device.py`); `/health` reports runtime device
- **Spheron runbooks** — `scripts/spheron_*.sh`, `make spheron-deploy`, `make deploy-api` / `make deploy-web` on VM
- **Studio UI refresh** — bottom dock, product job tab, lime theme (`apps/web/src/components/studio/`)
- **Persisted jobs + artifact files** — `job_store.py` (SQLite + `generated/jobs/`), `image_url` on `JobStatusResponse`, `GET /jobs/{id}/artifact`

Next planned milestones:

1. **Benchmark evidence** — `make benchmark-product` / `make spheron-benchmark` on fixtures; record job loop vs baseline CLIP
2. **Reference-conditioned generation** — IP-Adapter / composite (reference today is CLIP-only, not pixel lock)
3. VLM rubric evaluator (composition, artifacts, readable text, etc.)
4. Thin planner LLM over fixed tools (goal → capability graph, not CFG knobs)

## Design layers (intent vs execution)

External reviews (May 2026) and product direction align on **four layers**. The planner must **not** encode per-model samplers or CFG; adapters do.

| Layer | Module(s) | Thinks in |
|-------|-----------|-----------|
| **Goal** | `schemas.VisualGoal`, job brief | `realism`, `preserve_product`, `task` |
| **Capability** | `capabilities.py` | `text_to_image`, `quality_tier_routing`, `inpainting` |
| **Policy** | `router.py`, `correction.py`, `quality_tier` | tier bumps, workflow retries |
| **Adapter** | `sdxl_adapter.py`, `engine.py`, `registry.py` | steps, CFG, scheduler for `sdxl_base` |

**Validation hypothesis (unproven):** closed-loop `generate → evaluate → correct` improves measurable quality on a **narrow** workflow. Until proven, avoid large planner/RAG systems.

## Correction loop (first MVP)

Stateful path for goal-seeking generation without holding a long HTTP connection on `/generate`.

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant J as jobs.py
    participant S as job_store
    participant E as evaluator
    participant P as correction
    participant A as SDXL adapter + engine

    C->>API: POST /jobs {goal, prompt, quality_tier}
    API-->>C: 202 job_id queued
    J->>S: save_job queued
    J->>A: generate (attempt 1)
    A-->>J: image bytes + effective params
    J->>E: evaluate_output(goal, effective)
    E-->>J: passed / issues[]
    J->>S: save_job iteration update
    alt not passed
        J->>P: resolve_correction (tier bump or inpaint)
        alt tier bump
            P-->>J: patched GenerateRequest
            J->>A: generate (attempt 2..N)
        else inpaint (center mask or mask_base64)
            J->>A: inpaint on last image
        end
    end
    J->>S: save_artifact output.jpg
    J-->>J: status converged | failed | error
    C->>API: GET /jobs/{job_id}
    API-->>C: iterations[], image_url, image_base64?
    C->>API: GET /jobs/{job_id}/artifact
    API-->>C: JPEG file
```

### Job persistence (survives API restart)

```mermaid
flowchart LR
    subgraph RAM["In-process"]
        J[jobs.py worker]
        M[_jobs memory cache]
    end

    subgraph Disk["Gitignored generated/"]
        DB[(jobs.db SQLite)]
        IMG[jobs/job_id/output.jpg]
    end

    J -->|every status change| M
    J -->|write-through| DB
    J -->|on converge/fail| IMG
    API[GET /jobs/id] --> M
    API -->|cache miss| DB
    API2[GET /jobs/id/artifact] --> IMG
```

| Status | Meaning |
|--------|---------|
| `converged` | Evaluator passed within `max_iterations` |
| `failed` | `error_code=convergence_failed` — no patch left or still failing |
| `error` | `generation_timeout`, `capacity_reached`, `internal_error`, `server_restarted`, etc. |

**Job outputs:** `JobStatusResponse.image_url` (preferred, e.g. `/jobs/{id}/artifact`) plus optional `image_base64` for backward compatibility. Artifacts live under `ARTIFACTS_DIR` (default `<repo>/generated/`).

**Evaluator v0** — rule-based tier/steps vs `VisualGoal` (policy escalation).

**Evaluator v1 (product vertical)** — when `reference_image_base64` is set and `preserve_product` or `product_similarity_min` is set, runs **CLIP image–image similarity** (`clip_evaluator.py`, default threshold `0.85`). CLIP measures coarse similarity, not SKU geometry lock.

**Corrector (`resolve_correction`)** — tier bump on policy issues; on `product_similarity_low` with `goal.use_inpaint_correction` (and optional `mask_base64`), may schedule an **inpaint** step after attempt ≥ 2 using `StableDiffusionXLInpaintPipeline` (lazy-loaded). **Does not paste the reference JPEG into the scene.**

**Product expectation:** reference improves measurable CLIP and localized refinement; **faithful product composite** needs reference-conditioned generation (planned).

Stable error codes: `convergence_failed`, `job_not_found`, `artifact_not_found`, `server_restarted` (additive; do not rename without changelog).

### Benchmark harness (experimental proof)

Path: `benchmarks/product_similarity/` + `scripts/run_product_benchmark.py`.

For each manifest case with a fixture JPEG:

1. **Baseline** — one `POST /generate` → CLIP vs reference (computed in script).
2. **Job** — `POST /jobs` with `reference_image_base64` → poll → final CLIP + iteration log.

Outputs: `benchmarks/product_similarity/results/latest.json` and `latest.md` (gitignored). Use this to test the **unproven hypothesis**; do not treat positive `delta_clip` as product-market fit without human review.

## End-to-end architecture (current vs target)

### Today (M3 Pro MVP — sync generate + async jobs)

```mermaid
flowchart TB
    subgraph Client
        U[User / Browser]
        WEB[Next.js apps/web]
    end

    subgraph Edge["apps/web Route Handlers"]
        RH[POST /api/generate]
        RJ[POST/GET /api/jobs]
        RA[GET /api/jobs/id/artifact]
    end

    subgraph Inference["services/inference-api"]
        MW[Middleware: X-Request-ID + metrics]
        AUTH[API key + rate limit]
        VAL[Pydantic validation]
        RT[router.apply_quality_tier]
        BP[Semaphore: MAX_INFLIGHT=1]
        EX[run_in_executor]
        JOBS[jobs.py worker]
        STORE[job_store.py]
        REG[EngineRegistry]
        ENG[SDXLEngine]
        MPS[PyTorch diffusers on MPS/CUDA]
    end

    subgraph Local["Host disk — gitignored"]
        RAM[(Unified memory / VRAM)]
        WEIGHTS[(models/sdxl-base)]
        JDB[(generated/jobs.db)]
        JIMG[(generated/jobs/id/output.jpg)]
    end

    U --> WEB
    WEB --> RH
    WEB --> RJ
    WEB --> RA
    RH -->|POST /generate| MW
    RJ -->|POST/GET /jobs| MW
    RA -->|GET /jobs/id/artifact| MW
    MW --> AUTH --> VAL --> RT --> BP
    BP -->|sync path| EX --> REG --> ENG
    MW -->|async path| JOBS
    JOBS --> BP
    JOBS --> REG
    JOBS -->|write-through| STORE
    STORE --> JDB
    JOBS -->|converged JPEG| JIMG
    RA --> JIMG
    ENG --> MPS
    MPS --> RAM
    ENG -.-> WEIGHTS
    RH -->|base64 JSON| WEB
    RJ -->|status + image_url| WEB
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
        ART[GET /jobs/id/artifact]
        Q[In-process job worker]
        STORE[job_store SQLite + JPEG artifacts]
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
    Q --> STORE
    ART --> STORE
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
    participant J as jobs.py
    participant S as job_store
    participant R as Engine registry
    participant G as GPU engine

    C->>API: POST /jobs {prompt, quality_tier, plan?}
    API->>API: auth, validate
    API->>J: create_job
    J->>S: save_job queued
    API-->>C: 202 {job_id, status: queued}

    J->>J: asyncio worker + semaphore
    alt need different model
        J->>R: unload current / load model_id
        R->>G: load weights from disk or volume
    end
    J->>G: generate / inpaint / evaluate loop
    G-->>J: image bytes + metadata
    J->>S: save_artifact output.jpg
    J->>S: save_job converged

    C->>API: GET /jobs/{job_id}
    API->>S: load_job on cache miss
    API-->>C: status + image_url + iterations
    C->>API: GET /jobs/{job_id}/artifact
    API-->>C: JPEG file
```

## Tech debt (explicit)

| Area | What we have now | Debt if we rush multi-model / agents | Mitigation (do early) |
|------|------------------|--------------------------------------|------------------------|
| **Device** | `DEVICE` env via `device.py` (done) | Multi-GPU routing not supported | Document per-host defaults in README |
| **Model loading** | `EngineRegistry` lazy per `model_id` | OOM if multiple pipelines; no unload yet | `unload()`; max one resident on Mac |
| **Routing** | `quality_tier` → steps/CFG only; always `sdxl_base` weights | “fast tier” without Lightning weights is misleading | Separate `model_id` from tier; honest 503 if weights missing |
| **API shape** | Sync `/generate` + in-process **jobs** (no external queue) | No Redis/SQS; single-process worker | External queue later if multi-instance |
| **Correction** | Rules + CLIP + tier/inpaint on jobs | Inpaint does not composite reference SKU | IP-Adapter / mask composite; tune timeouts per host |
| **Orchestration** | None (client → API) | Agent logic inside `main.py` | New module `orchestrator/` or external service; **tools** call inference API |
| **Artifacts** | SQLite + local JPEG + `image_url`; base64 still returned | Single-host disk only; no CDN | Object storage URLs on cloud; drop base64 from JSON when clients migrated |
| **Metrics** | Global counters | Cannot compare models/tiers | Label metrics by `model_id`, `quality_tier`, job status |
| **Health** | `optimization: lightning` vs **base** weights on disk | Ops confusion | Health reports `model_id`, `device`, `loaded_models` |
| **Deploy** | README + `spheron_*` scripts (SSH/rsync) | No Dockerfile / IaC yet | Container image; health checks in orchestrator |
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
- `services/inference-api/router.py` for tier → steps/CFG (policy; moves toward adapter)
- `services/inference-api/sdxl_adapter.py` for effective request + metadata
- `services/inference-api/evaluator.py` / `correction.py` for closed-loop policy patches
- `services/inference-api/jobs.py` for async correction jobs
- `services/inference-api/main.py` for routing, policy, and metrics
- `services/inference-api/engine.py` for inference/runtime behavior (SDXL adapter backend)
- `apps/web/src/app/api/*` and `apps/web/src/components/studio/*` for UI/proxy changes

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
