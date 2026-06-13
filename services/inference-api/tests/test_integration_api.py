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

# Ensure inference-api package root is importable regardless of current working directory.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import engine as engine_module


def _fake_load_model(self: Any) -> None:
    self.pipeline = object()


def _fake_generate_ok(self: Any, req: Any, **_: Any) -> tuple[bytes, int]:
    # Small deterministic payload to validate Base64 decode path.
    return b"fake-jpeg-bytes", 12345


def _fake_inpaint_ok(self: Any, req: Any, **_kwargs: Any) -> tuple[bytes, int]:
    return b"fake-inpaint-bytes", 54321


with mock.patch.object(engine_module.SDXLEngine, "load_model", _fake_load_model), mock.patch.object(
    engine_module.SDXLEngine, "generate", _fake_generate_ok
):
    main = importlib.import_module("main")


class IntegrationAPITests(unittest.IsolatedAsyncioTestCase):
    API_HEADERS = {"X-API-Key": "test-api-key"}

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
        
        class _FakeEngine:
            def generate(self, req: Any, **kwargs: Any) -> tuple[bytes, int]:
                return _fake_generate_ok(self, req, **kwargs)

            def inpaint(self, req: Any, init_image: Any, mask_image: Any, **kwargs: Any) -> tuple[bytes, int]:
                return _fake_inpaint_ok(self, req, **kwargs)

        main.registry.get_engine = lambda _model_id: _FakeEngine()

        import jobs as jobs_module

        jobs_module.reset_store_for_tests()
        import rate_limit as rate_limit_module

        rate_limit_module.reset_for_tests()
        import api_config

        api_config.EXPECTED_API_KEY = self.API_HEADERS["X-API-Key"]
        main.EXPECTED_API_KEY = self.API_HEADERS["X-API-Key"]

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_health_endpoint(self) -> None:
        resp = await self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "healthy")
        import device as device_module

        self.assertEqual(body["engine"], device_module.get_runtime_device())

    async def test_generate_success_returns_base64_payload_and_metrics(self) -> None:
        resp = await self.client.post("/generate", json={"prompt": "test"}, headers=self.API_HEADERS)
        self.assertEqual(resp.status_code, 200)

        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["metadata"]["seed"], 12345)
        self.assertEqual(base64.b64decode(body["image_base64"]), b"fake-jpeg-bytes")

        metrics = (await self.client.get("/metrics", headers=self.API_HEADERS)).json()
        self.assertEqual(metrics["generate_requests_total"], 1)
        self.assertEqual(metrics["generate_accepted_total"], 1)
        self.assertEqual(metrics["generate_rejected_total"], 0)
        self.assertEqual(metrics["generate_success_total"], 1)
        self.assertEqual(metrics["generate_inflight"], 0)

    async def test_generate_quality_tier_balanced_sets_metadata(self) -> None:
        resp = await self.client.post(
            "/generate",
            json={"prompt": "tier test", "quality_tier": "balanced"},
            headers=self.API_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        meta = resp.json()["metadata"]
        self.assertEqual(meta["steps"], 25)
        self.assertEqual(meta["guidance_scale"], 6.0)
        self.assertEqual(meta["model_id"], "sdxl_base")
        self.assertEqual(meta["quality_tier"], "balanced")

    async def test_generate_backpressure_returns_429_and_retry_after(self) -> None:
        def _slow_generate(self: Any, req: Any) -> tuple[bytes, int]:
            time.sleep(0.25)
            return b"slow-bytes", 777
        class _Engine:
            def generate(self, req: Any, **kwargs: Any) -> tuple[bytes, int]:
                return _slow_generate(self, req)

        main.registry.get_engine = lambda _model_id: _Engine()
        req1 = self.client.post("/generate", json={"prompt": "one"}, headers=self.API_HEADERS)
        req2 = self.client.post("/generate", json={"prompt": "two"}, headers=self.API_HEADERS)
        r1, r2 = await asyncio.gather(req1, req2)

        responses = sorted([r1, r2], key=lambda r: r.status_code)
        self.assertEqual([responses[0].status_code, responses[1].status_code], [200, 429])

        reject = responses[1]
        self.assertEqual(reject.json()["error_code"], "capacity_reached")
        self.assertEqual(reject.headers.get("Retry-After"), "5")
        self.assertIsNotNone(reject.headers.get("X-Request-ID"))

        metrics = (await self.client.get("/metrics", headers=self.API_HEADERS)).json()
        self.assertEqual(metrics["generate_requests_total"], 2)
        self.assertEqual(metrics["generate_accepted_total"], 1)
        self.assertEqual(metrics["generate_rejected_total"], 1)
        self.assertEqual(metrics["generate_inflight"], 0)

    async def test_unhandled_engine_error_returns_500_with_request_id(self) -> None:
        def _raise_generate(self: Any, req: Any) -> tuple[bytes, int]:
            raise RuntimeError("boom")

        class _Engine:
            def generate(self, req: Any, **kwargs: Any) -> tuple[bytes, int]:
                return _raise_generate(self, req)  # or call _raise_generate / _very_slow_generate inside

        main.registry.get_engine = lambda _model_id: _Engine()
        resp = await self.client.post("/generate", json={"prompt": "fail"}, headers=self.API_HEADERS)

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
        class _Engine:
            def generate(self, req: Any, **kwargs: Any) -> tuple[bytes, int]:
                return _raise_generate(self, req)  # or call _raise_generate / _very_slow_generate inside

        main.registry.get_engine = lambda _model_id: _Engine()
        try:
            resp = await self.client.post("/generate", json={"prompt": "fail"}, headers=self.API_HEADERS)
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
        class _Engine:
            def generate(self, req: Any, **kwargs: Any) -> tuple[bytes, int]:
                return _raise_generate(self, req)  # or call _raise_generate / _very_slow_generate inside

        main.registry.get_engine = lambda _model_id: _Engine()
        try:
            resp = await self.client.post("/generate", json={"prompt":"fail"}, headers=self.API_HEADERS)
        finally:
            main.APP_ENV = old_env
        
        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "internal_error")
        self.assertNotIn("details", body)
        self.assertIn("request_id", body)

    async def test_generate_timeout_returns_504_and_updates_metrics(self) -> None:
        from engine import GenerationCancelledError

        def _slow_until_cancel(self: Any, req: Any, cancel_event: Any = None) -> tuple[bytes, int]:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise GenerationCancelledError("cancelled")
                time.sleep(0.02)

        old_timeout = main.GENERATION_TIMEOUT_SECONDS
        main.GENERATION_TIMEOUT_SECONDS = 0.1

        class _Engine:
            def generate(self, req: Any, cancel_event: Any = None) -> tuple[bytes, int]:
                return _slow_until_cancel(self, req, cancel_event)

        main.registry.get_engine = lambda _model_id: _Engine()
        try:
            started = time.perf_counter()
            resp = await self.client.post("/generate", json={"prompt": "timeout"}, headers=self.API_HEADERS)
            elapsed = time.perf_counter() - started
        finally:
            main.GENERATION_TIMEOUT_SECONDS = old_timeout

        self.assertLess(elapsed, 2.0, "should stop soon after cancel, not run full diffusion")
        self.assertEqual(resp.status_code, 504)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "generation_timeout")
        self.assertEqual(body["message"], "Generation timed out")
        self.assertIn("request_id", body)
        self.assertIsNotNone(resp.headers.get("X-Request-ID"))

        metrics = (await self.client.get("/metrics", headers=self.API_HEADERS)).json()
        self.assertEqual(metrics["generate_timeout_total"], 1)
        self.assertEqual(metrics["generate_inflight"], 0)

    async def test_generate_rejects_invalid_lora_name(self) -> None:
        resp = await self.client.post(
            "/generate",
            json={"prompt": "test", "lora_name": "../etc/passwd"},
            headers=self.API_HEADERS,
        )
        self.assertEqual(resp.status_code, 422)

    async def test_generate_lora_not_on_disk_returns_400(self) -> None:
        resp = await self.client.post(
            "/generate",
            json={"prompt": "test", "lora_name": "missing_lora_file"},
            headers=self.API_HEADERS,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error_code"], "lora_not_found")

    async def test_generate_lora_backend_mismatch_returns_400(self) -> None:
        with mock.patch(
            "main.resolve_lora_path",
            return_value=Path("/tmp/fake-lora.safetensors"),
        ):
            resp = await self.client.post(
                "/generate",
                json={"prompt": "test", "lora_name": "DR34ML4Y_LTXXX_V2"},
                headers=self.API_HEADERS,
            )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error_code"], "lora_backend_mismatch")

    async def test_generate_ltx_lora_with_ltx_base_mocked(self) -> None:
        class _LtxEngine:
            media_type = "video/mp4"

            def generate(self, req: Any, **_: Any) -> tuple[bytes, bytes, int]:
                return b"mp4-bytes", b"poster-jpeg", 42

        with mock.patch.object(main.registry, "get_engine", return_value=_LtxEngine()), mock.patch(
            "ltx_engine.ltx_model_on_disk",
            return_value=True,
        ), mock.patch(
            "main.resolve_lora_path",
            return_value=Path("/tmp/fake-lora.safetensors"),
        ):
            resp = await self.client.post(
                "/generate",
                json={
                    "prompt": "test video",
                    "model_id": "ltx_video",
                    "lora_name": "DR34ML4Y_LTXXX_V2",
                    "generation_profile": "ltx_fast",
                },
                headers=self.API_HEADERS,
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertTrue(body.get("video_base64"))
        self.assertEqual(body["metadata"]["model_id"], "ltx_video")

    async def test_list_loras_endpoint(self) -> None:
        resp = await self.client.get("/loras")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("loras", resp.json())

    async def test_list_generation_profiles_endpoint(self) -> None:
        resp = await self.client.get("/generation-profiles")
        self.assertEqual(resp.status_code, 200)
        ids = {p["profile_id"] for p in resp.json()["profiles"]}
        self.assertIn("lightning_4", ids)
        self.assertIn("ltx_fast", ids)
        self.assertIn("custom", ids)

    async def test_generate_lightning_profile_metadata(self) -> None:
        resp = await self.client.post(
            "/generate",
            json={"prompt": "lightning", "generation_profile": "lightning_4"},
            headers=self.API_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        meta = resp.json()["metadata"]
        self.assertEqual(meta["steps"], 4)
        self.assertEqual(meta["guidance_scale"], 0.0)
        self.assertEqual(meta["scheduler"], "euler_trailing")

    async def test_generate_without_api_key_returns_401(self) -> None:
        resp = await self.client.post("/generate", json={"prompt": "test"})
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "unauthorized")
        self.assertIn("request_id", body)

    async def test_metrics_without_api_key_returns_401(self) -> None:
        resp = await self.client.get("/metrics")
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "unauthorized")
        self.assertIn("request_id", body)

    async def test_generate_rate_limited_returns_429(self) -> None:
        import api_config
        import rate_limit as rate_limit_module

        old_limit = api_config.RATE_LIMIT_REQUESTS
        try:
            api_config.RATE_LIMIT_REQUESTS = 1
            rate_limit_module.reset_for_tests()

            first = await self.client.post(
                "/generate", json={"prompt": "first"}, headers=self.API_HEADERS
            )
            second = await self.client.post(
                "/generate", json={"prompt": "second"}, headers=self.API_HEADERS
            )

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 429)

            body = second.json()
            self.assertEqual(body["status"], "error")
            self.assertEqual(body["error_code"], "rate_limited")
            self.assertIn("request_id", body)
            self.assertIsNotNone(second.headers.get("Retry-After"))
            self.assertIsNotNone(second.headers.get("X-Request-ID"))

        finally:
            api_config.RATE_LIMIT_REQUESTS = old_limit
            rate_limit_module.reset_for_tests()

    async def test_generate_rate_limit_is_per_key(self) -> None:
        import api_config
        import rate_limit as rate_limit_module

        old_limit = api_config.RATE_LIMIT_REQUESTS
        try:
            api_config.RATE_LIMIT_REQUESTS = 1
            rate_limit_module.reset_for_tests()

            key_a_headers = {"X-API-Key": "key-a"}
            key_b_headers = {"X-API-Key": "key-b"}
            api_config.EXPECTED_API_KEY = "key-a"
            main.EXPECTED_API_KEY = "key-a"

            r1 = await self.client.post(
                "/generate", json={"prompt": "a1"}, headers=key_a_headers
            )
            self.assertEqual(r1.status_code, 200)

            r2 = await self.client.post(
                "/generate", json={"prompt": "a2"}, headers=key_a_headers
            )
            self.assertEqual(r2.status_code, 429)
            self.assertEqual(r2.json()["error_code"], "rate_limited")

            api_config.EXPECTED_API_KEY = "key-b"
            main.EXPECTED_API_KEY = "key-b"
            r3 = await self.client.post(
                "/generate", json={"prompt": "b1"}, headers=key_b_headers
            )
            self.assertEqual(r3.status_code, 200)
        finally:
            api_config.EXPECTED_API_KEY = self.API_HEADERS["X-API-Key"]
            main.EXPECTED_API_KEY = self.API_HEADERS["X-API-Key"]
            api_config.RATE_LIMIT_REQUESTS = old_limit
            rate_limit_module.reset_for_tests()

    async def test_job_correction_converges_after_tier_bump(self) -> None:
        create = await self.client.post(
            "/jobs",
            json={
                "goal": {"realism": "high"},
                "prompt": "job test",
                "quality_tier": "fast",
                "max_iterations": 3,
            },
            headers=self.API_HEADERS,
        )
        self.assertEqual(create.status_code, 202)
        job_id = create.json()["job_id"]

        for _ in range(50):
            await asyncio.sleep(0.05)
            status = await self.client.get(f"/jobs/{job_id}", headers=self.API_HEADERS)
            self.assertEqual(status.status_code, 200)
            body = status.json()
            if body["status"] in ("converged", "failed", "error"):
                break
        else:
            self.fail("job did not finish in time")

        self.assertEqual(body["status"], "converged")
        self.assertGreaterEqual(len(body["iterations"]), 2)
        self.assertEqual(body["iterations"][0]["passed"], False)
        self.assertEqual(body["iterations"][-1]["passed"], True)
        self.assertIsNotNone(body.get("image_base64"))
        self.assertEqual(body.get("image_url"), f"/jobs/{job_id}/artifact")

    async def test_job_persisted_after_memory_cache_clear(self) -> None:
        """Simulates API restart: SQLite + files remain; RAM cache is empty."""
        create = await self.client.post(
            "/jobs",
            json={
                "goal": {"realism": "high"},
                "prompt": "persist test",
                "quality_tier": "fast",
                "max_iterations": 3,
            },
            headers=self.API_HEADERS,
        )
        self.assertEqual(create.status_code, 202)
        job_id = create.json()["job_id"]

        body: dict = {}
        for _ in range(50):
            await asyncio.sleep(0.05)
            status = await self.client.get(f"/jobs/{job_id}", headers=self.API_HEADERS)
            body = status.json()
            if body["status"] in ("converged", "failed", "error"):
                break
        else:
            self.fail("job did not finish in time")

        self.assertEqual(body["status"], "converged")

        import jobs as jobs_module

        jobs_module.clear_memory_cache_for_tests()

        reloaded = await self.client.get(f"/jobs/{job_id}", headers=self.API_HEADERS)
        self.assertEqual(reloaded.status_code, 200)
        reloaded_body = reloaded.json()
        self.assertEqual(reloaded_body["status"], "converged")
        self.assertEqual(reloaded_body.get("image_url"), f"/jobs/{job_id}/artifact")

        artifact = await self.client.get(
            f"/jobs/{job_id}/artifact",
            headers=self.API_HEADERS,
        )
        self.assertEqual(artifact.status_code, 200)
        self.assertEqual(artifact.content, b"fake-jpeg-bytes")

    async def test_job_with_clip_reference_converges_when_similarity_improves(self) -> None:
        import base64 as b64

        ref_b64 = b64.b64encode(b"reference-jpeg").decode("utf-8")
        call_count = {"n": 0}

        def _clip_side_effect(_ref: bytes, _out: bytes) -> float:
            call_count["n"] += 1
            return 0.92 if call_count["n"] >= 2 else 0.5

        with mock.patch("evaluator.clip_similarity", side_effect=_clip_side_effect):
            create = await self.client.post(
                "/jobs",
                json={
                    "goal": {"preserve_product": True, "product_similarity_min": 0.85},
                    "prompt": "product on table",
                    "quality_tier": "fast",
                    "max_iterations": 3,
                    "reference_image_base64": ref_b64,
                },
                headers=self.API_HEADERS,
            )
        self.assertEqual(create.status_code, 202)
        job_id = create.json()["job_id"]

        body: dict = {}
        for _ in range(50):
            await asyncio.sleep(0.05)
            status = await self.client.get(f"/jobs/{job_id}", headers=self.API_HEADERS)
            body = status.json()
            if body["status"] in ("converged", "failed", "error"):
                break

        self.assertEqual(body["status"], "converged")
        self.assertGreaterEqual(len(body["iterations"]), 2)
        self.assertIn("product_similarity_low", body["iterations"][0]["issues"])
        self.assertIsNotNone(body["iterations"][-1].get("clip_similarity"))

    async def test_inpaint_success_returns_base64(self) -> None:
        import base64 as b64
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (64, 64), color=(40, 40, 40)).save(buf, format="JPEG")
        tiny = b64.b64encode(buf.getvalue()).decode("utf-8")
        resp = await self.client.post(
            "/inpaint",
            json={
                "prompt": "refine product",
                "image_base64": tiny,
                "mask_base64": tiny,
                "quality_tier": "fast",
            },
            headers=self.API_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(b64.b64decode(body["image_base64"]), b"fake-inpaint-bytes")

    async def test_get_job_unknown_returns_404(self) -> None:
        resp = await self.client.get(
            "/jobs/00000000-0000-0000-0000-000000000000",
            headers=self.API_HEADERS,
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "job_not_found")

    async def test_chat_success_when_gguf_present(self) -> None:
        class _FakeChatEngine:
            def complete(self, req: Any) -> tuple[str, dict[str, str]]:
                return "Hello from dolphin", {"model_id": "dolphin_mixtral_8x7b"}

        main.registry.get_chat_engine = lambda _mid: _FakeChatEngine()

        fake_spec = mock.Mock()
        fake_spec.is_on_disk.return_value = True
        with mock.patch("main.get_chat_model", return_value=fake_spec):
            resp = await self.client.post(
                "/chat",
                json={
                    "model_id": "dolphin_mixtral_8x7b",
                    "prompt": "Say hello in one word",
                    "max_tokens": 32,
                },
                headers=self.API_HEADERS,
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["text"], "Hello from dolphin")

    async def test_chat_returns_503_when_gguf_missing(self) -> None:
        fake_spec = mock.Mock()
        fake_spec.is_on_disk.return_value = False
        with mock.patch("main.get_chat_model", return_value=fake_spec):
            resp = await self.client.post(
                "/chat",
                json={"model_id": "dolphin_mixtral_8x7b", "prompt": "test"},
                headers=self.API_HEADERS,
            )
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["error_code"], "model_not_available")

    async def test_models_lists_catalog(self) -> None:
        resp = await self.client.get("/models")
        self.assertEqual(resp.status_code, 200)
        ids = {m["model_id"] for m in resp.json()["models"]}
        self.assertIn("sdxl_base", ids)
        self.assertIn("dolphin_mixtral_8x7b", ids)
        self.assertIn("tiefighter_20b", ids)

    async def test_load_chat_model_success(self) -> None:
        class _FakeChatEngine:
            def load(self) -> None:
                return None

        main.registry.get_chat_engine = lambda _mid: _FakeChatEngine()

        fake_spec = mock.Mock()
        fake_spec.is_on_disk.return_value = True
        with mock.patch("main.get_chat_model", return_value=fake_spec):
            resp = await self.client.post(
                "/models/dolphin_mixtral_8x7b/load",
                headers=self.API_HEADERS,
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")

    async def test_load_chat_model_503_when_missing(self) -> None:
        fake_spec = mock.Mock()
        fake_spec.is_on_disk.return_value = False
        with mock.patch("main.get_chat_model", return_value=fake_spec):
            resp = await self.client.post(
                "/models/dolphin_mixtral_8x7b/load",
                headers=self.API_HEADERS,
            )
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["error_code"], "model_not_available")


if __name__ == "__main__":
    unittest.main()
