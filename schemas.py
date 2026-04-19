from pydantic import BaseModel, Field
from typing import Annotated

# PEP 604: Using | instead of Optional/Union
# PEP 585: Using built-in collections (dict)

class GenerateRequest(BaseModel):
    """
    Validation schema for SDXL-Lightning generation.
    Optimized for Apple Silicon memory constraints.
    """
    prompt: str = Field(..., description="The visual description of the image.")
    negative_prompt: str = Field(
        default="blurry, low quality, deformed, ugly, bad anatomy",
        description="Concepts to exclude."
    )
    
    seed: int | None = Field(default=None, description="Manual seed for deterministic results.")

    width: Annotated[int, Field(default=1024, ge=512, le=1536, multiple_of=8)]
    height: Annotated[int, Field(default=1024, ge=512, le=1536, multiple_of=8)]

    # SDXL-Lightning specific defaults (4 steps, 1.0 guidance)
    steps: Annotated[int, Field(default=4, ge=1, le=8)]
    guidance_scale: Annotated[float, Field(default=1.0, ge=0.0, le=2.0)]
    
    clip_skip: Annotated[int, Field(default=2, ge=1, le=4)]
    scheduler: str = Field(default="dpm++2m_karras")

    lora_path: str | None = Field(default=None, description="Local path to .safetensors")
    lora_scale: Annotated[float, Field(default=0.6, ge=0.0, le=1.0)]

class GenerateResponse(BaseModel):
    """
    Stateless response schema.
    """
    status: str
    image_base64: str
    metadata: dict[str, str | int | float | None]

class ErrorResponse(BaseModel):
    status: str
    message: str
    request_id: str
    error_code: str | None = None
    details: str | None = None
