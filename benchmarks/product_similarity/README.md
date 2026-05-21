# Product similarity benchmark

Compares single-shot `POST /generate` vs correction `POST /jobs` using CLIP vs a reference JPEG.

## Run

1. Add fixtures: `fixtures/ring_reference.jpg`, `fixtures/watch_reference.jpg` (or edit `manifest.json`).
2. Start API: `make run` (Mac) or VM API on `:8001`.
3. From repo root:

```bash
export GENERATION_TIMEOUT_SECONDS=600   # Mac MPS
make benchmark-product
```

Results: `results/latest.md` (gitignored — regenerated each run).

On GPU VM:

```bash
make spheron-benchmark   # from Mac only
```

See root [README.md](../../README.md) for deploy steps.
