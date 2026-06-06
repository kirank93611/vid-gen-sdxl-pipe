"""Resolve LoRA files under LORAS_DIR — local .safetensors only (no arbitrary paths)."""

from __future__ import annotations

import re
from pathlib import Path

from api_config import LORAS_DIR

# Safe catalog ids: filename stem only (no path separators or ..)
_LORA_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


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


def list_lora_names() -> list[dict[str, str]]:
    """Scan LORAS_DIR for *.safetensors (for GET /loras)."""
    if not LORAS_DIR.is_dir():
        return []
    out: list[dict[str, str]] = []
    for p in sorted(LORAS_DIR.glob("*.safetensors")):
        out.append({"lora_name": p.stem, "filename": p.name})
    return out
