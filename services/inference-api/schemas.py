"""
Pydantic request/response models — the HTTP JSON contract (source of truth).

Changing fields here is a contract change: update integration tests and apps/web proxies.
OpenAPI is generated from FastAPI routes that use these models.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Annotated, Literal
from typing import Any

# PEP 604: Using | instead of Optional/Union
# PEP 585: Using built-in collections (dict)

class GenerateRequest(BaseModel):
    """
    Validation schema for SDXL base generation.
    Optimized for Apple Silicon memory constraints(Uses MPS).

    This class is the API contract for POST /generate input.
    FastAPI + Pydantic validate this before inference runs.
    """
    # Reject unknown JSON fields (clients must use lora_name, not raw paths).
    model_config = ConfigDict(extra="forbid")

    # Required text description of target image.
    prompt: str = Field(..., description="The visual description of the image.")
    # Optional negative prompt for things to avoid in output.
    negative_prompt: str = Field(
        default="blurry, low quality, deformed, ugly, bad anatomy",
        description="Concepts to exclude."
    )
    
    # Optional manual seed; if None, engine generates one.
    seed: int | None = Field(default=None, description="Manual seed for deterministic results.")

    # Image dimensions constrained for model stability and memory safety.
    width: Annotated[int, Field(default=1024, ge=512, le=1536, multiple_of=8)]
    height: Annotated[int, Field(default=1024, ge=512, le=1536, multiple_of=8)]

    # SDXL base specific defaults (4 steps, 1.0 guidance)
    steps: Annotated[int, Field(default=4, ge=1, le=40)]
    guidance_scale: Annotated[float, Field(default=1.0, ge=0.0, le=12.0)]
    
    # Runtime tuning knobs for text encoder and denoiser behavior.
    clip_skip: Annotated[int, Field(default=2, ge=1, le=4)]
    scheduler: str = Field(default="dpm++2m_karras")

    model_id: str | None = Field(
        default=None,
        description="Image/video backend: sdxl_base, ltx_video, or ckpt_<checkpoint_stem>.",
    )
    generation_profile: (
        Literal[
            "custom",
            "lightning_4",
            "lightning_8",
            "sdxl_fast",
            "sdxl_balanced",
            "sdxl_quality",
            "sd15_standard",
            "ltx_fast",
        ]
        | None
    ) = Field(
        default=None,
        description="Preset block merged onto request. Auto lightning_4 when LoRA name contains 'lightning'.",
    )

    # tier field (legacy — maps to sdxl_* profiles when generation_profile unset)
    quality_tier: Literal["fast", "balanced", "quality"] | None = Field(
        default=None,
        description="When set, server maps this to steps and guidance_scale (see router.py).",
    )

    lora_name: str | None = Field(
        default=None,
        description="LoRA catalog id → models/loras/<lora_name>.safetensors on disk.",
    )
    lora_weight: Annotated[float, Field(default=0.8, ge=0.0, le=2.0)]

    num_frames: Annotated[int, Field(default=49, ge=9, le=121)]
    frame_rate: Annotated[float, Field(default=24.0, ge=8.0, le=60.0)]

    @field_validator("scheduler")
    @classmethod
    def validate_scheduler(cls, v: str) -> str:
        allowed = {"dpm++2m_karras", "euler", "euler_trailing"}
        if v not in allowed:
            raise ValueError(f"Unsupported scheduler: {v}. Use one of: {sorted(allowed)}")
        return v

    @field_validator("lora_name")
    @classmethod
    def validate_lora_name_field(cls, v: str | None) -> str | None:
        if v is None:
            return None
        from lora_utils import validate_lora_name

        return validate_lora_name(v)

class GenerateResponse(BaseModel):
    """
    Stateless response schema.

    Returned by POST /generate on success.
    - image_base64 contains the JPEG payload.
    - metadata echoes effective generation settings.
    """
    # High-level response status, expected "success" for this model.
    status: str
    # Base64-encoded JPEG poster frame (always set; first frame for video).
    image_base64: str
    # Base64-encoded MP4 when model_id is a video backend (e.g. ltx_video).
    video_base64: str | None = None
    # Structured fields used for debugging/analytics/reproducibility.
    metadata: dict[str, str | int | float | None]

class ErrorResponse(BaseModel):
    """
    Standard error payload used by API endpoints.

    Keep this shape stable so frontend and tests can rely on it.
    """
    # High-level response status, expected "error" for this model.
    status: str
    # Human-readable error message for logs/UI.
    message: str
    # Correlation id for tracing request across logs.
    request_id: str
    # Stable machine-readable error code for frontend behavior.
    error_code: str | None = None
    # Optional debug details in development environments.
    details: str | None = None


class VisualGoal(BaseModel):
    """Model-agnostic intent for correction jobs (planner layer — not sampler knobs)."""

    model_config = ConfigDict(extra="forbid")

    task: str = Field(
        default="general",
        description="Workflow hint, e.g. general, luxury_jewelry, product_composite.",
    )
    realism: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="When high, evaluator enforces stronger tier/steps policy.",
    )
    preserve_product: bool | None = Field(
        default=None,
        description="When true, avoid fast-tier shortcuts for product fidelity.",
    )
    product_similarity_min: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Min CLIP similarity vs reference_image when provided (default 0.85).",
    )
    use_inpaint_correction: bool | None = Field(
        default=None,
        description="When true, job may run SDXL inpaint (mask or auto center mask) after tier bump.",
    )


class InpaintRequest(BaseModel):
    """Inpaint a region of an existing image (white = repaint in mask_image)."""

    model_config = ConfigDict(extra="forbid")

    prompt: str
    image_base64: str = Field(..., description="Init RGB image (JPEG/PNG Base64).")
    mask_base64: str = Field(..., description="Grayscale mask; white pixels are inpainted.")
    negative_prompt: str = Field(
        default="blurry, low quality, deformed, ugly, bad anatomy, glitter, gold dust",
    )
    quality_tier: Literal["fast", "balanced", "quality"] | None = "fast"
    strength: Annotated[float, Field(default=0.85, ge=0.1, le=1.0)]
    seed: int | None = None
    width: Annotated[int, Field(default=1024, ge=512, le=1536, multiple_of=8)]
    height: Annotated[int, Field(default=1024, ge=512, le=1536, multiple_of=8)]


class EvalResult(BaseModel):
    """Outcome of one evaluate pass (universal across backends)."""

    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    attempt: int = Field(ge=1)
    metrics: dict[str, float] = Field(default_factory=dict)


class JobIterationRecord(BaseModel):
    """One generate → evaluate → optional correct cycle."""

    attempt: int
    passed: bool
    issues: list[str]
    quality_tier: str | None = None
    steps: int | None = None
    guidance_scale: float | None = None
    seed: int | None = None
    clip_similarity: float | None = None
    correction: Literal["generate", "inpaint", "tier_bump"] | None = None


class JobCreateRequest(BaseModel):
    """Start a correction loop: generate, evaluate, patch policy, retry until pass or cap."""

    model_config = ConfigDict(extra="forbid")

    goal: VisualGoal
    prompt: str = Field(..., description="Visual description (intent, not adapter internals).")
    negative_prompt: str = Field(
        default="blurry, low quality, deformed, ugly, bad anatomy, glitter, gold dust",
    )
    quality_tier: Literal["fast", "balanced", "quality"] | None = Field(
        default="fast",
        description="Initial policy profile; correction may bump tier.",
    )
    max_iterations: Annotated[int, Field(default=3, ge=1, le=5)]
    seed: int | None = None
    width: Annotated[int, Field(default=1024, ge=512, le=1536, multiple_of=8)]
    height: Annotated[int, Field(default=1024, ge=512, le=1536, multiple_of=8)]
    reference_image_base64: str | None = Field(
        default=None,
        description="Optional product/reference JPEG (Base64) for CLIP similarity eval.",
    )
    mask_base64: str | None = Field(
        default=None,
        description="Optional inpaint mask (white=repaint). Auto center mask if goal.use_inpaint_correction.",
    )
    lora_name: str | None = Field(
        default=None,
        description="Optional LoRA id (models/loras/<name>.safetensors). Generate steps only.",
    )
    lora_weight: Annotated[float, Field(default=0.8, ge=0.0, le=2.0)]
    model_id: str | None = Field(
        default=None,
        description="sdxl_base or ckpt_<stem> for SD 1.5 checkpoints.",
    )
    generation_profile: (
        Literal[
            "custom",
            "lightning_4",
            "lightning_8",
            "sdxl_fast",
            "sdxl_balanced",
            "sdxl_quality",
            "sd15_standard",
        ]
        | None
    ) = None
    steps: Annotated[int | None, Field(default=None, ge=1, le=40)] = None
    guidance_scale: Annotated[float | None, Field(default=None, ge=0.0, le=12.0)] = None
    scheduler: str | None = None
    clip_skip: Annotated[int | None, Field(default=None, ge=1, le=4)] = None


class JobCreateResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running"]
    message: str = "Job accepted"


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "converged", "failed", "error"]
    goal: VisualGoal
    iterations: list[JobIterationRecord] = Field(default_factory=list)
    image_base64: str | None = None
    image_url: str | None = Field(
        default=None,
        description="GET path for final JPEG on disk (smaller than base64 in JSON).",
    )
    metadata: dict[str, Any] | None = None
    error_code: str | None = None
    message: str | None = None


class ChatRequest(BaseModel):
    """POST /chat — GGUF text LLM (not image generation)."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(
        default="dolphin_mixtral_8x7b",
        description="Chat model_id from GET /models (catalog). Unloads SDXL from VRAM when loaded.",
    )

    @field_validator("model_id")
    @classmethod
    def validate_chat_model_id(cls, v: str) -> str:
        from model_catalog import get_chat_model

        get_chat_model(v)
        return v
    prompt: str = Field(..., min_length=1)
    system_prompt: str | None = Field(
        default=None,
        description="Optional system instruction (prompt expansion, style, etc.).",
    )
    max_tokens: Annotated[int, Field(default=512, ge=1, le=4096)]
    temperature: Annotated[float, Field(default=0.7, ge=0.0, le=2.0)]
    top_p: Annotated[float, Field(default=0.9, ge=0.0, le=1.0)]


class ChatResponse(BaseModel):
    status: str
    text: str
    metadata: dict[str, Any]
