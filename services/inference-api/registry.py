"""
Lazy-loaded engines keyed by model_id (catalog in model_catalog.py).

Only one heavy model resident in VRAM at a time (unload on switch).
"""

from __future__ import annotations

import logging
import threading
from typing import Union

from checkpoint_utils import is_checkpoint_model_id, resolve_checkpoint_path
from device import resolve_torch_device
from engine import SDXLEngine
from gguf_engine import GGUFEngine
from model_catalog import (
    CHAT_MODEL_IDS,
    IMAGE_MODEL_IDS,
    SUPPORTED_MODEL_IDS,
    get_chat_model,
    get_image_model,
)
from sd15_engine import SD15Engine

logger = logging.getLogger("sdxl_api")

EngineT = Union[SDXLEngine, SD15Engine, GGUFEngine]


class EngineRegistry:
    def __init__(self, default_model_path: str, device: str | None = None) -> None:
        self._default_model_path = default_model_path
        self._device = device or resolve_torch_device()
        self._engines: dict[str, EngineT] = {}
        self._lock = threading.Lock()

    def _unload(self, model_id: str) -> None:
        eng = self._engines.pop(model_id, None)
        if eng is None:
            return
        if hasattr(eng, "unload"):
            eng.unload()
        logger.info("unloaded model_id=%s", model_id)

    def _evict_all_except(self, keep_id: str) -> None:
        for mid in list(self._engines.keys()):
            if mid != keep_id:
                self._unload(mid)

    def get_engine(self, model_id: str) -> SDXLEngine | SD15Engine:
        if model_id not in IMAGE_MODEL_IDS and not is_checkpoint_model_id(model_id):
            raise ValueError(f"Not an image model_id: {model_id}")

        with self._lock:
            self._evict_all_except(model_id)
            if model_id not in self._engines:
                logger.info("loading image engine model_id=%s", model_id)
                if is_checkpoint_model_id(model_id):
                    path = str(resolve_checkpoint_path(model_id))
                    self._engines[model_id] = SD15Engine(
                        checkpoint_path=path,
                        device=self._device,
                    )
                else:
                    spec = get_image_model(model_id)
                    path = (
                        str(spec.local_path)
                        if spec.local_path.is_dir()
                        else self._default_model_path
                    )
                    self._engines[model_id] = SDXLEngine(
                        model_path=path,
                        device=self._device,
                    )
            eng = self._engines[model_id]
        if not isinstance(eng, (SDXLEngine, SD15Engine)):
            raise TypeError("engine type mismatch")
        return eng

    def get_chat_engine(self, model_id: str) -> GGUFEngine:
        if model_id not in CHAT_MODEL_IDS:
            raise ValueError(f"Not a chat model_id: {model_id}")
        spec = get_chat_model(model_id)
        with self._lock:
            self._evict_all_except(model_id)
            if model_id not in self._engines:
                logger.info("loading chat engine model_id=%s", model_id)
                self._engines[model_id] = GGUFEngine(spec=spec)
            eng = self._engines[model_id]
        if not isinstance(eng, GGUFEngine):
            raise TypeError("engine type mismatch")
        return eng
