"""Async wrapper for GGUF chat (executor + timeout)."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from gguf_engine import GGUFEngine
from registry import EngineRegistry
from schemas import ChatRequest

logger = logging.getLogger("sdxl_api")

_chat_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gguf-chat")


def _load_chat_sync(registry: EngineRegistry, model_id: str) -> dict[str, str]:
    engine: GGUFEngine = registry.get_chat_engine(model_id)
    engine.load()
    return {"model_id": model_id, "status": "loaded"}


async def load_chat_model(
    model_id: str,
    *,
    registry: EngineRegistry,
    timeout_seconds: float,
) -> dict[str, str]:
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(_chat_executor, _load_chat_sync, registry, model_id),
        timeout=timeout_seconds,
    )


async def chat_completion(
    payload: ChatRequest,
    *,
    registry: EngineRegistry,
    timeout_seconds: float,
) -> tuple[str, dict]:
    engine: GGUFEngine = registry.get_chat_engine(payload.model_id)

    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(_chat_executor, engine.complete, payload),
        timeout=timeout_seconds,
    )
