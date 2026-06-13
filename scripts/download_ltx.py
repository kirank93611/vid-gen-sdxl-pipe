#!/usr/bin/env python3
"""Download LTX 2.3 dev weights for ltx_video model."""

from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = REPO_ROOT / "models" / "ltx-2.3"
HF_REPO = os.getenv("LTX_HF_REPO", "Lightricks/LTX-2.3")
HF_FILENAME = os.getenv(
    "LTX_HF_FILENAME",
    "ltx-2.3-22b-dev.safetensors",
)


def main() -> None:
    dest_dir = Path(os.getenv("LTX_MODEL_DIR", str(DEFAULT_DEST)))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / HF_FILENAME

    if dest_file.is_file() and dest_file.stat().st_size > 1_000_000_000:
        print(f"LTX weights already present: {dest_file}")
        return

    print(f"Downloading {HF_REPO}/{HF_FILENAME} → {dest_file}")
    print("(Large download — ~46 GB for dev weights.)")
    cached = hf_hub_download(
        repo_id=HF_REPO,
        filename=HF_FILENAME,
        local_dir=str(dest_dir),
    )
    print(f"Done: {cached}")


if __name__ == "__main__":
    main()
