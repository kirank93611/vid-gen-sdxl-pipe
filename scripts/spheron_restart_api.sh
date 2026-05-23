#!/usr/bin/env bash
# Restart inference API on VM (pick up new schemas.py e.g. use_inpaint_correction).
# Run on VM: bash scripts/spheron_restart_api.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$REPO_ROOT/services/inference-api"

if ! grep -q use_inpaint_correction "$API_DIR/schemas.py" 2>/dev/null; then
  echo "ERROR: schemas.py missing use_inpaint_correction — sync code from Mac first:"
  echo "  make spheron-sync   # run on Mac"
  exit 1
fi

stop_port_8001() {
  echo "==> Freeing port 8001..."
  pkill -9 -f "uvicorn main:app" 2>/dev/null || true
  if command -v fuser >/dev/null 2>&1; then
    fuser -k 8001/tcp 2>/dev/null || true
  fi
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti :8001 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      kill -9 $pids 2>/dev/null || true
    fi
  fi
  sleep 2
}

stop_port_8001

source "$REPO_ROOT/.venv/bin/activate"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/llama_cuda_env.sh"
export DEVICE="${DEVICE:-cuda}"
export GENERATION_TIMEOUT_SECONDS="${GENERATION_TIMEOUT_SECONDS:-300}"
export GENERATION_CANCEL_GRACE_SECONDS="${GENERATION_CANCEL_GRACE_SECONDS:-120}"
export INPAINT_STRENGTH="${INPAINT_STRENGTH:-0.85}"

echo "==> Checking Python can import main..."
cd "$API_DIR"
if ! python -c "import main" 2>/tmp/sdxl-import.log; then
  echo "ERROR: import main failed:"
  cat /tmp/sdxl-import.log
  exit 1
fi

: > /tmp/sdxl-api.log
echo "==> Starting uvicorn on :8001..."
nohup uvicorn main:app --host 0.0.0.0 --port 8001 >> /tmp/sdxl-api.log 2>&1 &

echo "==> Waiting for /health (up to 90s)..."
for i in $(seq 1 90); do
  if curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
    echo "==> API healthy (${i}s)"
    curl -s http://127.0.0.1:8001/health
    echo ""
    exit 0
  fi
  if grep -qE "Error|Traceback|Address already in use" /tmp/sdxl-api.log 2>/dev/null; then
    if grep -q "Address already in use" /tmp/sdxl-api.log; then
      echo "ERROR: port 8001 still busy — run: ss -tlnp | grep 8001"
      stop_port_8001
      exit 1
    fi
    if [[ $i -gt 5 ]] && grep -q Traceback /tmp/sdxl-api.log; then
      echo "ERROR: uvicorn crashed on startup:"
      tail -40 /tmp/sdxl-api.log
      exit 1
    fi
  fi
  sleep 1
done

echo "ERROR: /health did not respond in 90s"
tail -40 /tmp/sdxl-api.log
exit 1
