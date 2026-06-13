"""Shared async generation path for /generate and correction jobs."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import TYPE_CHECKING

import io

from PIL import Image

from engine import GenerationCancelledError
from schemas import GenerateRequest
from sdxl_adapter import effective_request

if TYPE_CHECKING:
    from registry import EngineRegistry

logger = logging.getLogger("sdxl_api")

# Single worker: one diffusion run at a time; timeouts drain this queue before releasing capacity.
_GPU_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sdxl-gpu")
GENERATION_CANCEL_GRACE_SECONDS = float(os.getenv("GENERATION_CANCEL_GRACE_SECONDS", "120"))


def _run_generate(
    engine: object,
    payload: GenerateRequest,
    cancel_event: threading.Event,
) -> tuple[bytes, bytes | None, int, GenerateRequest, str]:
    effective, model_id = effective_request(payload)
    raw = engine.generate(effective, cancel_event=cancel_event)  # type: ignore[attr-defined]
    if len(raw) == 3:
        video_bytes, poster_bytes, used_seed = raw
        return poster_bytes, video_bytes, used_seed, effective, model_id
    image_bytes, used_seed = raw
    return image_bytes, None, used_seed, effective, model_id


async def generate_image_bytes(
    payload: GenerateRequest,
    *,
    registry: EngineRegistry,
    timeout_seconds: float,
    cancel_grace_seconds: float | None = None,
) -> tuple[bytes, bytes | None, int, GenerateRequest, str]:
    """
    Run one inference step. Raises asyncio.TimeoutError on wall-clock timeout.

    On timeout, sets a cooperative cancel flag, waits for the GPU thread to exit
    (so MPS is not left busy for the next request), then re-raises TimeoutError.
    """
    effective, model_id = effective_request(payload)
    engine = registry.get_engine(model_id)
    cancel_event = threading.Event()
    grace = (
        cancel_grace_seconds
        if cancel_grace_seconds is not None
        else GENERATION_CANCEL_GRACE_SECONDS
    )

    loop = asyncio.get_running_loop()
    # concurrent.futures.Future so shutdown can use .result(timeout=...) after cancel.
    cf_future = _GPU_EXECUTOR.submit(
        _run_generate,
        engine,
        payload,
        cancel_event,
    )

    try:
        return await asyncio.wait_for(
            asyncio.wrap_future(cf_future),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        cancel_event.set()
        logger.warning(
            "Generation wall-clock timeout (%.0fs); cooperative cancel requested",
            timeout_seconds,
        )
        try:
            await loop.run_in_executor(
                None,
                lambda: cf_future.result(timeout=grace),
            )
        except GenerationCancelledError:
            pass
        except FuturesTimeoutError:
            logger.error(
                "GPU thread did not stop within %.0fs after cancel", grace
            )
        except Exception:
            logger.exception("GPU thread failed during post-timeout shutdown")
        raise


def _run_inpaint(
    engine: object,
    effective: GenerateRequest,
    init_image_bytes: bytes,
    mask_bytes: bytes,
    strength: float,
    cancel_event: threading.Event,
) -> tuple[bytes, int]:
    init_image = Image.open(io.BytesIO(init_image_bytes)).convert("RGB")
    mask_image = Image.open(io.BytesIO(mask_bytes)).convert("L")
    image_bytes, used_seed = engine.inpaint(  # type: ignore[attr-defined]
        effective,
        init_image,
        mask_image,
        strength=strength,
        cancel_event=cancel_event,
    )
    return image_bytes, used_seed


async def inpaint_image_bytes(
    payload: GenerateRequest,
    *,
    init_image_bytes: bytes,
    mask_bytes: bytes,
    strength: float,
    registry: EngineRegistry,
    timeout_seconds: float,
    cancel_grace_seconds: float | None = None,
) -> tuple[bytes, int, GenerateRequest, str]:
    """Run SDXL inpaint on the single GPU worker (same cancel/timeout semantics as generate)."""
    effective, model_id = effective_request(payload)
    engine = registry.get_engine(model_id)
    cancel_event = threading.Event()
    grace = (
        cancel_grace_seconds
        if cancel_grace_seconds is not None
        else GENERATION_CANCEL_GRACE_SECONDS
    )
    loop = asyncio.get_running_loop()
    cf_future = _GPU_EXECUTOR.submit(
        _run_inpaint,
        engine,
        effective,
        init_image_bytes,
        mask_bytes,
        strength,
        cancel_event,
    )
    try:
        image_bytes, used_seed = await asyncio.wait_for(
            asyncio.wrap_future(cf_future),
            timeout=timeout_seconds,
        )
        return image_bytes, used_seed, effective, model_id
    except asyncio.TimeoutError:
        cancel_event.set()
        logger.warning(
            "Inpaint wall-clock timeout (%.0fs); cooperative cancel requested",
            timeout_seconds,
        )
        try:
            await loop.run_in_executor(
                None,
                lambda: cf_future.result(timeout=grace),
            )
        except GenerationCancelledError:
            pass
        except FuturesTimeoutError:
            logger.error(
                "GPU thread did not stop within %.0fs after inpaint cancel", grace
            )
        except Exception:
            logger.exception("GPU thread failed during post-inpaint-timeout shutdown")
        raise
