"""SDXL adapter: translate policy (tier) into GenerateRequest execution fields."""

from __future__ import annotations

from schemas import GenerateRequest, InpaintRequest
from generation_profiles import apply_generation_policy

TIER_ORDER = ("fast", "balanced", "quality")


def effective_request(req: GenerateRequest) -> tuple[GenerateRequest, str]:
    """Apply generation_profile / quality_tier policy."""
    return apply_generation_policy(req)


def effective_inpaint_request(req: InpaintRequest) -> tuple[GenerateRequest, str]:
    """Map InpaintRequest policy fields into a GenerateRequest for the adapter."""
    gen = GenerateRequest(
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        quality_tier=req.quality_tier,
        seed=req.seed,
        width=req.width,
        height=req.height,
    )
    return apply_generation_policy(gen)


def bump_quality_tier(current: str | None) -> str | None:
    """Move fast → balanced → quality; return None if already at max."""
    if current is None:
        return "balanced"
    try:
        idx = TIER_ORDER.index(current)
    except ValueError:
        return "balanced"
    if idx >= len(TIER_ORDER) - 1:
        return None
    return TIER_ORDER[idx + 1]


def build_metadata(
    effective: GenerateRequest,
    payload: GenerateRequest,
    model_id: str,
    used_seed: int,
) -> dict[str, str | int | float | None]:
    return {
        "prompt": effective.prompt,
        "width": effective.width,
        "height": effective.height,
        "steps": effective.steps,
        "guidance_scale": effective.guidance_scale,
        "clip_skip": effective.clip_skip,
        "scheduler": effective.scheduler,
        "seed": used_seed,
        "model_id": model_id,
        "generation_profile": payload.generation_profile or payload.quality_tier,
        "quality_tier": payload.quality_tier,
        "lora_name": effective.lora_name,
        "lora_weight": effective.lora_weight if effective.lora_name else None,
        "num_frames": getattr(effective, "num_frames", None),
        "frame_rate": getattr(effective, "frame_rate", None),
        "media_type": "video/mp4" if model_id.startswith("ltx") else "image/jpeg",
    }
