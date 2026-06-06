# ADR 0001: Monorepo layout (Next.js + FastAPI inference)

**Status:** Accepted  
**Date:** 2026-05

## Context

We need SEO/marketing pages, a product studio UI, and GPU-backed image generation. Running SDXL in the browser or in Next.js API routes is not viable for production.

## Decision

1. **Single Next.js app** at `apps/web/` with route groups for public (`/explore`) and product studio (`/`).
2. **Dedicated inference service** at `services/inference-api/` — one deployable, own Dockerfile/env, scales on GPU hosts.
3. **HTTP JSON contract** owned by FastAPI Pydantic models; web proxies via Route Handlers.
4. **Optional** `packages/shared/` later for OpenAPI-generated types — not required for MVP.

## Consequences

- CORS and API keys are managed at the proxy layer for browser clients.
- Contract changes require coordinated updates to Python tests and Next.js `/api/*` routes.
- Spheron (or any GPU VM) deploys inference and web as separate processes; see `scripts/` and Makefile.

## Alternatives considered

- **FastAPI templates for marketing:** Rejected — poor SEO and splits design ownership.
- **Multiple Next apps (`landing` + `dashboard`):** Deferred until separate deploys or teams are needed.

## References

- `.cursor/rules/monorepo-layout.mdc`
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [docs/CODEBASE.md](../CODEBASE.md)
