"""Source-image inspection for the local sheet editor."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from sprite_builder.sheets.models import SheetInspection


def inspect_sheet(image: str | Path | Image.Image) -> SheetInspection:
    source: Image.Image
    if isinstance(image, (str, Path)):
        source = Image.open(image)
        close = True
    else:
        source = image
        close = False
    try:
        mode = source.mode
        has_alpha = "A" in source.getbands() or "transparency" in source.info
        rgba = np.asarray(source.convert("RGBA"))
        alpha = rgba[:, :, 3]
        uses_transparency = bool(np.any(alpha < 255))
        rgb = rgba[:, :, :3]
        border = np.concatenate((rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]))
        colors, counts = np.unique(border.reshape(-1, 3), axis=0, return_counts=True)
        winning = int(np.argmax(counts))
        border_rgb = (
            int(colors[winning][0]),
            int(colors[winning][1]),
            int(colors[winning][2]),
        )
        top_left_rgb = (
            int(rgb[0, 0, 0]),
            int(rgb[0, 0, 1]),
            int(rgb[0, 0, 2]),
        )
        confidence = float(counts[winning] / max(1, len(border)))
        return SheetInspection(
            width=source.width,
            height=source.height,
            mode=mode,
            has_alpha=has_alpha,
            uses_transparency=uses_transparency,
            top_left_rgb=top_left_rgb,
            border_rgb=border_rgb,
            solid_background_likely=not uses_transparency and confidence >= 0.60,
            background_confidence=confidence,
        )
    finally:
        if close:
            source.close()
