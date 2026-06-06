"""
Unified model discovery — plug-and-play catalog for clients.

Discovery rules (no code change to add assets):
  - SDXL diffusers dir: register in model_catalog.IMAGE_MODELS (+ files on disk)
  - SD 1.5 checkpoints: drop *.safetensors in models/checkpoints/ → ckpt_<stem>
  - LoRAs: drop *.safetensors in models/loras/ → lora_name = stem
  - GGUF chat: register in model_catalog.CHAT_MODELS + download script
  - Generation presets: generation_profiles.PROFILES (API GET /generation-profiles)
"""

from __future__ import annotations

from typing import Any

from checkpoint_utils import list_checkpoints
from model_catalog import list_models_payload


def list_all_models() -> list[dict[str, Any]]:
    """Merge static image/chat catalog with filesystem SD 1.5 checkpoints."""
    models = list_models_payload()
    seen = {m["model_id"] for m in models}
    for ckpt in list_checkpoints():
        mid = ckpt["model_id"]
        if mid in seen:
            continue
        models.append(
            {
                "model_id": mid,
                "display_name": ckpt["display_name"],
                "family": "image",
                "backend": ckpt["backend"],
                "supports": ["text_to_image"],
                "on_disk": True,
            }
        )
        seen.add(mid)
    return models
