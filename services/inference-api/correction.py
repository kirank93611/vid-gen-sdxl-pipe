"""Map evaluator issues to policy patches (no raw CFG/sampler — adapter owns those)."""

from __future__ import annotations

from schemas import EvalResult, GenerateRequest
from sdxl_adapter import bump_quality_tier


def apply_corrections(req: GenerateRequest, evaluation: EvalResult) -> GenerateRequest | None:
    """
    Return an updated request for the next attempt, or None if no patch applies.
    """
    if evaluation.passed:
        return None

    tier = req.quality_tier
    changed = False

    if "tier_too_low" in evaluation.issues or "steps_too_low" in evaluation.issues:
        next_tier = bump_quality_tier(tier)
        if next_tier is not None:
            tier = next_tier
            changed = True

    if "product_fidelity_risk" in evaluation.issues or "product_similarity_low" in evaluation.issues:
        next_tier = bump_quality_tier(tier)
        if next_tier is not None:
            tier = next_tier
            changed = True

    if not changed:
        return None

    return req.model_copy(update={"quality_tier": tier})
