# Visual Studio — SDXL product composite

Monorepo: **FastAPI inference** (`services/inference-api`) + **Next.js studio** (`apps/web`).

| Doc | Use when |
|-----|----------|
| **This README** | Install, run locally, deploy to GPU VM, test |
| [docs/MODELS.md](./docs/MODELS.md) | **Plug-and-play** — LoRAs, checkpoints, catalog, profiles |
| [docs/LORAS.md](./docs/LORAS.md) | Download Civitai LoRAs → VM, `lora_name` in API/UI |
| [docs/CHECKPOINTS.md](./docs/CHECKPOINTS.md) | SD 1.5 checkpoints (URPM, etc.) |
| [docs/RUNBOOK-SPHERON.md](./docs/RUNBOOK-SPHERON.md) | **Spheron SSH, sync, weights, tunnel** (Windows + Mac) |
| [docs/CODEBASE.md](./docs/CODEBASE.md) | **Onboarding map** — modules, paths, what to read first |
| [docs/CONTRIBUTING.md](./docs/CONTRIBUTING.md) | PR workflow, contract checklist, code conventions |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System design, jobs loop, limitations |
| [LLD.md](./LLD.md) | Modules and API detail |
| [services/inference-api/README.md](./services/inference-api/README.md) | API env vars and endpoint reference |
| [apps/web/README.md](./apps/web/README.md) | Next.js routes and studio UI layout |
| [scripts/README.md](./scripts/README.md) | Spheron deploy scripts and Makefile targets |

---

## What you need on disk (not in git)

| Path | Purpose |
|------|---------|
| `.venv/` | Python env (repo root) |
| `models/sdxl-base/` | SDXL 1.0 weights (~6.5 GB) |
| `apps/web/node_modules/` | After `npm install` |
| `apps/web/.env.local` | Copy from `.env.example` |
| `.env.spheron` | Spheron VM IP + SSH private key path (copy from `.env.spheron.example`) |

**Never commit:** `.venv`, `models/`, `node_modules/`, `.next/`, `generated/`, `.env.spheron`, `spheron_sync.tgz`, `benchmarks/.../results/`, `.env.local`.

Clean artifacts: `make clean`

---

## Repository layout

```text
image-sd/
├── apps/web/                 # Next.js studio (shadcn + bottom dock UI)
├── services/inference-api/   # FastAPI: /generate, /jobs, /inpaint
├── scripts/                  # Deploy + benchmark helpers
├── benchmarks/product_similarity/
├── Makefile
├── requirements.txt
└── README.md
```

---

## A. Local Mac (develop & test)

### 1. One-time setup

```bash
cd image-sd
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install diffusers uvicorn accelerate
```

Download model (once):

```bash
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='stabilityai/stable-diffusion-xl-base-1.0', local_dir='./models/sdxl-base', allow_patterns=['model_index.json','scheduler/*','tokenizer/*','tokenizer_2/*','text_encoder/config.json','text_encoder/model.fp16.safetensors','text_encoder_2/config.json','text_encoder_2/model.fp16.safetensors','vae/config.json','vae/diffusion_pytorch_model.fp16.safetensors','unet/config.json','unet/diffusion_pytorch_model.fp16.safetensors'])"
```

### 2. Run inference API

```bash
source .venv/bin/activate
export GENERATION_TIMEOUT_SECONDS=300   # recommended for balanced/quality tiers
make test-integration
make run
```

- API: http://127.0.0.1:8001  
- Health: `curl http://127.0.0.1:8001/health`  
- Key: `dev-local-key` (header `X-API-Key`)

### 3. Run web UI

**Use port 3001** if you have an SSH tunnel on 3000 to a VM.

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev:local
```

Open **http://localhost:3001** — lime header, bottom **Generate** dock, **Product job** tab.

| Mode | What it does |
|------|----------------|
| Quick generate | `POST /api/generate` → single SDXL image |
| Product job | `POST /api/jobs` → generate + CLIP eval + tier/inpaint correction |

**Important:** Reference JPEG is used for **CLIP scoring**, not pixel-perfect product copy. See [ARCHITECTURE.md](./ARCHITECTURE.md).

---

## A2. Local Windows (develop & test)

### 1. Python (one-time)

Install **Python 3.12+** from [python.org](https://www.python.org/downloads/) with **Add to PATH** checked. Disable Windows Store python aliases (Settings → App execution aliases).

```powershell
cd E:\path\to\sdxl
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install diffusers uvicorn accelerate
```

If `Activate.ps1` is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Download SDXL weights (once) — same Python one-liner as Mac section A, or run setup on Spheron instead.

### 2. Run inference API

```powershell
$env:GENERATION_TIMEOUT_SECONDS = "300"
cd services\inference-api
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

