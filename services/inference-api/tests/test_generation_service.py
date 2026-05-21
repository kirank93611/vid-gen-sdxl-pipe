"""Unit tests for cooperative GPU cancel on generation timeout."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import engine as engine_module
from engine import GenerationCancelledError
from generation_service import generate_image_bytes
from schemas import GenerateRequest


def _fake_load_model(self: Any) -> None:
    self.pipeline = object()


class _CancelAwareEngine:
    def generate(
        self,
        req: GenerateRequest,
        *,
        cancel_event: threading.Event | None = None,
    ) -> tuple[bytes, int]:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelledError("cancelled")
            time.sleep(0.02)


class _Registry:
    def get_engine(self, _model_id: str) -> _CancelAwareEngine:
        return _CancelAwareEngine()


class GenerationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_triggers_cancel_and_drains_executor(self) -> None:
        with mock.patch.object(engine_module.SDXLEngine, "load_model", _fake_load_model):
            payload = GenerateRequest(prompt="cancel-test", quality_tier="fast")
            started = time.perf_counter()
            with self.assertRaises(asyncio.TimeoutError):
                await generate_image_bytes(
                    payload,
                    registry=_Registry(),  # type: ignore[arg-type]
                    timeout_seconds=0.1,
                    cancel_grace_seconds=5.0,
                )
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 2.0)

            # Second call should start promptly if the executor was drained.
            t0 = time.perf_counter()
            with self.assertRaises(asyncio.TimeoutError):
                await generate_image_bytes(
                    payload,
                    registry=_Registry(),  # type: ignore[arg-type]
                    timeout_seconds=0.05,
                    cancel_grace_seconds=5.0,
                )
            self.assertLess(time.perf_counter() - t0, 2.0)


if __name__ == "__main__":
    unittest.main()
