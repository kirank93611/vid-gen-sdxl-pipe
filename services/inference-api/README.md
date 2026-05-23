# Inference API (FastAPI + SDXL)

GPU-backed REST service: synchronous `/generate` and `/inpaint`, async `/jobs` with evaluation and correction.

## Run locally

From repository root:

```bash
source .venv/bin/activate
export GENERATION_TIMEOUT_SECONDS=300   # recommended for balanced/quality tiers
make run
# → http://127.0.0.1:8001
```

Integration tests (mocked GPU):

```bash
make test-integration
```

## Module layout

See [docs/CODEBASE.md](../../docs/CODEBASE.md) for the full dependency graph.

| Module | Responsibility |
|--------|----------------|
| `main.py` | Routes, middleware, metrics, backpressure semaphore |
| `api_config.py` | Environment configuration |
| `api_auth.py` | `X-API-Key` validation |
| `rate_limit.py` | Per-key sliding window |
| `generation_service.py` | Thread-pool inference + timeout + cooperative cancel |
| `jobs.py` | In-process job queue and correction loop |
| `engine.py` | Diffusers SDXL text2img + inpaint |
| `schemas.py` | **Contract** (Pydantic) |
| `evaluator.py` | Goal checks + CLIP similarity |
| `correction.py` | Tier bump / inpaint correction |

## HTTP endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/generate` | Key | Base64 JPEG in response |
| POST | `/inpaint` | Key | `image_base64`, `mask_base64`, `strength` |
| POST | `/jobs` | Key | 202 + `job_id`; poll `GET /jobs/{id}` |
| GET | `/jobs/{job_id}` | Key | Status, iterations, final image |
| GET | `/health` | — | `engine` = mps/cuda/cpu |
| GET | `/capabilities` | — | Model skill manifest |
| GET | `/metrics` | Key | Counters for ops dashboards |
| GET | `/openapi.json` | — | Machine-readable contract |

Default API key (dev): `dev-local-key` header `X-API-Key`.

## Environment variables

Defined in `api_config.py`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SDXL_API_KEY` | `dev-local-key` | Expected `X-API-Key` |
| `SDXL_MODEL_PATH` | `<repo>/models/sdxl-base` | Local diffusers folder |
| `GENERATION_TIMEOUT_SECONDS` | `90` | Per-request asyncio timeout |
| `MAX_INFLIGHT_GENERATIONS` | `1` | GPU concurrency semaphore |
| `INPAINT_STRENGTH` | `0.85` | Job correction inpaint default |
| `RATE_LIMIT_REQUESTS` | `5` | Per-key max in window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding window length |
| `APP_ENV` | `dev` | `dev` adds error `details` on 500 |
| `DEVICE` | auto | `cuda`, `mps`, or `cpu` (see `device.py`) |

## Jobs and reference images

- `reference_image_base64` on job create is used for **CLIP** similarity when `preserve_product` or `product_similarity_min` is set.
- It does **not** paste the reference into the output — expect semantic similarity, not pixel match.
- `goal.use_inpaint_correction` triggers inpaint on `product_similarity_low` (requires API schema + worker from current branch).

## Changing the contract

1. Edit `schemas.py`
2. Update route behavior in `main.py` / `jobs.py` if needed
3. Run `make test-integration`
4. Update [README.md](../../README.md) and Next.js `/api/*` routes if fields are exposed to the UI

## Tests

`tests/test_integration_api.py` — ASGI client with mocked `SDXLEngine`.  
`rate_limit.reset_for_tests()` clears limiter state between cases.

See [tests/README.md](tests/README.md).
