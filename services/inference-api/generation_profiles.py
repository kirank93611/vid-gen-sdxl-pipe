"""Composable generation presets (blocks) — map profile id → runtime knobs.

Profiles merge onto the client request; explicit ``custom`` skips preset overrides
except ``model_id``. ``quality_tier`` is legacy; prefer ``generation_profile``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from schemas import GenerateRequest

ProfileId = Literal[
    "custom",
    "lightning_4",
    "lightning_8",
    "sdxl_fast",
    "sdxl_balanced",
    "sdxl_quality",
    "sd15_standard",
]

DEFAULT_MODEL_ID = "sdxl_base"


@dataclass(frozen=True)
class GenerationProfile:
    profile_id: ProfileId
    display_name: str
    description: str
    steps: int | None = None
    guidance_scale: float | None = None
    scheduler: str | None = None
    clip_skip: int | None = None
    lora_weight: float | None = None
    backend: Literal["sdxl", "sd15", "any"] = "any"


PROFILES: dict[ProfileId, GenerationProfile] = {
    "custom": GenerationProfile(
        profile_id="custom",
        display_name="Custom",
        description="Use steps, CFG, and scheduler from the request (Advanced panel).",
    ),
    "lightning_4": GenerationProfile(
        profile_id="lightning_4",
        display_name="Lightning 4-step",
        description="SDXL + Lightning LoRA: 4 steps, CFG 0, euler trailing.",
        steps=4,
        guidance_scale=0.0,
        scheduler="euler_trailing",
        clip_skip=2,
        lora_weight=1.0,
        backend="sdxl",
    ),
    "lightning_8": GenerationProfile(
        profile_id="lightning_8",
        display_name="Lightning 8-step",
        description="SDXL + Lightning LoRA: 8 steps, CFG 1, euler trailing.",
        steps=8,
        guidance_scale=1.0,
        scheduler="euler_trailing",
        clip_skip=2,
        lora_weight=1.0,
        backend="sdxl",
    ),
    "sdxl_fast": GenerationProfile(
        profile_id="sdxl_fast",
        display_name="SDXL Fast",
        description="12 steps, CFG 5 — standard SDXL base (no Lightning).",
        steps=12,
        guidance_scale=5.0,
        scheduler="dpm++2m_karras",
        clip_skip=2,
        backend="sdxl",
    ),
    "sdxl_balanced": GenerationProfile(
        profile_id="sdxl_balanced",
        display_name="SDXL Balanced",
        description="25 steps, CFG 6.",
        steps=25,
        guidance_scale=6.0,
        scheduler="dpm++2m_karras",
        clip_skip=2,
        backend="sdxl",
    ),
    "sdxl_quality": GenerationProfile(
        profile_id="sdxl_quality",
        display_name="SDXL Quality",
        description="35 steps, CFG 7.",
        steps=35,
        guidance_scale=7.0,
        scheduler="dpm++2m_karras",
        clip_skip=2,
        backend="sdxl",
    ),
    "sd15_standard": GenerationProfile(
        profile_id="sd15_standard",
        display_name="SD 1.5 Standard",
        description="Single-file checkpoint: 25 steps, CFG 7, 512px.",
        steps=25,
        guidance_scale=7.0,
        scheduler="dpm++2m_karras",
        clip_skip=1,
        backend="sd15",
    ),
}

_LEGACY_TIER_TO_PROFILE: dict[str, ProfileId] = {
    "fast": "sdxl_fast",
    "balanced": "sdxl_balanced",
    "quality": "sdxl_quality",
}


def _is_lightning_lora(name: str | None) -> bool:
    return bool(name and "lightning" in name.lower())


def resolve_profile_id(req: GenerateRequest) -> ProfileId | None:
    if req.generation_profile is not None:
        return req.generation_profile
    if _is_lightning_lora(req.lora_name):
        return "lightning_4"
    if req.quality_tier is not None:
        return _LEGACY_TIER_TO_PROFILE.get(req.quality_tier)
    return None


def list_profiles_payload() -> list[dict[str, Any]]:
    return [
        {
            "profile_id": p.profile_id,
            "display_name": p.display_name,
            "description": p.description,
            "steps": p.steps,
            "guidance_scale": p.guidance_scale,
            "scheduler": p.scheduler,
            "clip_skip": p.clip_skip,
            "lora_weight": p.lora_weight,
            "backend": p.backend,
        }
        for p in PROFILES.values()
    ]


def apply_generation_policy(req: GenerateRequest) -> tuple[GenerateRequest, str]:
    """Merge profile + model_id; return (effective_request, model_id)."""
    from checkpoint_utils import is_checkpoint_model_id, normalize_model_id

    model_id = normalize_model_id(req.model_id)
    profile_id = resolve_profile_id(req)

    if profile_id is None:
        return req, model_id

    if profile_id == "custom":
        return req, model_id

    profile = PROFILES[profile_id]
    updates: dict[str, Any] = {}
    for field in ("steps", "guidance_scale", "scheduler", "clip_skip", "lora_weight"):
        val = getattr(profile, field)
        if val is not None:
            updates[field] = val

    effective = req.model_copy(update=updates)
    return effective, model_id


def model_supports_lora(model_id: str) -> bool:
    from checkpoint_utils import is_checkpoint_model_id

    return not is_checkpoint_model_id(model_id)
