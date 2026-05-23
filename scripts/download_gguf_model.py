#!/usr/bin/env python3
"""Download a catalog chat model GGUF to models/<subdir>/."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_API = REPO_ROOT / "services" / "inference-api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from model_catalog import CHAT_MODEL_IDS, get_chat_model  # noqa: E402


def main() -> None:
    model_id = os.environ.get("GGUF_MODEL_ID") or (
        sys.argv[1] if len(sys.argv) > 1 else "dolphin_mixtral_8x7b"
    )
    if model_id not in CHAT_MODEL_IDS:
        print(f"Unknown model_id: {model_id}")
        print(f"Available: {', '.join(sorted(CHAT_MODEL_IDS))}")
        sys.exit(1)

    spec = get_chat_model(model_id)
    dest = spec.gguf_path().parent
    dest.mkdir(parents=True, exist_ok=True)
    target = spec.gguf_path()

    min_bytes = spec.gguf_min_bytes or 1_000_000_000
    if target.is_file():
        size = target.stat().st_size
        if size >= min_bytes:
            print(f"Already present: {target} ({size // (1024**3)} GiB)")
            return
        print(
            f"Removing stale/incompatible GGUF ({size // (1024**3)} GiB, need >= {min_bytes // (1024**3)} GiB): {target}"
        )
        target.unlink()

    from huggingface_hub import hf_hub_download

    print(f"Downloading {spec.hf_repo} / {spec.gguf_filename}")
    print(f"  → {dest}")
    path = hf_hub_download(
        repo_id=spec.hf_repo,
        filename=spec.gguf_filename,
        local_dir=str(dest),
    )
    print("Done:", path)


if __name__ == "__main__":
    main()
