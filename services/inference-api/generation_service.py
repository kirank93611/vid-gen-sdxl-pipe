"""Shared async generation path for /generate and correction jobs."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from schemas import GenerateRequest
from sdxl_adapter import effective_request

if TYPE_CHECKING:
    from registry import EngineRegistry


async def generate_image_bytes(
    payload: GenerateRequest,
    *,
    registry: EngineRegistry,
    timeout_seconds: float,
) -> tuple[bytes, int, GenerateRequest, str]:
    """
    Run one inference step. Raises asyncio.TimeoutError on wall-clock timeout.
    """
    effective, model_id = effective_request(payload)
    engine = registry.get_engine(model_id)
    loop = asyncio.get_running_loop()
    image_bytes, used_seed = await asyncio.wait_for(
        loop.run_in_executor(None, engine.generate, effective),
        timeout=timeout_seconds,
    )
    return image_bytes, used_seed, effective, model_id
