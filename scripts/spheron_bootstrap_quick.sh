#!/usr/bin/env bash
# Fast path after spot VM recycle: skip torch/model if already on disk.
# Run on VM: cd /root/image-sd && bash scripts/spheron_bootstrap_quick.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> GPU"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

echo "==> Python venv"
if [[ ! -f .venv/bin/activate ]]; then
  echo "No .venv — run full setup: bash scripts/spheron_setup.sh"
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
  echo "CUDA torch missing — run: bash scripts/spheron_setup.sh"
  exit 1
fi
python -c "import torch; print('cuda:', torch.cuda.get_device_name(0))"

echo "==> App imports"
if ! python -c "import fastapi, diffusers" 2>/dev/null; then
  pip install -q fastapi uvicorn diffusers transformers accelerate pydantic pillow huggingface_hub httpx safetensors
fi

MODEL_DIR="${SDXL_MODEL_PATH:-$REPO_ROOT/models/sdxl-base}"
UNET="$MODEL_DIR/unet/diffusion_pytorch_model.fp16.safetensors"
if [[ ! -f "$UNET" ]]; then
  echo "SDXL weights missing — run: bash scripts/spheron_setup.sh"
  exit 1
fi
echo "Model OK: $MODEL_DIR"

# shellcheck disable=SC1091
. "$(dirname "$0")/spheron_ensure_node.sh"

export DEVICE="${DEVICE:-cuda}"
export GENERATION_TIMEOUT_SECONDS="${GENERATION_TIMEOUT_SECONDS:-300}"
export SDXL_MODEL_PATH="$MODEL_DIR"

echo "==> API"
bash scripts/spheron_restart_api.sh

echo "==> Web"
bash scripts/spheron_deploy_web.sh

echo "==> Ready. From Mac: make spheron-tunnel"
