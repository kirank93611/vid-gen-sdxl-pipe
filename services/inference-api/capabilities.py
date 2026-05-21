"""Capability manifest: model-agnostic skills vs concrete model_id (adapter registry)."""

from __future__ import annotations

from typing import TypedDict


class ModelCapability(TypedDict):
    model_id: str
    supports: tuple[str, ...]


# Planner/policy use capability names; adapters map model_id → execution knobs.
CAPABILITIES: dict[str, ModelCapability] = {
    "sdxl_base": {
        "model_id": "sdxl_base",
        "supports": (
            "text_to_image",
            "quality_tier_routing",
            "inpainting",
        ),
    },
}


def list_capabilities() -> list[ModelCapability]:
    return list(CAPABILITIES.values())


def model_supports(model_id: str, capability: str) -> bool:
    entry = CAPABILITIES.get(model_id)
    if entry is None:
        return False
    return capability in entry["supports"]
