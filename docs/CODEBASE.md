# Codebase map (architect / staff engineer onboarding)

Navigation index for the monorepo. Ops: [README.md](../README.md), [RUNBOOK-SPHERON.md](./RUNBOOK-SPHERON.md). Design: [ARCHITECTURE.md](../ARCHITECTURE.md). **Plug-and-play models:** [MODELS.md](./MODELS.md).

## Monorepo boundaries

| Area | Path | Deploy unit | Owns |
|------|------|-------------|------|
| Web | `apps/web/` | Next.js | Studio UI, BFF proxies, SEO |
| Inference | `services/inference-api/` | FastAPI + GPU | Generate, inpaint, jobs, chat, catalog |
| Scripts | `scripts/` | Shell | Spheron sync, deploy, benchmarks |
| Benchmarks | `benchmarks/` | Offline Python | Product-similarity fixtures |

**Rules:** No Python inference in `apps/*`. No React in `services/inference-api/`. HTTP contract owned by `schemas.py` + integration tests.

## Inference API — module graph

```text
main.py                    HTTP routes, middleware, metrics, semaphore
├── api_config.py          Env vars
├── api_auth.py / rate_limit.py / api_logging.py
├── generation_service.py  Executor, timeout, cancel
├── generation_profiles.py Presets (source of truth for profiles)
├── router.py              Re-exports apply_generation_policy
├── model_registry.py      Unified GET /models list
├── model_catalog.py       SDXL + GGUF registrations
├── checkpoint_utils.py    SD 1.5 ckpt scan (plug-and-play)
├── lora_utils.py          LoRA scan (plug-and-play)
├── registry.py            Lazy engines, VRAM eviction
├── engine.py / sd15_engine.py / gguf_engine.py
├── jobs.py / job_store.py / evaluator.py / correction.py
└── schemas.py             Pydantic contract
```

### Request paths

| Endpoint | Auth | GPU | Notes |
|----------|------|-----|-------|
| `POST /generate` | Yes | Semaphore | SDXL or SD1.5 checkpoint |
| `POST /inpaint` | Yes | Semaphore | SDXL |
| `POST /jobs` | Yes | Worker | CLIP + correction loop |
| `GET /models` | No | No | Catalog + checkpoints |
| `GET /loras` | No | No | Filesystem scan |
| `GET /generation-profiles` | No | No | Preset blocks |
| `POST /chat` | Yes | Load GGUF | Chat models |
| `GET /health`, `/metrics` | Partial | No | Observability |

## Web app — structure

```text
apps/web/src/
├── app/
│   ├── page.tsx, explore/, chat/
│   └── api/              BFF → inference (generate, jobs, models, loras, profiles, chat)
├── components/
│   ├── studio/           Editor (dock/, canvas, nav, chat-interface)
│   └── ui/               shadcn
└── lib/
    ├── api/              inference-config, errors, catalog, generate
    ├── studio/           defaults, model-utils, profile-utils, types
    ├── studio-api.ts     Barrel re-exports (legacy imports)
    └── studio-constants.ts
```

**Contract rule:** Generation profiles and model lists come from the **API**, not hardcoded TS mirrors.

## Tests

| Layer | Command |
|-------|---------|
| Integration (required on API changes) | `make test-integration` |
| GPU benchmark (manual) | `make spheron-benchmark` |

## ADRs

| ID | Topic |
|----|--------|
| [0001](adr/0001-monorepo-layout.md) | Monorepo layout |

## Read first by role

1. **Run:** [README.md](../README.md) + [RUNBOOK-SPHERON.md](./RUNBOOK-SPHERON.md)
2. **Add model/LoRA:** [MODELS.md](./MODELS.md)
3. **Change API:** `schemas.py` → tests → `apps/web/src/app/api/*`
4. **Change studio:** `components/studio/`, `lib/api/`, `lib/studio/`
5. **GPU behavior:** `registry.py`, `generation_service.py`, [ARCHITECTURE.md](../ARCHITECTURE.md)
