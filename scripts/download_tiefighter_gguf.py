#!/usr/bin/env python3
"""Backward-compatible: downloads tiefighter_20b via download_gguf_model.py."""
import subprocess
import sys
from pathlib import Path

script = Path(__file__).resolve().parent / "download_gguf_model.py"
sys.exit(subprocess.call([sys.executable, str(script), "tiefighter_20b"]))
