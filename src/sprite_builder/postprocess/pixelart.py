from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def _image(value: str | Path | Image.Image) -> Image.Image:
    return (Image.open(value) if not isinstance(value, Image.Image) else value).convert("RGBA")


def quantize_palette(
    image: str | Path | Image.Image,
    palette: list[tuple[int, int, int]],
    *,
    alpha_thresholds: tuple[int, int] = (32, 223),
) -> Image.Image:
    if not palette:
        raise ValueError("Palette must not be empty")
    arr = np.asarray(_image(image)).copy()
    lab = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    pal_rgb = np.uint8(palette).reshape(-1, 1, 3)
    pal_lab = cv2.cvtColor(pal_rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    flat = lab.reshape(-1, 3)
    nearest = np.argmin(((flat[:, None] - pal_lab[None]) ** 2).sum(axis=2), axis=1)
    arr[:, :, :3] = np.asarray(palette, np.uint8)[nearest].reshape(arr.shape[:2] + (3,))
    lo, hi = alpha_thresholds
    alpha = arr[:, :, 3]
    alpha[alpha < lo] = 0
    alpha[alpha > hi] = 255
    return Image.fromarray(arr, "RGBA")


def normalize_sprite(
    image: str | Path | Image.Image,
    *,
    target_body_height: int,
    source_body_height: int | None = None,
    palette: list[tuple[int, int, int]] | None = None,
) -> Image.Image:
    """Scale once to a fixed canonical body height.

    Callers should pass the same ``source_body_height`` for every frame.
    When omitted, the alpha bounding-box height is used (suited to calibration,
    not weapon-heavy animation frames).
    """
    rgba = _image(image)
    arr = np.asarray(rgba)
    if source_body_height is None:
        ys = np.where(arr[:, :, 3] > 8)[0]
        if not len(ys):
            raise ValueError("Cannot normalize an empty sprite")
        source_body_height = int(ys.max() - ys.min() + 1)
    if source_body_height <= 0 or target_body_height <= 0:
        raise ValueError("Body heights must be positive")
    scale = target_body_height / source_body_height
    size = (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale)))
    # AREA for reduction; nearest for enlargement preserves hard pixel blocks.
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_NEAREST
    resized = cv2.resize(arr, size, interpolation=interpolation)
    result = Image.fromarray(resized.astype(np.uint8), "RGBA")
    return quantize_palette(result, palette) if palette else result
