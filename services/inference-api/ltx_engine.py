"""LTX 2 / 2.3 text-to-video via diffusers LTX2Pipeline."""

from __future__ import annotations

import io
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

from device import resolve_torch_device
from engine import GenerationCancelledError
from lora_utils import resolve_lora_path
from schemas import GenerateRequest

_DEFAULT_NUM_FRAMES = int(os.getenv("LTX_NUM_FRAMES", "49"))
_DEFAULT_FRAME_RATE = float(os.getenv("LTX_FRAME_RATE", "24"))


def resolve_ltx_model_path() -> Path:
    """Return the first on-disk LTX checkpoint, or the default expected path."""
    from api_config import REPO_ROOT

    env = os.environ.get("LTX_MODEL_PATH")
    if env:
        return Path(env)

    candidates = [
        REPO_ROOT / "models" / "ltx-2.3" / "ltx-2.3-22b-dev.safetensors",
        REPO_ROOT / "models" / "ltx-2.3" / "ltx-2.3-22b-distilled.safetensors",
        REPO_ROOT / "models" / "ltx-2" / "ltx-2-19b-dev-fp8.safetensors",
        REPO_ROOT / "models" / "ltx-2",
    ]
    for path in candidates:
        if path.is_file():
            return path
        if path.is_dir() and (path / "model_index.json").is_file():
            return path

    return candidates[0]


def ltx_model_on_disk(path: Path | None = None) -> bool:
    resolved = path or resolve_ltx_model_path()
    if resolved.is_file():
        return resolved.stat().st_size > 1_000_000_000
    return resolved.is_dir() and (resolved / "model_index.json").is_file()


class LTX2Engine:
    """LTX2 text-to-video; returns (mp4_bytes, poster_jpeg_bytes, seed)."""

    media_type = "video/mp4"

    def __init__(self, model_path: str | Path | None = None, device: str | None = None) -> None:
        self.model_path = Path(model_path) if model_path else resolve_ltx_model_path()
        self.device = device or resolve_torch_device()
        self.pipeline = None
        self._active_lora_key: tuple[str, float] | None = None
        self._lock = threading.Lock()
        self.load_model()

    def load_model(self) -> None:
        if not ltx_model_on_disk(self.model_path):
            raise FileNotFoundError(
                f"LTX weights not found at {self.model_path}. "
                "Run: make download-ltx (or set LTX_MODEL_PATH)."
            )

        from diffusers import LTX2Pipeline

        if self.device == "cuda":
            dtype = torch.bfloat16
        elif self.device == "mps":
            dtype = torch.float16
        else:
            dtype = torch.float32

        print(f"Loading LTX from {self.model_path} on device={self.device}")

        if self.model_path.is_file():
            self.pipeline = LTX2Pipeline.from_single_file(
                str(self.model_path),
                torch_dtype=dtype,
            )
        else:
            self.pipeline = LTX2Pipeline.from_pretrained(
                str(self.model_path),
                torch_dtype=dtype,
            )

        if self.device == "cuda":
            self.pipeline.to("cuda")
        elif self.device == "mps":
            try:
                self.pipeline.to("mps")
            except Exception:
                self.pipeline.enable_model_cpu_offload()
        else:
            self.pipeline.enable_model_cpu_offload()

        print(f"LTX pipeline ready on {self.device}.")

    def unload(self) -> None:
        with self._lock:
            self.pipeline = None
            self._active_lora_key = None

    def _clear_lora(self) -> None:
        assert self.pipeline is not None
        try:
            if hasattr(self.pipeline, "unfuse_lora"):
                self.pipeline.unfuse_lora()
        except Exception:
            pass
        try:
            self.pipeline.unload_lora_weights()
        except Exception:
            pass
        self._active_lora_key = None

    def _apply_lora(self, req: GenerateRequest) -> None:
        assert self.pipeline is not None
        if not req.lora_name:
            if self._active_lora_key is not None:
                self._clear_lora()
            return

        key = (req.lora_name, req.lora_weight)
        if key == self._active_lora_key:
            return

        self._clear_lora()
        path = resolve_lora_path(req.lora_name)
        self.pipeline.load_lora_weights(str(path.parent), weight_name=path.name)
        try:
            self.pipeline.fuse_lora(lora_scale=req.lora_weight)
        except Exception:
            adapters = (
                self.pipeline.get_list_adapters()
                if hasattr(self.pipeline, "get_list_adapters")
                else {}
            )
            names = list(adapters.keys()) if adapters else ["default_0"]
            self.pipeline.set_adapters(names, adapter_weights=[req.lora_weight])
        self._active_lora_key = key

    def generate(
        self,
        req: GenerateRequest,
        *,
        cancel_event: threading.Event | None = None,
    ) -> tuple[bytes, bytes, int]:
        from diffusers.pipelines.ltx2.export_utils import encode_video

        seed = (
            req.seed
            if req.seed is not None
            else torch.randint(0, 2**32 - 1, (1,)).item()
        )
        generator = torch.Generator(device="cpu").manual_seed(seed)

        num_frames = getattr(req, "num_frames", None) or _DEFAULT_NUM_FRAMES
        frame_rate = getattr(req, "frame_rate", None) or _DEFAULT_FRAME_RATE

        def _on_step_end(step_index: int, _timestep: int) -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelledError("cancelled")

        with self._lock:
            assert self.pipeline is not None
            self._apply_lora(req)

            output = self.pipeline(
                prompt=req.prompt,
                negative_prompt=req.negative_prompt,
                width=req.width,
                height=req.height,
                num_frames=num_frames,
                frame_rate=frame_rate,
                num_inference_steps=req.steps,
                guidance_scale=req.guidance_scale,
                generator=generator,
                output_type="np",
                return_dict=False,
                callback_on_step_end=_on_step_end if cancel_event else None,
            )

        video, audio = output[0], output[1]
        frames = video[0] if isinstance(video, (list, tuple)) else video
        if isinstance(frames, np.ndarray):
            frame0 = frames[0]
            if frame0.max() <= 1.0:
                poster = Image.fromarray((frame0 * 255).astype(np.uint8))
            else:
                poster = Image.fromarray(frame0.astype(np.uint8))
        else:
            poster = frames[0] if hasattr(frames, "__getitem__") else frames

        poster_buf = io.BytesIO()
        poster.save(poster_buf, format="JPEG", quality=90)
        poster_bytes = poster_buf.getvalue()

        audio_tensor = audio[0] if isinstance(audio, (list, tuple)) else audio
        vocoder_rate = int(self.pipeline.vocoder.config.output_sampling_rate)

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            encode_video(
                video[0] if isinstance(video, (list, tuple)) else video,
                fps=int(frame_rate),
                audio=audio_tensor.float().cpu(),
                audio_sample_rate=vocoder_rate,
                output_path=tmp_path,
            )
            mp4_bytes = Path(tmp_path).read_bytes()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return mp4_bytes, poster_bytes, seed
