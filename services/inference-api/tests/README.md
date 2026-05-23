# Inference API tests

## Integration (`test_integration_api.py`)

- Uses **httpx** `ASGITransport` against `main.app`
- **Mocks** `SDXLEngine.load_model`, `generate`, and `inpaint` — no GPU required
- Resets `main._metrics`, job store, and `rate_limit.reset_for_tests()` in `asyncSetUp`

Run from repo root:

```bash
make test-integration
```

## When to update tests

Any change to:

- Status codes or `error_code` on `/generate`, `/inpaint`, `/jobs`, `/health`, `/metrics`
- Response JSON shape in `schemas.py`
- Auth or rate-limit behavior

## Patching in tests

- API key: `api_config.EXPECTED_API_KEY` and `main.EXPECTED_API_KEY`
- Rate limit threshold: `api_config.RATE_LIMIT_REQUESTS` (read by `rate_limit.py` at runtime)