### 3. Run web UI

```powershell
cd apps\web
copy .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000 — CPU inference is slow; use Spheron for GPU (section B2).

---

## B. Spheron GPU VM (production test)

Full runbook: **[docs/RUNBOOK-SPHERON.md](./docs/RUNBOOK-SPHERON.md)** (SSH keys, sync, weights, tunnel, troubleshooting).

**Spot VMs get a new IP every deploy.** Update `.env.spheron` (or `make spheron-set-ip` on Mac).

### B1. Mac / Linux

Run **`make spheron-*` from your laptop** — not inside the VM SSH session.

```bash
cp .env.spheron.example .env.spheron
make spheron-set-ip IP=<VM_IP>          # writes .env.spheron (gitignored)
# optional: SPM_USER=ubuntu make spheron-set-ip IP=...
```

| Command | When | Time |
|---------|------|------|
| `make spheron-set-ip IP=…` | New IP from Spheron dashboard | instant |
| `make spheron-sync` | Code only | ~seconds |
| `make spheron-setup` | **First** VM (torch + SDXL download) | ~15–25 min |
| `make spheron-up` | **Same disk**, new IP (skip model/torch if present) | ~5–15 min |
| `make spheron-deploy` | Code + restart API + rebuild web | ~5–15 min |
| `make spheron-tunnel` | Browser → studio + API | — |

### B2. Windows (PowerShell)

**1. SSH key (one-time)** — generate on PC, add `.pub` to Spheron:

```powershell
ssh-keygen -t ed25519 -f C:\Users\YOU\.ssh\id_ed25519
type C:\Users\YOU\.ssh\id_ed25519.pub
```

**2. Config** — copy `.env.spheron.example` → `.env.spheron`, set `SPHERON_IP` and `SPHERON_SSH_KEY`.

**3. First-time setup** (sync + PyTorch + SDXL download + start API, ~15–25 min):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\spheron_windows_setup.ps1
```

**4. Tunnel** (leave open; keeps `apps/web/.env.local` on `127.0.0.1`):

```powershell
ssh -i C:\Users\YOU\.ssh\id_ed25519 `
  -L 8001:127.0.0.1:8001 `
  -L 3000:127.0.0.1:3000 `
  ubuntu@<VM_IP>
