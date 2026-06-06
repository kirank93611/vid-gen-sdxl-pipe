"""Capability manifest — derived from model_catalog."""

from __future__ import annotations

from typing import TypedDict

from model_catalog import list_capabilities as _list_capabilities


class ModelCapability(TypedDict):
    model_id: str
    supports: tuple[str, ...]


def list_capabilities() -> list[ModelCapability]:
    return _list_capabilities()  # type: ignore[return-value]


def model_supports(model_id: str, capability: str) -> bool:
    for entry in list_capabilities():
        if entry["model_id"] == model_id:
            return capability in entry["supports"]
    return False
