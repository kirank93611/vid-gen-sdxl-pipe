#!/usr/bin/env bash
# Run entirely ON the Spheron VM after code is present (no Mac model upload).
# Usage: ssh ubuntu@<host> 'cd ~/image-sd && bash scripts/spheron_vm_bootstrap.sh'
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f services/inference-api/main.py ]]; then
  echo "ERROR: services/inference-api/main.py missing. Sync code only from Mac:"
  echo "  rsync -avz --exclude .venv --exclude models --exclude node_modules --exclude .git \\"
  echo "    ./ ubuntu@<host>:~/image-sd/"
  exit 1
fi

bash scripts/spheron_setup.sh

export DEVICE=cuda
export SDXL_MODEL_PATH="${SDXL_MODEL_PATH:-$REPO_ROOT/models/sdxl-base}"
export GENERATION_TIMEOUT_SECONDS="${GENERATION_TIMEOUT_SECONDS:-300}"
export EXPECTED_API_KEY="${EXPECTED_API_KEY:-dev-local-key}"

# shellcheck disable=SC1091
source .venv/bin/activate

if pgrep -f "uvicorn main:app" >/dev/null 2>&1; then
  echo "==> Stopping existing uvicorn"
  pkill -f "uvicorn main:app" || true
  sleep 2
fi

echo "==> Starting API on 0.0.0.0:8001 (log: /tmp/sdxl-api.log)"
cd services/inference-api
nohup uvicorn main:app --host 0.0.0.0 --port 8001 > /tmp/sdxl-api.log 2>&1 &
cd "$REPO_ROOT"

echo "==> Waiting for model load (first start can take 1–2 min)..."
for _ in $(seq 1 120); do
  if curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
    curl -s http://127.0.0.1:8001/health
    echo ""
    break
  fi
  sleep 2
done

echo "==> Generating test image"
python scripts/spheron_generate.py \
  --api-url http://127.0.0.1:8001 \
  --api-key "$EXPECTED_API_KEY" \
  --out generated/spheron_smoke.jpg \
  --prompt "luxury gold ring on black velvet, studio softbox lighting, photorealistic product photography"

echo "==> Done. Image: $REPO_ROOT/generated/spheron_smoke.jpg"
echo "    Pull to Mac: scp ubuntu@<host>:~/image-sd/generated/spheron_smoke.jpg ."
echo ""
echo "==> Optional: studio UI on port 3000"
echo "    bash scripts/spheron_deploy_web.sh"
echo "    Mac tunnel: ssh -L 3000:127.0.0.1:3000 ubuntu@<host>  →  http://127.0.0.1:3000"
