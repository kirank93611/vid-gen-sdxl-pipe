# SDXL Image API

Monorepo for **local SDXL image generation** on Apple Silicon (MPS) and a **Next.js** UI. The FastAPI service owns the HTTP contract; the web app proxies requests so API keys stay on the server.

**Deeper design (current + target pipelines, Spheron):** see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Repository layout

| Path | Purpose |
|------|---------|
| `services/inference-api/` | FastAPI: `main.py`, `engine.py`, `router.py`, `schemas.py`, `tests/` |
| `apps/web/` | Next.js App Router UI + `POST /api/generate` proxy |
| `packages/` | Optional shared TS types / constants (see `packages/README.md`) |
| `.cursor/rules/` | Cursor project rules (monorepo, Python, quality bar) |
| `models/` | Local SDXL weights (**gitignored**) at `models/sdxl-base` |

### Source tree (tracked in git)

```text
image-sd/
├── .cursor/rules/
├── apps/web/
│   ├── src/app/              # pages + api/generate route
│   ├── src/components/       # generate form
│   └── .env.example
├── packages/README.md
├── services/inference-api/
│   ├── client.py
│   ├── engine.py
│   ├── main.py
│   ├── router.py
│   ├── schemas.py
│   └── tests/
│       ├── test_integration_api.py
│       └── test_router.py
├── ARCHITECTURE.md
├── Makefile
├── requirements.txt          # Python lockfile (see Install)
└── README.md
```

**Not in git:** `.venv/`, `models/`, `generated/`, `apps/web/node_modules/`, `apps/web/.next/`, `.env` / `.env.local`, local `*.jpg` outputs.

## Quick start (API + web)

### 1. Python inference API

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install diffusers uvicorn accelerate   # if not already present in your env
```

Download weights into `./models/sdxl-base` (see [Download model](#download-model-locally)).

```bash
make test-integration
make run
```

API: `http://127.0.0.1:8001` — docs at `/docs`, health at `/health`.

### 2. Next.js web app

In a second terminal:

```bash
cd apps/web
cp .env.example .env.local   # adjust SDXL_API_URL / SDXL_API_KEY if needed
npm install
npm run dev
```

Open `http://localhost:3000`, enter a prompt, and generate. The UI calls `/api/generate`, which forwards to the inference API with `X-API-Key` on the server.

## System flow (today)

```mermaid
flowchart LR
    Browser --> Next["apps/web"]
    Next --> Proxy["Route Handler /api/generate"]
    Proxy --> API["FastAPI /generate"]
    API --> Tier["router.apply_quality_tier"]
    Tier --> Engine["SDXLEngine"]
    Engine --> MPS["MPS / models/sdxl-base"]
    MPS --> API
    API --> Proxy
    Proxy --> Browser
```

## Requirements

- macOS with Apple Silicon (MVP target)
- Python 3.12+ in `.venv` at repo root
- Node.js 20+ for `apps/web`
- Local model files under `./models/sdxl-base`

## Install dependencies (Python)

With `uv` and an activated `.venv`:

```bash
uv pip install -r requirements.txt
```

The root `requirements.txt` is a broad environment lockfile. Inference needs **diffusers** and **uvicorn**; install them if imports fail:

```bash
uv pip install diffusers uvicorn accelerate
```

Minimal inference-only set (fresh venv):

```bash
uv pip install fastapi uvicorn torch diffusers transformers accelerate pydantic pillow huggingface_hub httpx requests
```

## Download model locally

Weights are **not** in git. Each machine needs **SDXL base 1.0** at `./models/sdxl-base`:

```bash
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='stabilityai/stable-diffusion-xl-base-1.0', local_dir='./models/sdxl-base', allow_patterns=['model_index.json','scheduler/*','tokenizer/*','tokenizer_2/*','text_encoder/config.json','text_encoder/model.fp16.safetensors','text_encoder_2/config.json','text_encoder_2/model.fp16.safetensors','vae/config.json','vae/diffusion_pytorch_model.fp16.safetensors','unet/config.json','unet/diffusion_pytorch_model.fp16.safetensors'])"
```

**Note:** Defaults and `quality_tier` profiles are tuned for **base SDXL** (more steps, higher CFG). `/health` may still report `"optimization": "lightning"` — that field is legacy; actual weights are base 1.0.

Override model path: `SDXL_MODEL_PATH=/path/to/weights make run`.

## Start the inference server

```bash
make run
```

Or manually:

