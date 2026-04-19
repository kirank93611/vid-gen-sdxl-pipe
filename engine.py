import torch
import threading
import io
import os
from pathlib import Path
from typing import Annotated, Callable, Any
from diffusers import (
    StableDiffusionXLPipeline, 
    EulerDiscreteScheduler, 
    DPMSolverMultistepScheduler
)
from schemas import GenerateRequest

# PEP 604 & 585 for clean configuration
SchedulerFactory = Callable[[dict[str, Any]], Any]

SCHEDULERS: dict[str, SchedulerFactory] = {
    "dpm++2m_karras": lambda cfg: DPMSolverMultistepScheduler.from_config(cfg, use_karras_sigmas=True),
    "euler":          lambda cfg: EulerDiscreteScheduler.from_config(cfg),
}

class SDXLEngine:
    """
    Stateful engine for SDXL-Lightning inference.
    Handles MPS device management and LoRA lifecycle.
    """
    def __init__(self, model_path: str) -> None:
        self.model_path = model_path
        self.pipeline: StableDiffusionXLPipeline | None = None
        self._loaded_lora: str | None = None
        self._lock = threading.Lock()
        self.load_model()

    def load_model(self) -> None:
        """Initializes the pipeline on Apple Silicon (MPS)."""
        print(f"Loading SDXL-Lightning from {self.model_path}")
        
        # Enforce offline mode to prevent network hangs during inference
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

        self.pipeline = StableDiffusionXLPipeline.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16,
            variant="fp16",
            use_safetensors=True,
            local_files_only=True,
        ).to("mps")

        # Set initial scheduler
        self.pipeline.scheduler = SCHEDULERS["dpm++2m_karras"](self.pipeline.scheduler.config)
        print("Model initialized on MPS.")

    def _manage_lora(self, lora_path: str | None) -> None:
        """Handles on-demand LoRA swapping to maintain stateless request flow."""
        if lora_path == self._loaded_lora:
            return

        if self._loaded_lora is not None:
            self.pipeline.unload_lora_weights()

        if lora_path:
            # Multi-tenancy support: load specific style adapter
            self.pipeline.load_lora_weights(lora_path)
        
        self._loaded_lora = lora_path

    def generate(self, req: GenerateRequest) -> tuple[bytes, int]:
        """
        Executes inference on MPS.
        Returns (raw_image_bytes, used_seed).
        """
        if req.scheduler not in SCHEDULERS:
            raise ValueError(f"Unsupported scheduler: {req.scheduler}")

        seed = req.seed if req.seed is not None else torch.randint(0, 2**32 - 1, (1,)).item()
        generator = torch.Generator(device="mps").manual_seed(seed)
        
        cross_attention_kwargs = {"scale": req.lora_scale} if req.lora_path else None

        with self._lock:
            # Reconfigure pipeline for specific request context
            self.pipeline.scheduler = SCHEDULERS[req.scheduler](self.pipeline.scheduler.config)
            self.pipeline.scheduler.set_timesteps(req.steps, device="mps")
            self._manage_lora(req.lora_path)

            # Apply Clip Skip for style control
            original_layers = self.pipeline.text_encoder.config.num_hidden_layers
            self.pipeline.text_encoder.config.num_hidden_layers -= (req.clip_skip - 1)

            try:
                # SDXL-Lightning optimization: 4 steps, low guidance
                output = self.pipeline(
                    prompt=req.prompt,
                    negative_prompt=req.negative_prompt,
                    width=req.width,
                    height=req.height,
                    num_inference_steps=req.steps,
                    guidance_scale=req.guidance_scale,
                    generator=generator,
                    cross_attention_kwargs=cross_attention_kwargs,
                ).images[0]
            finally:
                # Restore state for the next request in the pool
                self.pipeline.text_encoder.config.num_hidden_layers = original_layers

        # Buffer conversion for stateless response
        buffer = io.BytesIO()
        output.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue(), seed
