#!/usr/bin/env bash
# Source before starting uvicorn when using GGUF chat (prebuilt cu124 wheel).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  return 0 2>/dev/null || exit 0
fi
SITE="$("$PY" -c 'import site; print(site.getsitepackages()[0])')"
for sub in nvidia/cuda_runtime/lib nvidia/cublas/lib; do
  if [[ -d "$SITE/$sub" ]]; then
    export LD_LIBRARY_PATH="$SITE/$sub:${LD_LIBRARY_PATH:-}"
  fi
done
