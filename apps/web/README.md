# Web app (Next.js studio)

Product UI and BFF proxies to the inference API. No GPU code in this package.

**Ops:** [docs/RUNBOOK-SPHERON.md](../../docs/RUNBOOK-SPHERON.md) · **Models:** [docs/MODELS.md](../../docs/MODELS.md)

## Setup

```bash
cd apps/web
cp .env.example .env.local
npm install
```

| Variable | Purpose |
|----------|---------|
| `SDXL_INFERENCE_BASE` | API origin (catalog, health) |
| `SDXL_API_URL` | `POST /generate` |
| `SDXL_JOBS_URL` | Jobs API |
| `SDXL_API_KEY` | Server-side `X-API-Key` |
| `SDXL_FETCH_TIMEOUT_MS` | Proxy timeout (`600000+` for quality) |

## Run

```bash
npm run dev          # http://localhost:3000
npm run dev:local    # :3001 if :3000 is SSH tunnel
```

Tunnel API: `ssh -L 8001:127.0.0.1:8001 ubuntu@<VM_IP>`

## Routes

| Path | Purpose |
|------|---------|
| `/` | Studio editor |
| `/chat` | GGUF chat |
| `/explore` | Marketing |
| `/api/generate` | Proxy generate |
| `/api/jobs/*` | Proxy jobs + artifact |
| `/api/models` | Model catalog |
| `/api/loras` | LoRA catalog |
| `/api/generation-profiles` | Presets from API |
| `/api/chat` | Chat completion |

## Source layout

```text
src/
├── app/                      App Router + API routes
├── components/
│   ├── studio/
│   │   ├── dock/             Minibar + (future) settings panel splits
│   │   ├── generation-dock.tsx
│   │   ├── studio-editor.tsx, studio-canvas.tsx
│   │   └── chat-interface.tsx
│   └── ui/                   shadcn
└── lib/
    ├── api/                  Inference clients (prefer for new code)
    │   ├── inference-config.ts
    │   ├── errors.ts
    │   ├── catalog.ts        models, loras, profiles
    │   └── generate.ts       types + formatGenerationMeta
    └── studio/               UI-only defaults + helpers
        ├── defaults.ts       aspects, prompts, schedulers
        ├── model-utils.ts    ckpt_ detection
        └── profile-utils.ts  apply preset from API profile
```

Legacy barrels `studio-api.ts` and `studio-constants.ts` re-export from `lib/api` and `lib/studio` — migrate imports over time.

## Contract with backend

- **Source of truth:** `services/inference-api/schemas.py` + `GET /openapi.json`
- **Do not duplicate** generation profile numbers in TS — use `fetchGenerationProfiles()`
- Future: OpenAPI codegen → `packages/shared/` per ADR-0001

## Deploy

VM: `bash scripts/spheron_deploy_web.sh` or `make deploy-web`

See [docs/RUNBOOK-SPHERON.md](../../docs/RUNBOOK-SPHERON.md) for troubleshooting.
