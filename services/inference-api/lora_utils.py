"""Resolve LoRA files under LORAS_DIR — local .safetensors only (no arbitrary paths)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from api_config import LORAS_DIR

LoraBackend = Literal["sdxl", "ltx", "wan"]

# Safe catalog ids: filename stem only (no path separators or ..)
_LORA_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")

# Filename heuristics — video LoRAs are not interchangeable with SDXL.
_LTX_MARKERS = ("ltxxx", "ltx2", "ltx-2", "ltx_2", "ltxvideo", "ltx_video")
_WAN_MARKERS = ("_wan", "wan_", "wan2", "wan-2", "wan_2", "i2v_14b", "t2v_14b")


def validate_lora_name(name: str) -> str:
    if not _LORA_NAME_RE.fullmatch(name):
        raise ValueError(
            "Invalid lora_name: use letters, numbers, dot, underscore, hyphen (no paths)."
        )
    return name


def resolve_lora_path(lora_name: str) -> Path:
    """Map catalog id → models/loras/<name>.safetensors"""
    validate_lora_name(lora_name)
    path = (LORAS_DIR / f"{lora_name}.safetensors").resolve()
    root = LORAS_DIR.resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("Invalid lora_name")
    if not path.is_file():
        raise FileNotFoundError(
            f"LoRA not on disk: {path.name}. "
            f"Download .safetensors to {root} and use lora_name={lora_name!r}."
        )
    return path


def infer_lora_backend(lora_name: str) -> LoraBackend:
    """Guess which base model a LoRA was trained for (catalog id / filename stem)."""
    lower = lora_name.lower()
    if "ltx" in lower or any(marker in lower for marker in _LTX_MARKERS):
        return "ltx"
    if "wan" in lower or any(marker in lower for marker in _WAN_MARKERS):
        return "wan"
    return "sdxl"


def image_model_lora_backend(model_id: str) -> LoraBackend | None:
    """Return the LoRA backend for an image model_id, or None if LoRAs do not apply."""
    from checkpoint_utils import is_checkpoint_model_id

    if is_checkpoint_model_id(model_id):
        return None
    lower = model_id.lower()
    if lower.startswith("wan"):
        return "wan"
    if lower.startswith("ltx"):
        return "ltx"
    return "sdxl"


def lora_backend_mismatch_message(lora_name: str, model_id: str) -> str | None:
    """User-facing message when LoRA and base model backends differ."""
    lora_backend = infer_lora_backend(lora_name)
    model_backend = image_model_lora_backend(model_id)
    if model_backend is None:
        return "LoRAs apply to SDXL / video base models only, not SD 1.5 checkpoints."
    if lora_backend == model_backend:
        return None
    return (
        f"LoRA {lora_name!r} requires a {lora_backend.upper()} base model, "
        f"but {model_id!r} is {model_backend.upper()}. "
        f"Switch base model or pick an SDXL LoRA."
    )


def list_lora_names() -> list[dict[str, str]]:
    """Scan LORAS_DIR for *.safetensors (for GET /loras)."""
    if not LORAS_DIR.is_dir():
        return []
    out: list[dict[str, str]] = []
    for p in sorted(LORAS_DIR.glob("*.safetensors")):
        backend = infer_lora_backend(p.stem)
        out.append(
            {
                "lora_name": p.stem,
                "filename": p.name,
                "backend": backend,
            }
        )
    return out
