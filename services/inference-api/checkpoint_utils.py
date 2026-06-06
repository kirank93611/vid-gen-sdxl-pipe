"""Single-file SD 1.5 checkpoints under models/checkpoints/*.safetensors."""

from __future__ import annotations

import re
from pathlib import Path

from api_config import REPO_ROOT

CHECKPOINTS_DIR = Path(
    __import__("os").environ.get(
        "CHECKPOINTS_DIR",
        str(REPO_ROOT / "models" / "checkpoints"),
    )
)

_CKPT_PREFIX = "ckpt_"
_STEM_RE = re.compile(r"^[\w.\-]+$")


def validate_checkpoint_stem(stem: str) -> str:
    if not stem or not _STEM_RE.match(stem):
        raise ValueError("Invalid checkpoint id")
    return stem


def checkpoint_model_id(stem: str) -> str:
    return f"{_CKPT_PREFIX}{validate_checkpoint_stem(stem)}"


def is_checkpoint_model_id(model_id: str) -> bool:
    return model_id.startswith(_CKPT_PREFIX)


def normalize_model_id(model_id: str | None) -> str:
    if not model_id:
        from generation_profiles import DEFAULT_MODEL_ID

        return DEFAULT_MODEL_ID
    if model_id == "sdxl_base" or is_checkpoint_model_id(model_id):
        return model_id
    raise ValueError(
        f"Unknown model_id: {model_id}. Use sdxl_base or ckpt_<filename_stem>."
    )


def resolve_checkpoint_path(model_id: str) -> Path:
    if not is_checkpoint_model_id(model_id):
        raise ValueError(f"Not a checkpoint model_id: {model_id}")
    stem = model_id[len(_CKPT_PREFIX) :]
    validate_checkpoint_stem(stem)
    path = (CHECKPOINTS_DIR / f"{stem}.safetensors").resolve()
    root = CHECKPOINTS_DIR.resolve()
    if root not in path.parents and path.parent != root:
        raise ValueError("Invalid checkpoint path")
    if not path.is_file():
        raise FileNotFoundError(
            f"Checkpoint not found: {path.name}. Upload to {root} on the GPU VM."
        )
    return path


def list_checkpoints() -> list[dict[str, str]]:
    root = CHECKPOINTS_DIR
    if not root.is_dir():
        return []
    out: list[dict[str, str]] = []
    for p in sorted(root.glob("*.safetensors")):
        stem = p.stem
        try:
            validate_checkpoint_stem(stem)
        except ValueError:
            continue
        out.append(
            {
                "model_id": checkpoint_model_id(stem),
                "display_name": stem,
                "filename": p.name,
                "backend": "sd15",
            }
        )
    return out
