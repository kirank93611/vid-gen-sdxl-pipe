"""
SDXL diffusers pipelines: text-to-image and inpaint on the resolved torch device.

Loaded lazily via EngineRegistry; supports cooperative cancel between diffusion steps.
"""

import torch
import threading
import io
import os
from typing import Callable, Any
from PIL import Image
from diffusers import (
    StableDiffusionXLPipeline,
    StableDiffusionXLInpaintPipeline,
    EulerDiscreteScheduler,
    DPMSolverMultistepScheduler,
)
from schemas import GenerateRequest
from device import resolve_torch_device
from lora_utils import resolve_lora_path


class GenerationCancelledError(Exception):
    """Cooperative stop: diffusion interrupted between steps (timeout / shutdown)."""


SchedulerFactory = Callable[[dict[str, Any]], Any]

SCHEDULERS: dict[str, SchedulerFactory] = {
    "dpm++2m_karras": lambda cfg: DPMSolverMultistepScheduler.from_config(
        cfg, use_karras_sigmas=True
    ),
    "euler": lambda cfg: EulerDiscreteScheduler.from_config(cfg),
    "euler_trailing": lambda cfg: EulerDiscreteScheduler.from_config(
        cfg, timestep_spacing="trailing"
    ),
}


class SDXLEngine:
    """
    Stateful engine for SDXL inference on cuda, mps, or cpu.
    """

    def __init__(self, model_path: str, device: str | None = None) -> None:
        self.model_path = model_path
        self.device = device or resolve_torch_device()
        self.pipeline: StableDiffusionXLPipeline | None = None
        self.inpaint_pipeline: StableDiffusionXLInpaintPipeline | None = None
        self._lock = threading.Lock()
        self._active_lora_key: tuple[str, float] | None = None
        self.load_model()

    def load_model(self) -> None:
        print(f"Loading SDXL from {self.model_path} on device={self.device}")

        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

        dtype = torch.float16 if self.device in ("cuda", "mps") else torch.float32

        self.pipeline = StableDiffusionXLPipeline.from_pretrained(
            self.model_path,
            torch_dtype=dtype,
            variant="fp16" if dtype == torch.float16 else None,
            use_safetensors=True,
            local_files_only=True,
        ).to(self.device)

        self.pipeline.scheduler = SCHEDULERS["dpm++2m_karras"](
            self.pipeline.scheduler.config
        )
        print(f"Model initialized on {self.device}.")

    def _clear_lora(self, pipeline: StableDiffusionXLPipeline | StableDiffusionXLInpaintPipeline) -> None:
        try:
            if hasattr(pipeline, "unfuse_lora"):
                pipeline.unfuse_lora()
        except Exception:
            pass
        try:
            pipeline.unload_lora_weights()
        except Exception:
            pass
        self._active_lora_key = None

    def _apply_lora(
        self,
        pipeline: StableDiffusionXLPipeline | StableDiffusionXLInpaintPipeline,
        req: GenerateRequest,
    ) -> None:
        if not req.lora_name:
            if self._active_lora_key is not None:
                self._clear_lora(pipeline)
            return

        key = (req.lora_name, req.lora_weight)
        if key == self._active_lora_key:
            return

        self._clear_lora(pipeline)
        path = resolve_lora_path(req.lora_name)
        pipeline.load_lora_weights(str(path.parent), weight_name=path.name)
        try:
            pipeline.fuse_lora(lora_scale=req.lora_weight)
        except Exception:
            adapters = pipeline.get_list_adapters() if hasattr(pipeline, "get_list_adapters") else {}
            names = list(adapters.keys()) if adapters else ["default_0"]
            pipeline.set_adapters(names, adapter_weights=[req.lora_weight])
        self._active_lora_key = key

    def unload(self) -> None:
        """Release GPU weights (registry calls this when switching to GGUF chat)."""
        with self._lock:
            self.pipeline = None
            self.inpaint_pipeline = None
            self._active_lora_key = None

    def generate(
        self,
        req: GenerateRequest,
        *,
        cancel_event: threading.Event | None = None,
    ) -> tuple[bytes, int]:
        if req.scheduler not in SCHEDULERS:
            raise ValueError(f"Unsupported scheduler: {req.scheduler}")

        seed = req.seed if req.seed is not None else torch.randint(0, 2**32 - 1, (1,)).item()
        generator = torch.Generator(device=self.device).manual_seed(seed)

        with self._lock:
            self._apply_lora(self.pipeline, req)
            self.pipeline.scheduler = SCHEDULERS[req.scheduler](
                self.pipeline.scheduler.config
            )
            self.pipeline.scheduler.set_timesteps(req.steps, device=self.device)

            original_layers = self.pipeline.text_encoder.config.num_hidden_layers
            self.pipeline.text_encoder.config.num_hidden_layers -= req.clip_skip - 1

            def _on_step_end(
                _pipe: StableDiffusionXLPipeline,
                _step_index: int,
                _timestep: int,
                callback_kwargs: dict[str, Any],
            ) -> dict[str, Any]:
                if cancel_event is not None and cancel_event.is_set():
                    raise GenerationCancelledError("cancelled")
                return callback_kwargs

            try:
                output = self.pipeline(
                    prompt=req.prompt,
                    negative_prompt=req.negative_prompt,
                    width=req.width,
                    height=req.height,
                    num_inference_steps=req.steps,
                    guidance_scale=req.guidance_scale,
                    generator=generator,
                    callback_on_step_end=_on_step_end if cancel_event is not None else None,
                ).images[0]
            except GenerationCancelledError:
                raise
            finally:
                self.pipeline.text_encoder.config.num_hidden_layers = original_layers

        buffer = io.BytesIO()
        output.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue(), seed

    def _ensure_inpaint_pipeline(self) -> StableDiffusionXLInpaintPipeline:
        if self.inpaint_pipeline is not None:
            return self.inpaint_pipeline

        dtype = torch.float16 if self.device in ("cuda", "mps") else torch.float32
        self.inpaint_pipeline = StableDiffusionXLInpaintPipeline.from_pretrained(
            self.model_path,
            torch_dtype=dtype,
            variant="fp16" if dtype == torch.float16 else None,
            use_safetensors=True,
            local_files_only=True,
        ).to(self.device)
        self.inpaint_pipeline.scheduler = SCHEDULERS["dpm++2m_karras"](
            self.inpaint_pipeline.scheduler.config
        )
        return self.inpaint_pipeline

    def inpaint(
        self,
        req: GenerateRequest,
        init_image: Image.Image,
        mask_image: Image.Image,
        *,
        strength: float = 0.85,
        cancel_event: threading.Event | None = None,
    ) -> tuple[bytes, int]:
        if req.scheduler not in SCHEDULERS:
            raise ValueError(f"Unsupported scheduler: {req.scheduler}")

        size = (req.width, req.height)
        if init_image.size != size:
            init_image = init_image.resize(size, Image.Resampling.LANCZOS)
        if mask_image.size != size:
            mask_image = mask_image.resize(size, Image.Resampling.LANCZOS)

        seed = req.seed if req.seed is not None else torch.randint(0, 2**32 - 1, (1,)).item()
        generator = torch.Generator(device=self.device).manual_seed(seed)
        pipeline = self._ensure_inpaint_pipeline()

        with self._lock:
            pipeline.scheduler = SCHEDULERS[req.scheduler](pipeline.scheduler.config)
            pipeline.scheduler.set_timesteps(req.steps, device=self.device)

            def _on_step_end(
                _pipe: StableDiffusionXLInpaintPipeline,
                _step_index: int,
                _timestep: int,
                callback_kwargs: dict[str, Any],
            ) -> dict[str, Any]:
                if cancel_event is not None and cancel_event.is_set():
                    raise GenerationCancelledError("cancelled")
                return callback_kwargs

            try:
                output = pipeline(
                    prompt=req.prompt,
                    negative_prompt=req.negative_prompt,
                    image=init_image,
                    mask_image=mask_image,
                    width=req.width,
                    height=req.height,
                    num_inference_steps=req.steps,
                    guidance_scale=req.guidance_scale,
                    strength=strength,
                    generator=generator,
                    callback_on_step_end=_on_step_end if cancel_event is not None else None,
                ).images[0]
            except GenerationCancelledError:
                raise

        buffer = io.BytesIO()
        output.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue(), seed
