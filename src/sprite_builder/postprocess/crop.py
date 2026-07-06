from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class CropResult:
    image: Image.Image
    bbox: tuple[int, int, int, int]
    source_size: tuple[int, int]


def autocut_sprite(
    image: str | Path | Image.Image, *, padding: int = 0, alpha_threshold: int = 8
) -> CropResult:
    if not isinstance(image, Image.Image):
        image = Image.open(image)
    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba)[:, :, 3]
    points = np.argwhere(alpha > alpha_threshold)
    if not len(points):
        raise ValueError("Cannot crop an empty/transparent sprite")
    y0, x0 = points.min(axis=0)
    y1, x1 = points.max(axis=0) + 1
    x0, y0 = max(0, x0 - padding), max(0, y0 - padding)
    x1, y1 = min(rgba.width, x1 + padding), min(rgba.height, y1 + padding)
    bbox = tuple(map(int, (x0, y0, x1, y1)))
    return CropResult(rgba.crop(bbox), bbox, rgba.size)
