from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated

# PEP 604: Using | instead of Optional/Union
# PEP 585: Using built-in collections (dict)

class GenerateRequest(BaseModel):
    """
    Validation schema for SDXL-Lightning generation.
    Optimized for Apple Silicon memory constraints.

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

    # SDXL-Lightning specific defaults (4 steps, 1.0 guidance)
    steps: Annotated[int, Field(default=4, ge=1, le=8)]
    guidance_scale: Annotated[float, Field(default=1.0, ge=0.0, le=2.0)]
    
    # Runtime tuning knobs for text encoder and denoiser behavior.
    clip_skip: Annotated[int, Field(default=2, ge=1, le=4)]
    scheduler: str = Field(default="dpm++2m_karras")

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
