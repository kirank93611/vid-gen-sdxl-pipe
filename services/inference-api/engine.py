import torch
import threading
import io
import os
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
    Handles MPS device management and request-scoped pipeline mutation.

    Architecture intent:
    - Keep all model/runtime concerns here (diffusers, scheduler, MPS).
    - Keep API concerns out of this class (no FastAPI Request/Response).
    - Expose a small surface: load model once, generate per request.
    """
    def __init__(self, model_path: str) -> None:
        # Local filesystem path to SDXL weights (no runtime downloading).
        self.model_path = model_path
        # Diffusers pipeline object; initialized in load_model().
        self.pipeline: StableDiffusionXLPipeline | None = None
        # Protects mutable pipeline state during concurrent requests.
        self._lock = threading.Lock()
        # Eager load at process startup so first request is not delayed.
        self.load_model()

    def load_model(self) -> None:
        """
        Initialize the SDXL pipeline on Apple Silicon (MPS).

        Side effects:
        - Sets offline Hugging Face env flags.
        - Allocates model weights on MPS device.
        - Sets a default scheduler.
        """
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

    def generate(self, req: GenerateRequest) -> tuple[bytes, int]:
        """
        Execute one image generation request on MPS.

        Args:
            req: Validated generation request from API schema.

        Returns:
            Tuple of:
            - raw JPEG bytes
            - seed used for deterministic reproducibility
        """
        # Guardrail: only allow known scheduler keys.
        if req.scheduler not in SCHEDULERS:
            raise ValueError(f"Unsupported scheduler: {req.scheduler}")

        # If caller did not provide a seed, create a random one.
        seed = req.seed if req.seed is not None else torch.randint(0, 2**32 - 1, (1,)).item()
        # Torch generator tied to MPS device for deterministic sampling.
        generator = torch.Generator(device="mps").manual_seed(seed)

        with self._lock:
            # Reconfigure pipeline for specific request context
            self.pipeline.scheduler = SCHEDULERS[req.scheduler](self.pipeline.scheduler.config)
            self.pipeline.scheduler.set_timesteps(req.steps, device="mps")

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
                ).images[0]
            finally:
                # Restore state for the next request in the pool
                self.pipeline.text_encoder.config.num_hidden_layers = original_layers

        # Buffer conversion for stateless response
        buffer = io.BytesIO()
        output.save(buffer, format="JPEG", quality=90)
        # Return bytes instead of file paths to keep API stateless.
        return buffer.getvalue(), seed
