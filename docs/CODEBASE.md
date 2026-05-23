# Codebase map (architect / staff engineer onboarding)

This document is the **navigation index** for the monorepo. Operational runbooks live in [README.md](../README.md); system design in [ARCHITECTURE.md](../ARCHITECTURE.md); module-level API detail in [LLD.md](../LLD.md).

## Monorepo boundaries

| Area | Path | Deploy unit | Owns |
|------|------|-------------|------|
| Web | `apps/web/` | Next.js (Node) | SEO, studio UI, Route Handler proxies to inference |
| Inference | `services/inference-api/` | FastAPI (Python + GPU) | SDXL generate/inpaint, jobs loop, metrics |
| Scripts | `scripts/` | Shell (ops) | Spheron VM sync, deploy, benchmark helpers |
| Benchmarks | `benchmarks/` | Offline Python | Product-similarity fixtures and scoring |

**Rule:** No Python inference inside `apps/*`. No React inside `services/inference-api/`.

## Inference API — module graph

```text
main.py              HTTP routes, middleware, metrics, semaphore backpressure
├── api_config.py    Env vars (single place)
├── api_auth.py      X-API-Key gate
├── api_logging.py   request_id on all logs
├── rate_limit.py    Per-key sliding window (in-process)
├── generation_service.py   asyncio executor + timeout + cancel
├── jobs.py            async job worker: generate → evaluate → correct
├── router.py          quality_tier → steps/guidance/dims
├── registry.py        lazy EngineRegistry per model_id
├── engine.py          diffusers SDXL + inpaint pipelines
├── evaluator.py       rules + optional CLIP vs reference
├── correction.py      tier bump / inpaint correction policy
├── schemas.py         Pydantic contract (source of truth)
├── capabilities.py    model_id → supported skills manifest
└── sdxl_adapter.py    model-agnostic knobs → SDXL params
```

### Request paths

| Endpoint | Auth | Rate limit | GPU gate | Core logic |
|----------|------|------------|----------|------------|
| `POST /generate` | Yes | Yes | Semaphore | `generation_service` → `engine.generate` |
| `POST /inpaint` | Yes | Yes | Semaphore | `generation_service` → `engine.inpaint` |
| `POST /jobs` | Yes | Yes | Worker uses same semaphore | `jobs.run_job_loop` |
| `GET /jobs/{id}` | Yes | No | No | In-memory job store |
| `GET /health` | No | No | No | `device.get_runtime_device()` |
| `GET /capabilities` | No | No | No | `capabilities.list_capabilities()` |
| `GET /metrics` | Yes | No | No | Counters in `main._metrics` |

### Product jobs and reference images

- Reference image is **CLIP image–image similarity only** — not pixel compositing.
- When `product_similarity_low` and `use_inpaint_correction`, jobs run inpaint with a center mask (`image_utils`).
- See [ARCHITECTURE.md](../ARCHITECTURE.md) for the correction state machine.

### Configuration

All inference env vars are documented in `services/inference-api/api_config.py` and `services/inference-api/README.md`.

## Web app — structure

```text
apps/web/src/
├── app/
│   ├── page.tsx              Studio editor (/)
│   ├── explore/page.tsx      Marketing hero
│   └── api/                  BFF proxies (generate, jobs)
├── components/studio/        Bottom-dock editor UI
├── components/ui/            shadcn primitives
└── lib/
    ├── studio-api.ts         fetch helpers + error shaping
    └── studio-constants.ts   tiers, aspect ratios, copy
```

Proxies forward `X-API-Key` and `X-Request-ID` to the inference API (`SDXL_API_URL`, `SDXL_JOBS_URL` in `.env.example`).

## Tests

| Layer | Command | Location |
|-------|---------|----------|
| Integration (required on API changes) | `make test-integration` | `services/inference-api/tests/` |
| GPU benchmark (manual) | `make spheron-benchmark` | `benchmarks/product_similarity/` |

## ADRs

| ID | Topic |
|----|--------|
| [0001](adr/0001-monorepo-layout.md) | Monorepo layout and separation of concerns |

## What to read first (by role)

1. **Run something:** [README.md](../README.md)
2. **Change API contract:** `schemas.py` → integration tests → `apps/web` proxies
3. **Change GPU behavior:** `engine.py`, `generation_service.py`, `ARCHITECTURE.md`
4. **Change studio UX:** `apps/web/README.md`, `components/studio/`
5. **Deploy VM:** `scripts/README.md`, Makefile `deploy-*` targets
