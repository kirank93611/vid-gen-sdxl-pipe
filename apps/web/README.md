# Web app (Next.js studio)

Product UI and Route Handler proxies to the inference API. No GPU code in this package.

## Setup

```bash
cd apps/web
cp .env.example .env.local
npm install
```

| Variable | Purpose |
|----------|---------|
| `SDXL_API_URL` | Inference base URL for `/api/generate` |
| `SDXL_JOBS_URL` | Inference base URL for `/api/jobs` |
| `SDXL_API_KEY` | Server-side key forwarded as `X-API-Key` |

## Run

```bash
npm run dev:local   # http://localhost:3001 — avoids VM SSH tunnel on :3000
npm run build && npm run start   # production on :3000
```

## Routes

| Path | Type | Purpose |
|------|------|---------|
| `/` | Client | Studio editor (`StudioEditor` + bottom dock) |
| `/explore` | Server | Marketing / hero |
| `/studio` | Redirect | → `/` |
| `/api/generate` | Route Handler | Proxy to `POST /generate` |
| `/api/jobs` | Route Handler | Proxy to `POST /jobs` |
| `/api/jobs/[jobId]` | Route Handler | Proxy to `GET /jobs/{id}` |

## Source layout

```text
src/
├── app/                    App Router pages and API routes
├── components/studio/      Editor: canvas, generation dock, layout
├── components/ui/          shadcn/ui primitives
└── lib/
    ├── studio-api.ts       Typed fetch + error formatting
    └── studio-constants.ts  Quality tiers, aspect ratios, defaults
```

**Largest UI file:** `components/studio/generation-dock.tsx` — generate vs product-job modes, polling, reference upload.

## Design system

- Tailwind + shadcn/ui
- Theme tokens in `src/app/globals.css` (lime accent studio look)
- Motion via `framer-motion` in studio components

## Contract with backend

Do not duplicate request field definitions by hand long-term — prefer OpenAPI codegen into `lib/api-types` when the API stabilizes. Until then, keep `studio-api.ts` in sync with `services/inference-api/schemas.py`.

## Production / VM notes

If you SSH-tunnel the VM web process to local port 3000, run local dev on **3001** (`dev:local`). Mixing `next dev` HTML with `next start` static chunks causes `/_next/static` 500 errors — rebuild with `rm -rf .next && npm run build`.

Deploy on GPU VM: `make deploy-web` from repo root (see [scripts/README.md](../../scripts/README.md)).
