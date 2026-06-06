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
# Windows (no make):
cd services/inference-api
python -m unittest discover -s tests -p "test_*.py" -v
```

## Spheron GPU VM

Production inference runs on CUDA (`DEVICE=cuda`). Setup and tunnel from your laptop:

**[docs/RUNBOOK-SPHERON.md](../../docs/RUNBOOK-SPHERON.md)**

Quick start on VM after `spheron_setup.sh`:

```bash
export DEVICE=cuda GENERATION_TIMEOUT_SECONDS=300 SDXL_MODEL_PATH=~/image-sd/models/sdxl-base
bash scripts/spheron_restart_api.sh
curl -s http://127.0.0.1:8001/health   # expect "engine":"cuda"
```

Windows one-shot from repo root: `powershell -ExecutionPolicy Bypass -File scripts\spheron_windows_setup.ps1`

## Module layout

See [docs/CODEBASE.md](../../docs/CODEBASE.md) for the full dependency graph.

| Module | Responsibility |
|--------|----------------|
| `main.py` | Routes, middleware, metrics, backpressure semaphore |
| `api_config.py` | Environment configuration |
| `api_auth.py` | `X-API-Key` validation |
| `rate_limit.py` | Per-key sliding window |
| `generation_service.py` | Thread-pool inference + timeout + cooperative cancel |
| `jobs.py` | Job queue, correction loop, write-through to `job_store` |
| `job_store.py` | SQLite job snapshots + JPEG artifacts on disk |
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
| GET | `/jobs/{job_id}` | Key | Status, iterations, `image_url` / base64 |
| GET | `/jobs/{job_id}/artifact` | Key | Final JPEG file (preferred over base64) |
| GET | `/health` | — | `engine` = mps/cuda/cpu |
| POST | `/chat` | Key | TieFighter 20B GGUF text (not images) |
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
| `TIEFIGHTER_GGUF_FILE` | `...-Q4_K_M.gguf` | Quant file name under `models/tiefighter-20b/` |
| `TIEFIGHTER_N_GPU_LAYERS` | `-1` | llama.cpp GPU layers (`-1` = all) |
| `CHAT_TIMEOUT_SECONDS` | `120` | `/chat` wall-clock timeout |
| `ARTIFACTS_DIR` | `<repo>/generated` | Job JPEG output root |
| `JOB_DB_PATH` | `<repo>/generated/jobs.db` | SQLite job persistence |
| `LORAS_DIR` | `<repo>/models/loras` | SDXL LoRA `.safetensors` files |

### TieFighter 20B (text GGUF)

This is a **text LLM**, not an image model. Use **`POST /chat`** for prompt expansion, copy, agents — not **`POST /generate`**.

Download on GPU VM (~12 GB for Q4_K_M):

```bash
make spheron-download-llm
# or: DOWNLOAD_TIEFIGHTER=1 bash scripts/spheron_setup.sh
```

HF repo may require accepting the model gate on huggingface.co first.

Only **one** of SDXL or TieFighter stays loaded in VRAM at a time (automatic unload on switch).

## Jobs and reference images

- `reference_image_base64` on job create is used for **CLIP** similarity when `preserve_product` or `product_similarity_min` is set.
- It does **not** paste the reference into the output — expect semantic similarity, not pixel match.
- `goal.use_inpaint_correction` triggers inpaint on `product_similarity_low` (requires API schema + worker from current branch).

### Job persistence

- SQLite: `JOB_DB_PATH` (default `generated/jobs.db`)
- Final JPEG: `ARTIFACTS_DIR/jobs/<job_id>/output.jpg`
- Poll `GET /jobs/{id}` for `image_url`; download via `GET /jobs/{id}/artifact`
- Survives API restart; interrupted `queued`/`running` jobs → `error_code=server_restarted`

## Changing the contract

1. Edit `schemas.py`
2. Update route behavior in `main.py` / `jobs.py` if needed
3. Run `make test-integration`
4. Update [README.md](../../README.md) and Next.js `/api/*` routes if fields are exposed to the UI

## Tests

`tests/test_integration_api.py` — ASGI client with mocked `SDXLEngine`.  
`rate_limit.reset_for_tests()` clears limiter state between cases.

See [tests/README.md](tests/README.md).
