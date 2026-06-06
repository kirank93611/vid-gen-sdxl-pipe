"""Model-agnostic output evaluation (rules + optional CLIP vs reference)."""

from __future__ import annotations

import base64
import logging

from clip_evaluator import clip_similarity, default_similarity_threshold
from schemas import EvalResult, GenerateRequest, VisualGoal
from sdxl_adapter import effective_request

logger = logging.getLogger("sdxl_api")

_HIGH_REALISM_MIN_STEPS = 20


def decode_reference(reference_image_base64: str | None) -> bytes | None:
    """Decode optional base64 reference image for CLIP evaluation."""
    if not reference_image_base64:
        return None
    try:
        return base64.b64decode(reference_image_base64, validate=True)
    except Exception as exc:
        raise ValueError("Invalid reference_image_base64") from exc


def evaluate_output(
    goal: VisualGoal,
    request: GenerateRequest,
    *,
    attempt: int,
    output_image: bytes | None = None,
    reference_image: bytes | None = None,
) -> EvalResult:
    """
    Score a completed generation against goal constraints.

    When reference_image is set and preserve_product or product_similarity_min is set,
    runs CLIP image–image similarity (visual eval v1).
    """
    effective, _model_id = effective_request(request)
    issues: list[str] = []
    metrics: dict[str, float] = {}
    score = 1.0

    if goal.realism == "high":
        if effective.quality_tier == "fast":
            issues.append("tier_too_low")
            score = min(score, 0.4)
        if effective.steps < _HIGH_REALISM_MIN_STEPS:
            issues.append("steps_too_low")
            score = min(score, 0.5)

    if goal.preserve_product and effective.quality_tier == "fast":
        issues.append("product_fidelity_risk")
        score = min(score, 0.45)

    use_clip = reference_image is not None and (
        goal.preserve_product or goal.product_similarity_min is not None
    )
    if use_clip and output_image is not None:
        try:
            similarity = clip_similarity(reference_image, output_image)
            metrics["clip_similarity"] = similarity
            threshold = default_similarity_threshold(goal.product_similarity_min)
            metrics["clip_similarity_min"] = threshold
            if similarity < threshold:
                issues.append("product_similarity_low")
                score = min(score, similarity)
        except Exception as exc:
            logger.exception("CLIP evaluation failed on attempt %s", attempt)
            issues.append("evaluation_failed")
            score = 0.0

    passed = len(issues) == 0
    return EvalResult(
        passed=passed,
        score=score,
        issues=issues,
        attempt=attempt,
        metrics=metrics,
    )