```bash
cd services/inference-api && source ../../.venv/bin/activate && uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

Default port **8001** (`PORT=8000 make run` to override).

## Health check

```bash
curl http://127.0.0.1:8001/health
```

Example:

```json
{"status":"healthy","engine":"mps","backend":"diffusers","optimization":"lightning"}
```

## Metrics

```bash
curl http://127.0.0.1:8001/metrics -H "X-API-Key: dev-local-key"
```

## API key authentication

- `/generate` and `/metrics` require header `X-API-Key`.
- Default dev key: `dev-local-key` (override with `SDXL_API_KEY` before `make run`).
- Next.js reads the same values from `apps/web/.env.local` (`SDXL_API_KEY`, `SDXL_API_URL`) — never expose the key to the browser.

## Generate an image

### With `quality_tier` (recommended for base SDXL)

The server sets `steps` and `guidance_scale` from `services/inference-api/router.py`:

| Tier | Steps | Guidance |
|------|-------|----------|
| `fast` | 12 | 5.0 |
| `balanced` | 25 | 6.0 |
| `quality` | 35 | 7.0 |

```bash
curl -sS -X POST "http://127.0.0.1:8001/generate" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-key" \
  -d '{
    "prompt": "a cinematic portrait of a tiger in rain, ultra detailed",
    "quality_tier": "balanced",
    "width": 1024,
    "height": 1024,
    "seed": 1234
  }'
```

### Explicit steps (no tier override)

```bash
curl -sS -X POST "http://127.0.0.1:8001/generate" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-key" \
  -d '{
    "prompt": "a red apple on a wooden table",
    "steps": 25,
    "guidance_scale": 6.0,
    "scheduler": "dpm++2m_karras"
  }'
```

Success responses include `image_base64` and `metadata` (`steps`, `guidance_scale`, `model_id`, `quality_tier`, `seed`, …). Responses include header `X-Request-ID`.

`GENERATION_TIMEOUT_SECONDS` defaults to **90** in `main.py`; quality tiers can take most of that on a Mac — watch logs for `generation_timeout` (504).

## Request fields

| Field | Description |
|-------|-------------|
| `prompt` | Required text prompt |
| `negative_prompt` | Optional; default anti-artifact string |
| `seed` | Optional; random if omitted |
| `width` / `height` | 512–1536, multiple of 8; default 1024 |
| `steps` | 1–40; default 4 (use tier or raise for base SDXL) |
| `guidance_scale` | 0.0–12.0; default 1.0 |
| `quality_tier` | Optional: `fast`, `balanced`, `quality` — overrides steps/CFG |
| `clip_skip` | 1–4; default 2 |
| `scheduler` | `dpm++2m_karras` or `euler` |

Unknown fields (e.g. `lora_path`) return **422**.

## Backpressure and rate limits

- **Capacity:** `MAX_INFLIGHT_GENERATIONS=1` → second concurrent `/generate` gets **429** `capacity_reached` with `Retry-After: 5`.
- **Rate limit:** per API key, sliding window → **429** `rate_limited`.

## Save the returned image

```bash
cd services/inference-api && source ../../.venv/bin/activate && python client.py
```

Or decode JSON with Python/`base64` (outputs are gitignored if written beside the service).

## Integration tests

```bash
make test-integration
```

Runs `test_integration_api.py` and `test_router.py` with **mocked** GPU work.

## Web app (`apps/web`)

See [apps/web/README.md](./apps/web/README.md). Summary:

- `npm run dev` → `http://localhost:3000`
- Server route `src/app/api/generate/route.ts` proxies to `SDXL_API_URL`
- Client component `src/components/generate-form.tsx`

## Collaboration notes

- Contract source of truth: `schemas.py` + integration tests.
- Inference only in `engine.py` (and future engine modules).
- Contract changes → update tests, this README, and `ARCHITECTURE.md` when behavior meaning changes.

## Common issues

**Missing model files** — ensure `models/sdxl-base/model_index.json` and fp16 safetensors exist (see download command).

**504 timeout** — lower tier, reduce steps, or raise `GENERATION_TIMEOUT_SECONDS` for local dev.

**Blurry images with default `steps: 4`** — you are on **base** weights; use `quality_tier: "balanced"` or higher steps/CFG.

**Next cannot reach API** — inference must be on `127.0.0.1:8001`; check `apps/web/.env.local`.

**`GET /` returns 404** — use `/health`, `/docs`, or `POST /generate`.
