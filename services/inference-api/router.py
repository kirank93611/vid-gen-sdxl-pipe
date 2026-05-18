"""Map quality_tier into concrete generation parameters (single sdxl_base engine for now)."""

from __future__ import annotations

from schemas import GenerateRequest

# Logical backend id until you load a second checkpoint.
DEFAULT_MODEL_ID = "sdxl_base"

_TIER_STEPS_GUIDANCE: dict[str, tuple[int, float]] = {
    "fast": (12, 5.0),
    "balanced": (25, 6.0),
    "quality": (35, 7.0),
}


def apply_quality_tier(req: GenerateRequest) -> tuple[GenerateRequest, str]:
    """
    Returns (effective_request, model_id).

    If quality_tier is None, effective_request == req (no override).
    If set, steps and guidance_scale are replaced from the table; other fields unchanged.
    """
    if req.quality_tier is None:
        return req, DEFAULT_MODEL_ID

    steps, guidance = _TIER_STEPS_GUIDANCE[req.quality_tier]
    effective = req.model_copy(
        update={"steps": steps, "guidance_scale": guidance},
    )
    return effective, DEFAULT_MODEL_ID
