# Shared packages (optional)

Use this folder for workspace-local packages shared across apps, for example:

- TypeScript types generated from the inference OpenAPI schema (`GET /openapi.json`)
- Shared constants (error codes, tier names) for `apps/web` and future clients

Nothing here is required for the current MVP. The live contract is defined in `services/inference-api/schemas.py` and validated by `services/inference-api/tests/`.

When you add a package, prefer importing generated types into `apps/web` rather than duplicating request/response shapes by hand.
