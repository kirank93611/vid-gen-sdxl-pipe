from pydantic import BaseModel, ConfigDict, Field
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
    # Forbid unknown fields so deferred features (ex: lora_path) fail fast.
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

    # tier field
    quality_tier: Literal["fast", "balanced", "quality"] | None = Field(
        default=None,
        description="When set, server maps this to steps and guidance_scale (see router.py).",
    )

class GenerateResponse(BaseModel):
    """
    Stateless response schema.

    Returned by POST /generate on success.
    - image_base64 contains the JPEG payload.
    - metadata echoes effective generation settings.
    """
    # High-level response status, expected "success" for this model.
    status: str
    # Base64-encoded JPEG bytes.
    image_base64: str
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
    metadata: dict[str, Any] | None = None
    error_code: str | None = None
    message: str | None = None
