"""
Central model catalog — add new models here (image + GGUF chat).

Paths: <repo>/models/<local_subdir>/<gguf_filename>
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from api_config import LTX_MODEL_PATH, REPO_ROOT, SDXL_MODEL_PATH

ModelFamily = Literal["image", "chat"]
ImageEngine = Literal["sdxl", "ltx2", "sd15"]


@dataclass(frozen=True)
class ImageModelSpec:
    model_id: str
    display_name: str
    local_path: Path
    engine: ImageEngine = "sdxl"
    supports: tuple[str, ...] = (
        "text_to_image",
        "quality_tier_routing",
        "inpainting",
    )

    @property
    def family(self) -> ModelFamily:
        return "image"

    def is_on_disk(self) -> bool:
        if self.engine == "ltx2":
            from ltx_engine import ltx_model_on_disk

            return ltx_model_on_disk(self.local_path)
        return self.local_path.is_dir()


@dataclass(frozen=True)
class ChatModelSpec:
    model_id: str
    display_name: str
    hf_repo: str
    gguf_filename: str
    local_subdir: str
    n_ctx: int = 4096
    n_gpu_layers: int = -1
    vram_gb_hint: float = 12.0
    gguf_min_bytes: int | None = None
    supports: tuple[str, ...] = ("chat", "text_completion", "prompt_expansion")
    default: bool = False

    @property
    def family(self) -> ModelFamily:
        return "chat"

    def gguf_path(self) -> Path:
        return REPO_ROOT / "models" / self.local_subdir / self.gguf_filename

    def is_on_disk(self) -> bool:
        p = self.gguf_path()
        if not p.is_file():
            return False
        min_bytes = self.gguf_min_bytes if self.gguf_min_bytes is not None else 100_000_000
        return p.stat().st_size >= min_bytes


IMAGE_MODELS: dict[str, ImageModelSpec] = {
    "sdxl_base": ImageModelSpec(
        model_id="sdxl_base",
        display_name="SDXL 1.0 Base",
        local_path=Path(SDXL_MODEL_PATH),
        engine="sdxl",
    ),
    "ltx_video": ImageModelSpec(
        model_id="ltx_video",
        display_name="LTX 2.3 Dev",
        local_path=LTX_MODEL_PATH,
        engine="ltx2",
        supports=("text_to_video", "quality_tier_routing"),
    ),
}

CHAT_MODELS: dict[str, ChatModelSpec] = {
    "tiefighter_20b": ChatModelSpec(
        model_id="tiefighter_20b",
        display_name="TieFighter Holomax 20B",
        hf_repo="DavidAU/TieFighter-Holodeck-Holomax-Mythomax-F1-V1-COMPOS-20B-gguf",
        gguf_filename="TieFighter-Holodeck-Holomax-Mythomax-F1-V1-COMPOS-20B-Q4_K_M.gguf",
        local_subdir="tiefighter-20b",
        n_ctx=4096,
        vram_gb_hint=12.0,
    ),
    "dolphin_mixtral_8x7b": ChatModelSpec(
        model_id="dolphin_mixtral_8x7b",
        display_name="Dolphin 2.6 Mixtral 8x7B",
        # mradermacher repack — TheBloke GGUFs fail on current llama.cpp (missing MoE tensors).
        hf_repo="mradermacher/dolphin-2.6-mixtral-8x7b-GGUF",
        gguf_filename="dolphin-2.6-mixtral-8x7b.Q4_K_M.gguf",
        local_subdir="dolphin-mixtral-8x7b",
        n_ctx=8192,
        vram_gb_hint=28.0,
        gguf_min_bytes=27_000_000_000,
        default=True,
    ),
}

IMAGE_MODEL_IDS = frozenset(IMAGE_MODELS.keys())
CHAT_MODEL_IDS = frozenset(CHAT_MODELS.keys())
SUPPORTED_MODEL_IDS = IMAGE_MODEL_IDS | CHAT_MODEL_IDS


def get_chat_model(model_id: str) -> ChatModelSpec:
    spec = CHAT_MODELS.get(model_id)
    if spec is None:
        raise ValueError(
            f"Unknown chat model_id: {model_id}. "
            f"Available: {', '.join(sorted(CHAT_MODEL_IDS))}"
        )
    return spec


def get_image_model(model_id: str) -> ImageModelSpec:
    spec = IMAGE_MODELS.get(model_id)
    if spec is None:
        raise ValueError(
            f"Unknown image model_id: {model_id}. "
            f"Available: {', '.join(sorted(IMAGE_MODEL_IDS))}"
        )
    return spec


def default_chat_model_id() -> str:
    for spec in CHAT_MODELS.values():
        if spec.default:
            return spec.model_id
    return next(iter(CHAT_MODEL_IDS))


def list_chat_model_ids() -> list[str]:
    return sorted(CHAT_MODEL_IDS)


def list_models_payload() -> list[dict]:
    out: list[dict] = []
    for spec in IMAGE_MODELS.values():
        out.append(
            {
                "model_id": spec.model_id,
                "display_name": spec.display_name,
                "family": "image",
                "supports": list(spec.supports),
                "backend": spec.engine if spec.engine != "sdxl" else "sdxl",
                "on_disk": spec.is_on_disk(),
            }
        )
    for spec in CHAT_MODELS.values():
        out.append(
            {
                "model_id": spec.model_id,
                "display_name": spec.display_name,
                "family": "chat",
                "supports": list(spec.supports),
                "on_disk": spec.is_on_disk(),
                "vram_gb_hint": spec.vram_gb_hint,
                "hf_repo": spec.hf_repo,
                "gguf_filename": spec.gguf_filename,
                "default": spec.default,
            }
        )
    return out


def list_capabilities() -> list[dict]:
    return [
        {"model_id": m["model_id"], "supports": tuple(m["supports"])}
        for m in list_models_payload()
    ]
