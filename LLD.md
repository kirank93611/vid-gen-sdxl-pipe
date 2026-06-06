# Low-Level Design (LLD) — image-sd

Companion to [ARCHITECTURE.md](./ARCHITECTURE.md) (system context, roadmap, tech debt). This document specifies **modules, classes, HTTP contracts, concurrency, and sequences** as implemented or planned in-repo.

**Scope:** `services/inference-api/` + `apps/web/` proxy.  
**Runtime target (MVP):** macOS Apple Silicon, MPS, local weights at `models/sdxl-base`.  
**Production target:** GPU VM (e.g. Spheron), CUDA, same HTTP contract.

---

## 1. Component diagram

```mermaid
flowchart TB
    subgraph ClientTier["Client tier"]
        Browser[Browser]
    end

    subgraph WebTier["apps/web — Next.js"]
        Page[src/app/page.tsx StudioEditor]
        Explore[src/app/explore/page.tsx]
        ProxyGen[src/app/api/generate/route.ts]
        ProxyJobs[src/app/api/jobs/route.ts]
        ProxyArt[src/app/api/jobs/jobId/artifact/route.ts]
    end

    subgraph APITier["services/inference-api — FastAPI"]
        MW[request_context_middleware]
        Routes[main.py routes]
        Schemas[schemas.py]
        Router[router.py]
        Registry[registry.py]
        Jobs[jobs.py worker]
        Store[job_store.py]
        Engine[engine.py SDXLEngine]
    end

    subgraph DataTier["Local data — gitignored"]
        Weights[(models/sdxl-base)]
        JobDB[(generated/jobs.db)]
        JobImg[(generated/jobs/id/output.jpg)]
        Env[.env / .env.local]
    end

    Browser --> Page
    Browser --> Explore
    Page -->|POST /api/generate or /api/jobs| ProxyGen
    Page --> ProxyJobs
    Page -->|GET /api/jobs/id/artifact| ProxyArt
    ProxyGen -->|POST /generate + X-API-Key| MW
    ProxyJobs -->|POST/GET /jobs + X-API-Key| MW
    ProxyArt -->|GET /jobs/id/artifact| MW
    MW --> Routes
    Routes --> Schemas
    Routes --> Router
    Routes --> Jobs
    Jobs --> Store
    Routes --> Registry
    Registry --> Engine
    Engine --> Weights
    Store --> JobDB
    Store --> JobImg
    ProxyGen -.->|SDXL_API_URL SDXL_API_KEY| Env
    ProxyJobs -.->|SDXL_JOBS_URL| Env
```

---

## 2. Module dependency graph

```mermaid
flowchart LR
    main[main.py]
    schemas[schemas.py]
    router[router.py]
    registry[registry.py]
    jobs[jobs.py]
    store[job_store.py]
    engine[engine.py]
    client[client.py]

    main --> schemas
    main --> router
    main --> registry
    main --> jobs
    main --> store
    jobs --> store
    jobs --> schemas
    registry --> engine
    router --> schemas
    engine --> schemas
    client -.->|HTTP only| main
```

| Module | Depends on | Must not depend on |
|--------|------------|-------------------|
| `schemas.py` | pydantic only | torch, diffusers, FastAPI |
| `router.py` | `schemas` | torch, FastAPI |
| `engine.py` | torch, diffusers, `schemas` | FastAPI Request/Response |
| `registry.py` | `engine` | FastAPI |
| `job_store.py` | `schemas`, sqlite3, pathlib | torch, FastAPI |
| `jobs.py` | `job_store`, `schemas`, evaluator, generation_service | FastAPI Request/Response |
| `main.py` | FastAPI, `schemas`, `router`, `registry`, `jobs`, `job_store` | diffusers pipeline internals |
| `client.py` | httpx/requests | — |

---

## 3. Class diagram (inference service)

