# Web (`apps/web`)

Next.js App Router UI for the SDXL inference API. The browser never holds the GPU API key: generation goes through a **server Route Handler** that proxies to FastAPI.

## Prerequisites

- Inference API running (from repo root: `make run` → `http://127.0.0.1:8001`)
- Node.js 20+

## Setup

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment (`/.env.local`)

| Variable | Purpose |
|----------|---------|
| `SDXL_API_URL` | Upstream generate URL (default `http://127.0.0.1:8001/generate`) |
| `SDXL_API_KEY` | Sent as `X-API-Key` from the server only |

Do **not** prefix the API key with `NEXT_PUBLIC_`.

## Project structure

```text
src/
├── app/
│   ├── api/generate/route.ts   # POST proxy to inference API
│   ├── page.tsx                # Generate UI
│   └── layout.tsx
└── components/
    └── generate-form.tsx       # Client form + result / errors
```

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server (port 3000) |
| `npm run build` | Production build |
| `npm run start` | Serve production build |
| `npm run lint` | ESLint |

## API usage from the UI

The form `POST`s JSON `{ "prompt": "..." }` to `/api/generate`. To use server-side quality tiers, extend the form body with `quality_tier` (`fast` | `balanced` | `quality`) — the inference API applies profiles from `services/inference-api/router.py`.

Successful responses expose `metadata` (including `model_id`, `steps`, `request_id` via response headers).

## Deploy notes

- Deploy Next (e.g. Vercel) separately from the GPU API.
- Set `SDXL_API_URL` to a reachable inference host in production.
- Inference on GPU cloud (e.g. Spheron) is documented in the repo root [ARCHITECTURE.md](../../ARCHITECTURE.md).

## Learn more

- Repo root [README.md](../../README.md)
- [Next.js documentation](https://nextjs.org/docs)