```

**5. Browser:** http://127.0.0.1:3000 (web on VM) **or** `npm run dev` locally with tunnel on `:8001` only.

**New IP:** edit `SPHERON_IP` in `.env.spheron`, run `ssh-keygen -R <IP>`, reconnect. Fresh disk → re-run setup script.

### First time on a fresh VM (empty disk)

```bash
make spheron-set-ip IP=<VM_IP>
make spheron-setup    # sync + spheron_setup.sh on VM
make spheron-tunnel   # http://127.0.0.1:3000
```

### Every new spot instance (IP changed, models still on disk)

```bash
make spheron-set-ip IP=<NEW_IP>
make spheron-up       # sync + quick bootstrap (API + web)
make spheron-tunnel
```

If the disk was wiped, use `make spheron-setup` again instead of `spheron-up`.

### Code-only update (same VM, same IP)

```bash
make spheron-deploy
```

On the VM after sync from Mac:

```bash
cd /root/image-sd   # or ~/image-sd for ubuntu user
make deploy-api
make deploy-web
```

### Use the UI from your Mac

```bash
make spheron-tunnel
```

**Browser:** http://127.0.0.1:3000 — hard refresh `Cmd+Shift+R`

**Terminal 2** — optional local UI against VM API:

```bash
# Only if you are NOT tunneling 3000, or use 3001 locally
cd apps/web && npm run dev:local
```

### Verify deployment

On VM:

```bash
curl -s http://127.0.0.1:8001/health
curl -s http://127.0.0.1:3000/ | grep -oE 'Start creating|Generate frame' | head -1
# Want: Start creating  (new UI). Not: Generate frame  (old UI)
```

Logs:

```bash
tail -f /tmp/sdxl-api.log
tail -f /tmp/visual-studio-web.log
```

### GPU benchmark (optional)

```bash
# Mac
make spheron-benchmark
```

---

## Makefile reference

| Target | Where | Action |
|--------|-------|--------|
| `make clean` | Mac/VM | Remove `.next`, benchmark results, caches |
| `make run` | Mac | Dev API with reload |
| `make test-integration` | Mac/VM | Mocked API tests |
| `make benchmark-product` | Mac | CLIP benchmark (API must be up) |
| `make spheron-sync` | **Mac** | Rsync code to VM |
| `make spheron-deploy` | **Mac** | Sync + restart API + rebuild web on VM |
| `make deploy-api` | **VM** | Restart inference API |
| `make deploy-web` | **VM** | Clean build + `next start` on :3000 |

---

## Scripts

| Script | Run on | Purpose |
|--------|--------|---------|
| `scripts/clean.sh` | Mac/VM | Delete build artifacts |
| `scripts/spheron_setup.sh` | VM | First-time CUDA + model download |
| `scripts/spheron_restart_api.sh` | VM | Restart API (waits for `/health`) |
| `scripts/spheron_deploy_web.sh` | VM | Kill :3000, `npm run build`, `next start` |
| `scripts/spheron_vm_bootstrap.sh` | VM | setup + API + smoke generate |
| `scripts/spheron_generate.py` | VM/Mac/Win | One `/generate` smoke test |
| `scripts/spheron_windows_setup.ps1` | **Windows** | SSH test, tarball sync, setup, start API |
| `scripts/run_product_benchmark.py` | Mac/VM | Product CLIP benchmark |
| `scripts/run_product_job.py` | Mac/VM | CLI product job with reference file |

---

## API quick reference

- `POST /generate` — single image (`quality_tier`: fast / balanced / quality)
- `POST /jobs` — correction loop (`goal.preserve_product`, `reference_image_base64`, optional `goal.use_inpaint_correction`)
- `POST /inpaint` — mask + init image
- `GET /jobs/{id}` — poll job status (`image_url` preferred)
- `GET /jobs/{id}/artifact` — download final JPEG from disk
- `GET /loras` — list `models/loras/*.safetensors` on the API host
- Optional: `lora_name`, `lora_weight` on `/generate` and `/jobs` — see [docs/LORAS.md](./docs/LORAS.md)
- Auth: `X-API-Key: dev-local-key`

Example product job:

```bash
curl -sS -X POST "http://127.0.0.1:8001/jobs" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-key" \
  -d '{
    "goal": {
      "preserve_product": true,
      "product_similarity_min": 0.85,
      "use_inpaint_correction": true
    },
    "prompt": "luxury ring on black velvet, studio lighting",
    "quality_tier": "fast",
    "max_iterations": 3,
    "reference_image_base64": "<BASE64_JPEG>"
  }'
```

---

## Common issues

| Symptom | Fix |
|---------|-----|
| `Permission denied (publickey)` to Spheron | Private key file missing on PC; add matching `.pub` to **this** VM — see [RUNBOOK-SPHERON.md](./docs/RUNBOOK-SPHERON.md) |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | `ssh-keygen -R <VM_IP>` then reconnect |
| `Python was not found` (Windows) | Install Python 3.12+ to PATH; disable Store aliases; use `.venv\Scripts\python.exe` |
| `pipefail: invalid option` on VM | CRLF in shell scripts — fixed by `spheron_windows_setup.ps1` or `sed -i 's/\r$//'` on `scripts/*.sh` |
| Generate uses CPU not GPU | Run API on Spheron; tunnel `:8001` — do not run uvicorn on Windows for production tests |
| Old purple sidebar UI | VM still on old `next` process — `make deploy-web` on VM; browser http://127.0.0.1:3000 + hard refresh |
| `422 use_inpaint_correction` | API not restarted — `make deploy-api` on VM after sync |
| `EADDRINUSE :3000` | `fuser -k 3000/tcp` then `make deploy-web` |
| `make spheron-sync` fails on VM | Run spheron targets from **Mac**, not inside SSH |
| Mac shows old UI on :3000 | SSH tunnel points to VM — use `npm run dev:local` on **:3001** |
| `/_next/static` 500 | Stale `.next` — `make deploy-web` (deletes `.next` and rebuilds) |
| Reference ≠ output ring | Expected today — CLIP only; see ARCHITECTURE.md |

---

## Env vars (inference)

| Variable | Default | Notes |
|----------|---------|-------|
| `DEVICE` | auto | `cuda` on VM, `mps` on Mac |
| `GENERATION_TIMEOUT_SECONDS` | `90` | Use `300` on GPU / quality tiers |
| `SDXL_API_KEY` | `dev-local-key` | Match `apps/web/.env.local` |
| `SDXL_MODEL_PATH` | `./models/sdxl-base` | |
| `ARTIFACTS_DIR` | `./generated` | Job SQLite + JPEG artifacts |
| `JOB_DB_PATH` | `./generated/jobs.db` | Job persistence |

Web proxy (`apps/web/.env.local`): `SDXL_API_URL`, `SDXL_JOBS_URL`, `SDXL_API_KEY`, `SDXL_FETCH_TIMEOUT_MS` — see `.env.example`.