```mermaid
classDiagram
    class GenerateRequest {
        +str prompt
        +str negative_prompt
        +int|None seed
        +int width
        +int height
        +int steps
        +float guidance_scale
        +int clip_skip
        +str scheduler
        +str|None quality_tier
    }

    class GenerateResponse {
        +str status
        +str image_base64
        +dict metadata
    }

    class ErrorResponse {
        +str status
        +str message
        +str request_id
        +str|None error_code
        +str|None details
    }

    class SDXLEngine {
        -str model_path
        -Pipeline pipeline
        -Lock _lock
        +load_model()
        +generate(req) bytes, int
    }

    class EngineRegistry {
        -str _default_model_path
        -dict _engines
        -Lock _lock
        +get_engine(model_id) SDXLEngine
    }

    class KeyRateState {
        +deque request_times
    }

    note for EngineRegistry "Implemented in registry.py;\nwire in main.py in progress"
    note for SDXLEngine "Eager load in __init__ today;\nfirst load moves to registry"

    EngineRegistry --> SDXLEngine : creates/caches
    SDXLEngine ..> GenerateRequest : reads
```

---

## 4. HTTP surface

| Method | Path | Auth | Response |
|--------|------|------|----------|
| `GET` | `/health` | No | `200` engine status JSON |
| `GET` | `/metrics` | `X-API-Key` | `200` counters |
| `POST` | `/generate` | `X-API-Key` | `200` / `401` / `422` / `429` / `500` / `504` |
| `POST` | `/jobs` | `X-API-Key` | `202` / `401` / `422` / `429` |
| `GET` | `/jobs/{job_id}` | `X-API-Key` | `200` / `401` / `404` |
| `GET` | `/jobs/{job_id}/artifact` | `X-API-Key` | `200` JPEG / `401` / `404` |
| `POST` | `/inpaint` | `X-API-Key` | `200` / `401` / `422` / `429` / `504` |
| — | `/docs` | No | OpenAPI UI |

### 4.1 Stable `error_code` values (product surface)

| HTTP | `error_code` | When |
|------|----------------|------|
| 401 | `unauthorized` | Missing/wrong API key |
| 422 | (validation) | Pydantic / unknown fields |
| 422 | `unsupported_model_id` | Registry rejects `model_id` |
| 404 | `job_not_found` | Unknown `job_id` on `GET /jobs/{id}` |
| 404 | `artifact_not_found` | Job exists but no JPEG on disk yet |
| (job body) | `convergence_failed` | Job `status=failed` after max iterations |
| (job body) | `server_restarted` | Job was `queued`/`running` when API restarted |
| 429 | `rate_limited` | Per-key sliding window exceeded |
| 429 | `capacity_reached` | Semaphore `MAX_INFLIGHT_GENERATIONS` |
| 500 | `internal_error` | Unhandled exception |
| 504 | `generation_timeout` | `asyncio.wait_for` exceeded |

### 4.2 Success metadata keys (`POST /generate`)

| Key | Source |
|-----|--------|
| `prompt`, `width`, `height`, `steps`, `guidance_scale`, `clip_skip`, `scheduler` | Effective request after tier routing |
| `seed` | Engine return value |
| `model_id` | `router.DEFAULT_MODEL_ID` today (`sdxl_base`) |
| `quality_tier` | Original client field (may be `null`) |

---

## 5. Configuration

| Variable | Where read | Default | Purpose |
|----------|------------|---------|---------|
| `SDXL_MODEL_PATH` | `main.py` | `<repo>/models/sdxl-base` | Weight directory |
| `SDXL_API_KEY` | `main.py` | `dev-local-key` | Expected `X-API-Key` |
| `APP_ENV` | `main.py` | `dev` | Include `details` on 500 if `dev` |
| `PORT` | Makefile | `8001` | Uvicorn port |
| `SDXL_API_URL` | `apps/web` route | `http://127.0.0.1:8001/generate` | Upstream `/generate` |
| `SDXL_JOBS_URL` | `apps/web` route | `http://127.0.0.1:8001/jobs` | Upstream `/jobs` base |
| `SDXL_API_KEY` | `apps/web` route | `dev-local-key` | Server-side proxy key |
| `SDXL_FETCH_TIMEOUT_MS` | `apps/web` route | `600000` | Proxy read timeout |
| `DEVICE` | `device.py` | auto (`cuda`/`mps`/`cpu`) | Inference device |
| `INPAINT_STRENGTH` | `main.py` / jobs | `0.85` | SDXL inpaint denoise strength |
| `ARTIFACTS_DIR` | `api_config.py` | `<repo>/generated` | Job JPEG root |
| `JOB_DB_PATH` | `api_config.py` | `<repo>/generated/jobs.db` | SQLite job snapshots |
| `GENERATION_TIMEOUT_SECONDS` | `main.py`, jobs | `90` | Wall-clock per GPU step |
| `GENERATION_CANCEL_GRACE_SECONDS` | `generation_service.py` | `120` | Drain GPU thread after timeout |

