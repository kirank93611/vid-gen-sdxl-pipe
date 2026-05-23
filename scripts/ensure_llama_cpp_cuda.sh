#!/usr/bin/env bash
# Prebuilt llama-cpp-python (CUDA) + pip CUDA runtime libs (no system nvcc required).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$REPO_ROOT/.venv/bin/activate"

pip install --no-cache-dir \
  nvidia-cuda-runtime-cu12 \
  nvidia-cublas-cu12

pip uninstall -y llama-cpp-python 2>/dev/null || true
pip install --no-cache-dir llama-cpp-python \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124

echo "==> llama-cpp-python CUDA wheel installed"
