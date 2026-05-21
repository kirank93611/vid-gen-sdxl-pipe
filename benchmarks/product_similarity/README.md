# Product similarity benchmark (coach)

Measures whether the **correction job loop** beats a **single-shot** `/generate` on CLIP similarity vs a reference product image.

## What you need

1. API running: `make run` (use `GENERATION_TIMEOUT_SECONDS=300` for multi-step jobs).
2. One JPEG per case under `fixtures/` (paths in `manifest.json`).
3. CLIP loads on first run (`CLIP_DEVICE=cpu` recommended while SDXL uses MPS).

## Run

From repo root:

```bash
source .venv/bin/activate
make benchmark-product
# or
python scripts/run_product_benchmark.py \
  --api-url http://127.0.0.1:8001 \
  --api-key dev-local-key
```

Results: `benchmarks/product_similarity/results/latest.json` and `latest.md`.

## Add a case

1. Copy product SKU photo to `fixtures/my_product.jpg`.
2. Add an entry to `manifest.json`:

```json
{
  "id": "my_product",
  "prompt": "your scene prompt — describe placement, not SKU pixels only",
  "reference_path": "fixtures/my_product.jpg"
}
```

3. Re-run the benchmark.

## How to read results

| Field | Meaning |
|-------|---------|
| `baseline.clip_similarity` | One `/generate` vs reference |
| `job.final_clip_similarity` | Last job output vs reference |
| `job.iterations` | How many evaluate passes ran |
| `job.converged` | Evaluator passed (rules + CLIP) |
| `delta_clip` | `final - baseline` (positive = job helped on this metric) |

**This does not prove** human “good photo” — only **reference embedding similarity**. Use it to test the hypothesis before building inpaint.

## Skip missing fixtures

Cases whose `reference_path` file is missing are skipped (listed in `skipped` in the report).