### Constants (`main.py`)

| Name | Value | Role |
|------|-------|------|
| `MAX_INFLIGHT_GENERATIONS` | `1` | Semaphore cap (Mac MVP) |
| `GENERATION_TIMEOUT_SECONDS` | `90` | Wall-clock cap on executor wait |
| `RATE_LIMIT_REQUESTS` | `5` | Per-key max in window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding window size |

### Quality tier table (`router.py`)

| `quality_tier` | `steps` | `guidance_scale` | `model_id` |
|----------------|---------|------------------|------------|
| `fast` | 12 | 5.0 | `sdxl_base` |
| `balanced` | 25 | 6.0 | `sdxl_base` |
| `quality` | 35 | 7.0 | `sdxl_base` |
| *(omit)* | client defaults | client defaults | `sdxl_base` |

---

## 6. Sequence — `POST /generate` success path

```mermaid
sequenceDiagram
    autonumber
    participant C as Client / Next proxy
    participant MW as Middleware
    participant G as generate()
    participant R as router.apply_quality_tier
    participant Reg as EngineRegistry
    participant E as SDXLEngine
    participant MPS as MPS / diffusers

    C->>G: POST /generate + JSON + X-API-Key
    G->>MW: request (already assigned request_id)
    G->>G: _require_api_key
    G->>G: _check_and_record_rate_limit
    G->>G: semaphore.acquire(non-blocking)
  G->>R: payload
    R-->>G: effective, model_id
    G->>Reg: get_engine(model_id)
    Reg-->>G: SDXLEngine instance
    G->>G: run_in_executor(engine.generate, effective)
    G->>E: generate(effective)
    E->>MPS: pipeline inference
    MPS-->>E: PIL image
    E-->>G: jpeg bytes, seed
    G-->>C: 200 GenerateResponse + X-Request-ID
```

---

## 7. Sequence — policy rejections (before GPU)

```mermaid
sequenceDiagram
    participant C as Client
    participant G as generate()

    alt Invalid API key
        C->>G: POST /generate
        G-->>C: 401 unauthorized
    else Rate limited
        C->>G: POST /generate
        G-->>C: 429 rate_limited + Retry-After
    else Capacity full
        C->>G: POST /generate
        G-->>C: 429 capacity_reached + Retry-After 5
    end
```

---

## 8. Concurrency and threading model

```mermaid
flowchart TB
    subgraph EventLoop["asyncio event loop"]
        HTTP[FastAPI handlers]
        Wait[asyncio.wait_for]
    end

    subgraph ThreadPool["default ThreadPoolExecutor"]
        Gen[SDXLEngine.generate]
    end

    subgraph Locks["threading.Lock"]
        ML[_metrics_lock]
        EL[SDXLEngine._lock]
        RL[EngineRegistry._lock]
    end

    HTTP --> Wait
    Wait --> Gen
    Gen --> EL
    HTTP --> ML
```

| Concern | Mechanism | Note |
|---------|-----------|------|
| Event loop blocking | `run_in_executor` | Inference never on main loop |
| Concurrent `/generate` | `Semaphore(1)` | Second request → `capacity_reached` |
| Metrics | `_metrics_lock` | Counter updates |
| Pipeline mutation | `SDXLEngine._lock` | Scheduler / clip_skip per request |
| Engine cache | `EngineRegistry._lock` | Lazy create under lock |
| Timeout | `wait_for(90s)` | Does **not** cancel GPU thread |

---

## 9. `SDXLEngine.generate` internal flow

