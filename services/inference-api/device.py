"""Resolve torch device from DEVICE env (cuda / mps / cpu)."""

from __future__ import annotations

import os

import torch

_RUNTIME_DEVICE: str | None = None


def resolve_torch_device() -> str:
    """
    Pick inference device once per process.

    DEVICE env overrides auto-detect (cuda if available, else mps, else cpu).
    """
    global _RUNTIME_DEVICE
    if _RUNTIME_DEVICE is not None:
        return _RUNTIME_DEVICE

    requested = os.getenv("DEVICE", "").strip().lower()
    if requested:
        if requested not in ("cuda", "mps", "cpu"):
            raise ValueError(f"Unsupported DEVICE={requested!r}; use cuda, mps, or cpu")
        if requested == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("DEVICE=cuda but torch.cuda.is_available() is False")
        if requested == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("DEVICE=mps but MPS is not available")
        _RUNTIME_DEVICE = requested
        return _RUNTIME_DEVICE

    if torch.cuda.is_available():
        _RUNTIME_DEVICE = "cuda"
    elif torch.backends.mps.is_available():
        _RUNTIME_DEVICE = "mps"
    else:
        _RUNTIME_DEVICE = "cpu"
    return _RUNTIME_DEVICE


def get_runtime_device() -> str:
    """Return resolved device (calls resolve_torch_device on first use)."""
    return resolve_torch_device()
