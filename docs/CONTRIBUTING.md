# Contributing

Guidelines for engineers extending this monorepo.

## Prerequisites

- Python 3.11+ with repo-root `.venv`
- Node 20+ for `apps/web`
- SDXL weights under `models/sdxl-base/` (not in git)

## Development workflow

1. **Branch** from `main` (or the active feature branch) with a focused scope.
2. **API changes** start in `services/inference-api/schemas.py`; run `make test-integration` before opening a PR.
3. **Web changes** use `cd apps/web && npm run dev:local` (port **3001** avoids SSH tunnel clashes on 3000).
4. **Contract checklist** (from `.cursor/rules/quality-and-contracts.mdc`):
   - Integration tests green
   - [README.md](../README.md) API examples still accurate
   - [ARCHITECTURE.md](../ARCHITECTURE.md) if design meaning changes
   - Next.js fetch/types if response shapes change

## Code style

### Python (`services/inference-api/`)

- Flat package layout: modules live beside `main.py` (no `__init__.py` package install).
- **Config:** add env vars to `api_config.py`, not scattered `os.getenv`.
- **HTTP concerns:** auth in `api_auth.py`, rate limits in `rate_limit.py`, routes stay thin in `main.py`.
- **Logging:** use `api_logging.log_info` / `log_error` with `request_id`.
- **Stable `error_code` values** are product surface — additive only unless versioning.

### TypeScript (`apps/web/`)

- App Router, server components where possible for SEO routes.
- Studio UI under `components/studio/`; shadcn under `components/ui/`.
- Call inference only via `/api/*` Route Handlers (never embed GPU keys in client bundles).

## Testing

```bash
make test-integration    # required for inference API changes
```

Flaky tests: backpressure and timeout tests use sleeps — keep them conservative under CI load.

## Commits and PRs

- One logical change per PR when possible (API vs UI vs deploy scripts).
- PR body: summary + test plan (commands run, manual checks on VM if deploy-related).

## Documentation updates

| Change type | Update |
|-------------|--------|
| New endpoint or field | `schemas.py`, integration tests, README API section |
| New env var | `api_config.py`, `services/inference-api/README.md` |
| Deploy flow | `scripts/README.md`, root README |
| Architectural decision | New file under `docs/adr/` |

See [CODEBASE.md](./CODEBASE.md) for the full module map.