```mermaid
flowchart TD
    A[generate req] --> B{scheduler in SCHEDULERS?}
    B -->|no| X[ValueError]
    B -->|yes| C[Resolve seed + Generator MPS]
    C --> D[Acquire engine._lock]
    D --> E[Set scheduler + set_timesteps]
    E --> F[Apply clip_skip on text_encoder]
    F --> G[pipeline prompt, size, steps, CFG]
    G --> H[Restore clip_skip layers]
    H --> I[JPEG BytesIO quality=90]
    I --> J[Return bytes, seed]
```

---

## 10. Next.js proxy (`apps/web`)

```mermaid
sequenceDiagram
    participant UI as StudioEditor + generation-dock
    participant RH as POST /api/generate
    participant RJ as GET /api/jobs/id/artifact
    participant API as FastAPI

    UI->>RH: fetch JSON prompt optional quality_tier
    RH->>API: POST /generate + X-API-Key from env
    API-->>RH: status body headers
    RH-->>UI: pass-through status + x-request-id
    Note over UI,RJ: After job converges
    UI->>RJ: GET artifact proxy
    RJ->>API: GET /jobs/id/artifact + X-API-Key
    API-->>RJ: JPEG bytes
    RJ-->>UI: image for canvas
```

| Concern | Design |
|---------|--------|
| API key | Server-only `SDXL_API_KEY`, never `NEXT_PUBLIC_` |
| Body | Transparent JSON forward |
| Errors | Upstream JSON + status preserved |
| Job images | Prefer `image_url` → `/api/jobs/{id}/artifact` over inline base64 |

---

## 11. State: implementation vs planned

```mermaid
flowchart LR
    subgraph Done["Implemented"]
        D1[schemas + tests]
        D2[main gates + metrics]
        D3[router quality_tier]
        D4[SDXLEngine MPS]
        D5[Next proxy + studio UI]
    end

    subgraph Done2["Also implemented"]
        D6[EngineRegistry lazy load]
        D7[POST /jobs + GET /jobs/id]
        D8[evaluator + correction loop]
        D9[POST /inpaint + job inpaint step]
        D10[DEVICE env + spheron deploy scripts]
        D11[job_store SQLite + artifact URLs]
    end

    subgraph Planned["LLD target"]
        P1[reference-conditioned gen IP-Adapter]
        P2[VLM rubric evaluator]
        P3[planner over tools]
    end

    Done --> Done2
    Done2 --> Planned
```

---

## 12. Correction jobs (implemented MVP)

In-process worker (`jobs.py`) with **write-through persistence** (`job_store.py`). Job metadata survives API restart; final images are JPEG files under `generated/jobs/<job_id>/`.

### HTTP

| Method | Path | Success | Notes |
|--------|------|---------|-------|
| POST | `/jobs` | 202 | Body: `JobCreateRequest` |
| GET | `/jobs/{job_id}` | 200 | `JobStatusResponse`; 404 `job_not_found` |
| GET | `/jobs/{job_id}/artifact` | 200 | Final JPEG; 404 `artifact_not_found` if not written yet |
| POST | `/inpaint` | 200 | Body: `InpaintRequest` (`image_base64`, `mask_base64`, `prompt`, …) |

### Schemas (additive)

- `VisualGoal` — `realism`, `preserve_product`, `product_similarity_min`, `use_inpaint_correction`, `task`
- `JobCreateRequest` — adds `reference_image_base64`, optional `mask_base64`
- `JobCreateResponse`, `JobStatusResponse` (`image_url` preferred over inline base64), `JobIterationRecord` (`correction`: `generate` | `inpaint` | `tier_bump`), `EvalResult`
- `InpaintRequest` — standalone inpaint endpoint

### Modules

