"""SDXL adapter: translate policy (tier) into GenerateRequest execution fields."""

from __future__ import annotations

from schemas import GenerateRequest
from router import apply_quality_tier

TIER_ORDER = ("fast", "balanced", "quality")


def effective_request(req: GenerateRequest) -> tuple[GenerateRequest, str]:
    """Apply quality_tier policy then return (effective_request, model_id)."""
    return apply_quality_tier(req)


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
        "quality_tier": payload.quality_tier,
    }
