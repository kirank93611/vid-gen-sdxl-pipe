"""GGUF text LLMs via llama-cpp-python (CUDA). Specs from model_catalog."""

from __future__ import annotations

import logging
import threading
from typing import Any

from model_catalog import ChatModelSpec
from schemas import ChatRequest

logger = logging.getLogger("sdxl_api")


class GGUFEngine:
    def __init__(self, *, spec: ChatModelSpec) -> None:
        self.spec = spec
        self.gguf_path = str(spec.gguf_path())
        self._llm: Any = None
        self._lock = threading.Lock()

    def load(self) -> None:
        if self._llm is not None:
            return
        if not self.spec.is_on_disk():
            raise FileNotFoundError(f"GGUF not found: {self.gguf_path}")

        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python not installed. On GPU VM: "
                "CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python"
            ) from exc

        logger.info(
            "loading GGUF model_id=%s path=%s n_gpu_layers=%s n_ctx=%s",
            self.spec.model_id,
            self.gguf_path,
            self.spec.n_gpu_layers,
            self.spec.n_ctx,
        )
        try:
            self._llm = Llama(
                model_path=self.gguf_path,
                n_gpu_layers=self.spec.n_gpu_layers,
                n_ctx=self.spec.n_ctx,
                verbose=False,
            )
        except ValueError as exc:
            raise RuntimeError(
                f"GGUF load failed for {self.spec.model_id}. "
                f"Re-download: python scripts/download_gguf_model.py {self.spec.model_id}"
            ) from exc
        logger.info("GGUF ready model_id=%s", self.spec.model_id)

    def unload(self) -> None:
        with self._lock:
            self._llm = None

    def complete(self, req: ChatRequest) -> tuple[str, dict[str, Any]]:
        self.load()
        assert self._llm is not None

        messages: list[dict[str, str]] = []
        if req.system_prompt:
            messages.append({"role": "system", "content": req.system_prompt})
        messages.append({"role": "user", "content": req.prompt})

        with self._lock:
            out = self._llm.create_chat_completion(
                messages=messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                top_p=req.top_p,
            )

        choice = out["choices"][0]
        text = (choice.get("message") or {}).get("content") or choice.get("text") or ""
        usage = out.get("usage") or {}
        meta = {
            "model_id": req.model_id,
            "display_name": self.spec.display_name,
            "completion_tokens": usage.get("completion_tokens"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "finish_reason": choice.get("finish_reason"),
        }
        return text.strip(), meta
