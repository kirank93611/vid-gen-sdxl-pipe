#!/usr/bin/env bash
# Remove local build artifacts (safe to re-run). Does not delete models/, .venv/, or node_modules/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Removing Next.js build cache..."
rm -rf apps/web/.next apps/web/out

echo "==> Removing benchmark / generated outputs..."
rm -rf benchmarks/product_similarity/results/*
mkdir -p benchmarks/product_similarity/results
rm -rf generated/* 2>/dev/null || true
mkdir -p generated 2>/dev/null || true

echo "==> Removing Python caches..."
find services/inference-api -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo "==> Done. Reinstall/run:"
echo "    make test-integration"
echo "    make run"
echo "    cd apps/web && npm run dev:local"
