"""Map evaluator issues to policy patches (tier bump or inpaint correction)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from schemas import EvalResult, GenerateRequest, JobCreateRequest
from sdxl_adapter import bump_quality_tier


@dataclass(frozen=True)
class CorrectionAction:
    kind: Literal["none", "tier_bump", "inpaint"]


def apply_corrections(req: GenerateRequest, evaluation: EvalResult) -> GenerateRequest | None:
    """Return tier-bumped request, or None if no tier patch applies."""
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


def resolve_correction(
    req: GenerateRequest,
    evaluation: EvalResult,
    payload: JobCreateRequest,
    *,
    attempt: int,
) -> tuple[CorrectionAction, GenerateRequest | None]:
    """Choose next correction: inpaint (localized) or tier bump (full reshoot)."""
    if evaluation.passed:
        return CorrectionAction("none"), None

    tier_patch = apply_corrections(req, evaluation)
    similarity_low = "product_similarity_low" in evaluation.issues
    inpaint_enabled = payload.goal.use_inpaint_correction is True
    has_mask = bool(payload.mask_base64) or inpaint_enabled

    if similarity_low and has_mask and attempt >= 2:
        return CorrectionAction("inpaint"), None

    if tier_patch is not None:
        return CorrectionAction("tier_bump"), tier_patch

    if similarity_low and has_mask:
        return CorrectionAction("inpaint"), None

    return CorrectionAction("none"), None
