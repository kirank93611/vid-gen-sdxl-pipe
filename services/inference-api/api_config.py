"""
Runtime configuration for the inference API (env vars and paths).

Import from here instead of scattering os.getenv across modules.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = REPO_ROOT / "models" / "sdxl-base"

APP_ENV = os.getenv("APP_ENV", "dev").lower()
API_KEY_HEADER = "X-API-Key"
EXPECTED_API_KEY = os.getenv("SDXL_API_KEY", "dev-local-key")

MAX_INFLIGHT_GENERATIONS = int(os.getenv("MAX_INFLIGHT_GENERATIONS", "1"))
GENERATION_TIMEOUT_SECONDS = int(os.getenv("GENERATION_TIMEOUT_SECONDS", "90"))
GENERATION_CANCEL_GRACE_SECONDS = float(
    os.getenv("GENERATION_CANCEL_GRACE_SECONDS", "120")
)
INPAINT_STRENGTH = float(os.getenv("INPAINT_STRENGTH", "0.85"))

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "5"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

SDXL_MODEL_PATH = os.environ.get("SDXL_MODEL_PATH", str(DEFAULT_MODEL_PATH))
