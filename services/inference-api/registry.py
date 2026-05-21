"""
Lazy-loaded inference engines keyed by model_id.
Architecture intent:
- Owns engine lifecycle (create, cache, future unload) — not HTTP or routing policy.
- main.py calls get_engine(model_id) after router.apply_quality_tier.
- MVP: only sdxl_base; one cached instance per id on this process.
"""



from __future__ import annotations

import logging
import threading

from device import resolve_torch_device
from engine import SDXLEngine

logger = logging.getLogger("sdxl_api")

# Stable ids echoed in API metadata; add new ids when weights + engine class exist.
SUPPORTED_MODEL_IDS = frozenset({"sdxl_base"})

class EngineRegistry:
    """
    Process-local cache of SDXLEngine instances.

    Thread-safe for concurrent get_engine calls; does not unload models yet.
    """

    def __init__(self, default_model_path: str, device: str | None = None) -> None:
        self._default_model_path = default_model_path
        self._device = device or resolve_torch_device()
        self._engines: dict[str, SDXLEngine] = {}
        self._lock = threading.Lock()

    def get_engine(self,model_id:str) -> SDXLEngine:
        if model_id not in SUPPORTED_MODEL_IDS:
            raise ValueError(f"Unsupported model_id: {model_id}")

        # Double-checked under lock: first request pays load_model(); rest reuse instance.
        with self._lock:
            if model_id not in self._engines:
                logger.info("loading engine model_id=%s", model_id)
                self._engines[model_id] = SDXLEngine(
                    model_path=self._default_model_path,
                    device=self._device,
                )
            return self._engines[model_id]


