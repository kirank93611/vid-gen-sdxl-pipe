"""Decode API images and build simple masks for inpaint corrections."""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageDraw


def decode_image_bytes(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def decode_image_base64(data_b64: str) -> Image.Image:
    return decode_image_bytes(base64.b64decode(data_b64, validate=True))


def decode_mask_base64(data_b64: str) -> Image.Image:
    """White = inpaint region (diffusers convention)."""
    return Image.open(io.BytesIO(base64.b64decode(data_b64, validate=True))).convert("L")


def image_to_jpeg_bytes(image: Image.Image, quality: int = 90) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def default_center_mask(width: int, height: int, *, fraction: float = 0.42) -> Image.Image:
    """Elliptical mask centered on frame — MVP when user does not upload a mask."""
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    rx = int(width * fraction / 2)
    ry = int(height * fraction / 2)
    cx, cy = width // 2, height // 2
    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    return mask


def mask_to_bytes(mask: Image.Image) -> bytes:
    buffer = io.BytesIO()
    mask.save(buffer, format="PNG")
    return buffer.getvalue()
