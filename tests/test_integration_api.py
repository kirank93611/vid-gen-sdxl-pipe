import asyncio
import base64
import importlib
import logging
import sys
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import httpx

# Ensure project root is importable regardless of current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import engine as engine_module


def _fake_load_model(self: Any) -> None:
    self.pipeline = object()


def _fake_generate_ok(self: Any, req: Any) -> tuple[bytes, int]:
    # Small deterministic payload to validate Base64 decode path.
    return b"fake-jpeg-bytes", 12345


with mock.patch.object(engine_module.SDXLEngine, "load_model", _fake_load_model), mock.patch.object(
    engine_module.SDXLEngine, "generate", _fake_generate_ok
):
    main = importlib.import_module("main")


class IntegrationAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

        self.transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://test")

        # Reset runtime state to keep tests isolated and deterministic.
        with main._metrics_lock:
            for key in main._metrics:
                main._metrics[key] = 0.0 if isinstance(main._metrics[key], float) else 0
        main._generate_semaphore = threading.Semaphore(main.MAX_INFLIGHT_GENERATIONS)
        main.engine.generate = _fake_generate_ok.__get__(main.engine, type(main.engine))

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_health_endpoint(self) -> None:
        resp = await self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "healthy")
        self.assertEqual(body["engine"], "mps")

    async def test_generate_success_returns_base64_payload_and_metrics(self) -> None:
        resp = await self.client.post("/generate", json={"prompt": "test"})
        self.assertEqual(resp.status_code, 200)

        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["metadata"]["seed"], 12345)
        self.assertEqual(base64.b64decode(body["image_base64"]), b"fake-jpeg-bytes")

        metrics = (await self.client.get("/metrics")).json()
        self.assertEqual(metrics["generate_requests_total"], 1)
        self.assertEqual(metrics["generate_accepted_total"], 1)
        self.assertEqual(metrics["generate_rejected_total"], 0)
        self.assertEqual(metrics["generate_success_total"], 1)
        self.assertEqual(metrics["generate_inflight"], 0)

    async def test_generate_backpressure_returns_429_and_retry_after(self) -> None:
        def _slow_generate(self: Any, req: Any) -> tuple[bytes, int]:
            time.sleep(0.25)
            return b"slow-bytes", 777

        main.engine.generate = _slow_generate.__get__(main.engine, type(main.engine))
        req1 = self.client.post("/generate", json={"prompt": "one"})
        req2 = self.client.post("/generate", json={"prompt": "two"})
        r1, r2 = await asyncio.gather(req1, req2)

        responses = sorted([r1, r2], key=lambda r: r.status_code)
        self.assertEqual([responses[0].status_code, responses[1].status_code], [200, 429])

        reject = responses[1]
        self.assertEqual(reject.json()["error_code"], "capacity_reached")
        self.assertEqual(reject.headers.get("Retry-After"), "5")
        self.assertIsNotNone(reject.headers.get("X-Request-ID"))

        metrics = (await self.client.get("/metrics")).json()
        self.assertEqual(metrics["generate_requests_total"], 2)
        self.assertEqual(metrics["generate_accepted_total"], 1)
        self.assertEqual(metrics["generate_rejected_total"], 1)
        self.assertEqual(metrics["generate_inflight"], 0)

    async def test_unhandled_engine_error_returns_500_with_request_id(self) -> None:
        def _raise_generate(self: Any, req: Any) -> tuple[bytes, int]:
            raise RuntimeError("boom")

        main.engine.generate = _raise_generate.__get__(main.engine, type(main.engine))
        resp = await self.client.post("/generate", json={"prompt": "fail"})

        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertIn("request_id", body)
        self.assertIsNotNone(resp.headers.get("X-Request-ID"))

    async def test_500_dev_includes_details(self) -> None:
        def _raise_generate(self: Any, req: Any) -> tuple[bytes, int]:
            raise RuntimeError("boom-dev")
        
        old_env = main.APP_ENV
        main.APP_ENV = "dev"
        main.engine.generate = _raise_generate.__get__(main.engine, type(main.engine))
        try:
            resp = await self.client.post("/generate", json={"prompt": "fail"})
        finally:
            main.APP_ENV = old_env

        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "internal_error")
        self.assertIn("details", body)
        self.assertIn("boom-dev", body["details"])
        self.assertIn("request_id", body)

    async def test_500_prod_hides_details(self) -> None:
        def _raise_generate(self: Any, req: Any) -> tuple[bytes, int]:
            raise RuntimeError("boom-prod")
        
        old_env = main.APP_ENV
        main.APP_ENV = "prod"
        main.engine.generate = _raise_generate.__get__(main.engine, type(main.engine))
        try:
            resp = await self.client.post("/generate", json={"prompt":"fail"})
        finally:
            main.APP_ENV = old_env
        
        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "internal_error")
        self.assertNotIn("details", body)
        self.assertIn("request_id", body)

    async def test_generate_timeout_returns_504_and_updates_metrics(self) -> None:
        def _very_slow_generate(self: Any, req: Any) -> tuple[bytes, int]:
            time.sleep(1.5)
            return b"late-bytes", 999

        old_timeout = main.GENERATION_TIMEOUT_SECONDS
        main.GENERATION_TIMEOUT_SECONDS = 0.1
        main.engine.generate = _very_slow_generate.__get__(main.engine, type(main.engine))
        try:
            resp = await self.client.post("/generate", json={"prompt": "timeout"})
        finally:
            main.GENERATION_TIMEOUT_SECONDS = old_timeout

        self.assertEqual(resp.status_code, 504)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "generation_timeout")
        self.assertEqual(body["message"], "Generation timed out")
        self.assertIn("request_id", body)
        self.assertIsNotNone(resp.headers.get("X-Request-ID"))

        metrics = (await self.client.get("/metrics")).json()
        self.assertEqual(metrics["generate_timeout_total"], 1)
        self.assertEqual(metrics["generate_inflight"], 0)



if __name__ == "__main__":
    unittest.main()
