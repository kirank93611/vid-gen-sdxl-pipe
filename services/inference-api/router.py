"""Generation policy — delegates to modular profiles (generation_profiles.py)."""

from __future__ import annotations

from generation_profiles import (
    DEFAULT_MODEL_ID,
    apply_generation_policy,
    list_profiles_payload,
    model_supports_lora,
)

# Backward-compatible alias used in tests/docs.
apply_quality_tier = apply_generation_policy

__all__ = [
    "DEFAULT_MODEL_ID",
    "apply_generation_policy",
    "apply_quality_tier",
    "list_profiles_payload",
    "model_supports_lora",
]
