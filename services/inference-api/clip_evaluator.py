"""CLIP image–image similarity for reference-based evaluation (lazy-loaded)."""

from __future__ import annotations

import io
import logging
import os
import threading
from typing import Any

logger = logging.getLogger("sdxl_api")

_clip_lock = threading.Lock()
_clip_model: Any = None
_clip_processor: Any = None
_clip_device: str | None = None

_DEFAULT_MODEL = os.getenv("CLIP_MODEL_ID", "openai/clip-vit-base-patch32")
_DEFAULT_THRESHOLD = float(os.getenv("PRODUCT_SIMILARITY_MIN", "0.85"))


def default_similarity_threshold(goal_threshold: float | None) -> float:
    if goal_threshold is not None:
        return goal_threshold
    return _DEFAULT_THRESHOLD


def _load_clip() -> tuple[Any, Any, str]:
    global _clip_model, _clip_processor, _clip_device
    with _clip_lock:
        if _clip_model is not None:
            return _clip_model, _clip_processor, _clip_device  # type: ignore[return-value]

        import torch
        from transformers import CLIPModel, CLIPProcessor

        device = os.getenv("CLIP_DEVICE", "cpu")
        logger.info("loading CLIP model_id=%s device=%s", _DEFAULT_MODEL, device)
        processor = CLIPProcessor.from_pretrained(_DEFAULT_MODEL)
        model = CLIPModel.from_pretrained(_DEFAULT_MODEL).to(device)
        model.eval()
        _clip_model = model
        _clip_processor = processor
        _clip_device = device
        return model, processor, device


def clip_similarity(reference_jpeg: bytes, output_jpeg: bytes) -> float:
    """
    Cosine similarity between CLIP embeddings of two images (0–1 typical range).

    Raises on invalid image bytes or model load failure.
    """
    import torch
    from PIL import Image

    model, processor, device = _load_clip()
    ref_img = Image.open(io.BytesIO(reference_jpeg)).convert("RGB")
    out_img = Image.open(io.BytesIO(output_jpeg)).convert("RGB")

    inputs = processor(images=[ref_img, out_img], return_tensors="pt", padding=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        features = model.get_image_features(**inputs)
        features = features / features.norm(dim=-1, keepdim=True)
        similarity = (features[0] @ features[1]).item()

    # CLIP cosine is in [-1, 1]; map to [0, 1] for thresholds.
    return float(max(0.0, min(1.0, (similarity + 1.0) / 2.0)))