| Module | Role |
|--------|------|
| `job_store.py` | SQLite upsert, `save_artifact`, `recover_interrupted_jobs` on startup |
| `evaluator.py` | Rules + optional CLIP when `reference_image_base64` set |
| `clip_evaluator.py` | Lazy CLIP (`CLIP_MODEL_ID`, `CLIP_DEVICE`, `PRODUCT_SIMILARITY_MIN`) |
| `correction.py` | `apply_corrections`, `resolve_correction` (tier vs inpaint) |
| `sdxl_adapter.py` | `effective_request`, `effective_inpaint_request`, `build_metadata` |
| `generation_service.py` | `generate_image_bytes`, `inpaint_image_bytes` (single GPU worker) |
| `image_utils.py` | Decode images/masks; `default_center_mask` for jobs |
| `device.py` | `resolve_torch_device`, `get_runtime_device` |
| `capabilities.py` | `text_to_image`, `quality_tier_routing`, `inpainting` |
| `jobs.py` | Memory cache + schedule, `generate → evaluate → correct` loop |

### Sequence

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant J as jobs.py
    participant S as job_store
    participant W as GPU worker
    participant Reg as EngineRegistry

    C->>API: POST /jobs
    API->>J: create_job
    J->>S: save_job queued
    API-->>C: 202 job_id
    J->>W: asyncio task _run_job
    W->>Reg: get_engine per step
    W->>W: generate / inpaint / evaluate
    J->>S: save_job each iteration
    J->>S: save_artifact output.jpg
    C->>API: GET /jobs/id
    API->>J: get_job
    J->>S: load_job on cache miss
    API-->>C: status, image_url, iterations
    C->>API: GET /jobs/id/artifact
    API-->>C: JPEG bytes
```

---

## 13. Testing map

| Test module | Layer | GPU |
|-------------|-------|-----|
| `tests/test_router.py` | `apply_quality_tier` | No |
| `tests/test_integration_api.py` | ASGI HTTP contract | Mocked `SDXLEngine` |

Integration tests patch `SDXLEngine.load_model` / `generate` at import time. When `main.py` uses `registry`, tests should mock `registry.get_engine` (see Phase 1 wiring). Includes `test_job_persisted_after_memory_cache_clear` (SQLite + artifact survive simulated restart).

---

## 14. File layout (inference-api)

```text
services/inference-api/
├── main.py               # HTTP: /generate, /jobs, /inpaint, metrics
├── schemas.py            # Pydantic contracts (+ VisualGoal, InpaintRequest)
├── router.py             # quality_tier → steps/CFG/model_id
├── registry.py           # Engine lifecycle (lazy cache)
├── sdxl_adapter.py       # Policy → effective request
├── generation_service.py # generate + inpaint on GPU executor
├── evaluator.py          # Goal vs output (rules + CLIP)
├── clip_evaluator.py     # CLIP similarity (lazy load)
├── correction.py         # resolve_correction (tier / inpaint)
├── image_utils.py        # Masks, decode helpers
├── device.py             # DEVICE env
├── capabilities.py       # Capability manifest
├── jobs.py               # Correction job worker + memory cache
├── job_store.py          # SQLite persistence + JPEG artifacts
├── api_config.py         # Env vars (ARTIFACTS_DIR, JOB_DB_PATH, …)
├── engine.py             # SDXL txt2img + inpaint pipelines
├── client.py             # Sample HTTP client
└── tests/
    ├── test_integration_api.py
    ├── test_generation_service.py
    ├── test_router.py
    ├── test_evaluator.py
    ├── test_correction.py
    └── test_clip_evaluator.py
```

---

## 15. Benchmark harness

| Path | Role |
|------|------|
| `benchmarks/product_similarity/manifest.json` | Case list: `id`, `prompt`, `reference_path`, optional overrides |
| `benchmarks/product_similarity/fixtures/` | Reference JPEGs (e.g. ring, watch) |
| `scripts/spheron_*.sh`, `scripts/clean.sh` | VM deploy + artifact cleanup — see README |
| `scripts/run_product_benchmark.py` | HTTP client: baseline vs job, writes `results/latest.json` |
| `make benchmark-product` | Runs script (requires live API + fixtures) |

Integration test: `tests/test_benchmark_manifest.py` (schema only, no GPU).

---

## 16. Related documents

| Document | Contents |
|----------|----------|
| [README.md](./README.md) | Setup, curl, env, runbooks |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System context, target diagrams, tech debt, Spheron |
| [.cursor/rules/](./.cursor/rules/) | Merge checklist, monorepo boundaries |
