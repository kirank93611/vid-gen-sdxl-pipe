"""SD 1.5 text-to-image from a single .safetensors checkpoint (Comfy/Civitai style)."""

from __future__ import annotations

import io
import threading
from typing import Any, Callable

import torch
from PIL import Image
from diffusers import StableDiffusionPipeline
from transformers import CLIPTextModel, CLIPTokenizer

from device import resolve_torch_device
from engine import GenerationCancelledError, SCHEDULERS
from schemas import GenerateRequest

_SD15_REPO = "runwayml/stable-diffusion-v1-5"


class SD15Engine:
    """Loads one merged checkpoint; no LoRA / inpaint in MVP."""

    def __init__(self, checkpoint_path: str, device: str | None = None) -> None:
        self.checkpoint_path = checkpoint_path
        self.device = device or resolve_torch_device()
        self.pipeline: StableDiffusionPipeline | None = None
        self._lock = threading.Lock()
        self.load_model()

    def load_model(self) -> None:
        dtype = torch.float16 if self.device in ("cuda", "mps") else torch.float32
        print(f"Loading SD1.5 checkpoint {self.checkpoint_path} on {self.device}")

        # transformers >= 5.6 flattened CLIPTextModel (no .text_model). Pre-load
        # encoders from the SD1.5 hub so diffusers skips the broken inspect path.
        text_encoder = CLIPTextModel.from_pretrained(
            _SD15_REPO,
            subfolder="text_encoder",
            torch_dtype=dtype,
        )
        tokenizer = CLIPTokenizer.from_pretrained(_SD15_REPO, subfolder="tokenizer")

        try:
            self.pipeline = StableDiffusionPipeline.from_single_file(
                self.checkpoint_path,
                torch_dtype=dtype,
                use_safetensors=True,
                safety_checker=None,
                feature_extractor=None,
                requires_safety_checker=False,
                text_encoder=text_encoder,
                tokenizer=tokenizer,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load SD 1.5 checkpoint {self.checkpoint_path}: {exc}"
            ) from exc

        # diffusers may still attach a safety checker on first load; strip it for checkpoints.
        self.pipeline.safety_checker = None
        self.pipeline.feature_extractor = None
        self.pipeline = self.pipeline.to(self.device)
        self.pipeline.scheduler = SCHEDULERS["dpm++2m_karras"](
            self.pipeline.scheduler.config
        )
        print(f"SD1.5 checkpoint ready on {self.device}.")

    def unload(self) -> None:
        with self._lock:
            self.pipeline = None

    def generate(
        self,
        req: GenerateRequest,
        *,
        cancel_event: threading.Event | None = None,
    ) -> tuple[bytes, int]:
        if req.scheduler not in SCHEDULERS:
            raise ValueError(f"Unsupported scheduler: {req.scheduler}")

        seed = (
            req.seed
            if req.seed is not None
            else torch.randint(0, 2**32 - 1, (1,)).item()
        )
        generator = torch.Generator(device=self.device).manual_seed(seed)

        with self._lock:
            assert self.pipeline is not None
            self.pipeline.scheduler = SCHEDULERS[req.scheduler](
                self.pipeline.scheduler.config
            )
            self.pipeline.scheduler.set_timesteps(req.steps, device=self.device)

            def _on_step_end(
                _pipe: StableDiffusionPipeline,
                _step_index: int,
                _timestep: int,
                callback_kwargs: dict[str, Any],
            ) -> dict[str, Any]:
                if cancel_event is not None and cancel_event.is_set():
                    raise GenerationCancelledError("cancelled")
                return callback_kwargs

            output = self.pipeline(
                prompt=req.prompt,
                negative_prompt=req.negative_prompt,
                width=req.width,
                height=req.height,
                num_inference_steps=req.steps,
                guidance_scale=req.guidance_scale,
                generator=generator,
                callback_on_step_end=_on_step_end if cancel_event else None,
            ).images[0]

        buffer = io.BytesIO()
        output.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue(), seed
