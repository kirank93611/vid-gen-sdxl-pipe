#!/usr/bin/env bash
# Run on Spheron Ubuntu GPU VM (RTX 6000 Ada). Installs deps, downloads SDXL weights, smoke-checks CUDA.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> GPU"
if ! nvidia-smi; then
  echo ""
  echo "nvidia-smi failed (often: Driver/library version mismatch after apt upgrade)."
  echo "Fix: sudo reboot   (wait 1–2 min, SSH back in, re-run this script)"
  echo "Spheron panel may also offer Restart instance."
  exit 1
fi

echo "==> Python venv"
if [[ ! -f .venv/bin/activate ]]; then
  rm -rf .venv
  if ! python3 -m venv .venv 2>/dev/null; then
    echo "Installing python3-venv..."
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip
    python3 -m venv .venv
  fi
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> PyTorch (CUDA)"
if ! python -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
  pip install --upgrade pip
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
fi
python -c "import torch; print('cuda:', torch.cuda.is_available(), torch.cuda.get_device_name(0))"

echo "==> App dependencies"
pip install -q fastapi uvicorn diffusers transformers accelerate pydantic pillow huggingface_hub httpx safetensors

echo "==> SDXL weights (download on VM — faster than rsync from Mac)"
MODEL_DIR="${SDXL_MODEL_PATH:-$REPO_ROOT/models/sdxl-base}"
UNET_WEIGHT="$MODEL_DIR/unet/diffusion_pytorch_model.fp16.safetensors"
if [[ ! -f "$UNET_WEIGHT" ]]; then
  mkdir -p "$MODEL_DIR"
  export SDXL_MODEL_PATH="$MODEL_DIR"
  python - <<'PY'
from huggingface_hub import snapshot_download
import os
dest = os.environ["SDXL_MODEL_PATH"]
snapshot_download(
    repo_id="stabilityai/stable-diffusion-xl-base-1.0",
    local_dir=dest,
    allow_patterns=[
        "model_index.json", "scheduler/*", "tokenizer/*", "tokenizer_2/*",
        "text_encoder/config.json", "text_encoder/model.fp16.safetensors",
        "text_encoder_2/config.json", "text_encoder_2/model.fp16.safetensors",
        "vae/config.json", "vae/diffusion_pytorch_model.fp16.safetensors",
        "unet/config.json", "unet/diffusion_pytorch_model.fp16.safetensors",
    ],
)
print("Downloaded to", dest)
PY
else
  echo "Model already present at $MODEL_DIR ($(du -sh "$MODEL_DIR" | cut -f1))"
fi

echo "==> Done. Start API with:"
echo "  export DEVICE=cuda SDXL_MODEL_PATH=$MODEL_DIR GENERATION_TIMEOUT_SECONDS=300"
echo "  make run"
