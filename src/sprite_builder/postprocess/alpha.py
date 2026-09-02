"""Deterministic alpha inspection for transparent-first sprite generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from PIL import Image

AlphaStatus = Literal["pass", "review", "missing", "reject"]


@dataclass(frozen=True, slots=True)
class AlphaInspection:
    status: AlphaStatus
    reasons: tuple[str, ...]
    has_alpha_channel: bool
    transparent_ratio: float
    partial_alpha_ratio: float
    border_transparent_ratio: float
    foreground_border_ratio: float
    foreground_components: int
    largest_component_ratio: float
    hidden_rgb_ratio: float

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


def inspect_native_alpha(
    image: str | Path | Image.Image,
    *,
    min_transparent_ratio: float = 0.05,
    min_border_transparent_ratio: float = 0.98,
    max_foreground_border_ratio: float = 0.01,
    alpha_threshold: int = 8,
    region: tuple[int, int, int, int] | None = None,
) -> AlphaInspection:
    """Verify that a generated image contains a usable isolated foreground alpha."""

    source = Image.open(image) if not isinstance(image, Image.Image) else image
    has_alpha = "A" in source.getbands()
    rgba = np.asarray(source.convert("RGBA"))
    if region is not None:
        x, y, width, height = region
        if min(x, y, width, height) < 0 or width < 1 or height < 1:
            raise ValueError(f"Invalid alpha inspection region: {region}")
        rgba = rgba[y : y + height, x : x + width]
    alpha = rgba[:, :, 3]
    transparent = alpha <= alpha_threshold
    foreground = ~transparent
    transparent_ratio = float(transparent.mean())
    partial_ratio = float(((alpha > alpha_threshold) & (alpha < 247)).mean())
    border = np.concatenate((alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]))
    border_transparent_ratio = float((border <= alpha_threshold).mean())
    foreground_border_ratio = 1.0 - border_transparent_ratio

    component_count = 0
    largest_component_ratio = 0.0
    if foreground.any():
        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
            foreground.astype(np.uint8), 8
        )
        component_count = max(0, count - 1)
        areas = stats[1:, cv2.CC_STAT_AREA] if count > 1 else np.asarray([], dtype=np.int32)
        largest_component_ratio = float(areas.max() / foreground.sum()) if len(areas) else 0.0

    hidden = rgba[:, :, :3][transparent]
    hidden_rgb_ratio = float(np.any(hidden != 0, axis=1).mean()) if len(hidden) else 0.0
    reasons: list[str] = []
    if not has_alpha or np.all(alpha == 255):
        reasons.append("alpha_channel_missing_or_fully_opaque")
        status: AlphaStatus = "missing"
    elif not foreground.any():
        reasons.append("foreground_missing")
        status = "reject"
    else:
        if transparent_ratio < min_transparent_ratio:
            reasons.append("transparent_area_below_minimum")
        if border_transparent_ratio < min_border_transparent_ratio:
            reasons.append("foreground_or_background_touches_border")
        if foreground_border_ratio > max_foreground_border_ratio:
            reasons.append("foreground_border_spill")
        if largest_component_ratio < 0.50:
            reasons.append("foreground_is_highly_fragmented")
        if hidden_rgb_ratio > 0.01:
            reasons.append("hidden_rgb_under_transparency")
        blocking = {
            "transparent_area_below_minimum",
            "foreground_or_background_touches_border",
            "foreground_border_spill",
        }
        status = "reject" if blocking.intersection(reasons) else "review" if reasons else "pass"

    return AlphaInspection(
        status=status,
        reasons=tuple(reasons),
        has_alpha_channel=has_alpha,
        transparent_ratio=transparent_ratio,
        partial_alpha_ratio=partial_ratio,
        border_transparent_ratio=border_transparent_ratio,
        foreground_border_ratio=foreground_border_ratio,
        foreground_components=component_count,
        largest_component_ratio=largest_component_ratio,
        hidden_rgb_ratio=hidden_rgb_ratio,
    )


def inspect_native_sheet_alpha(
    image: str | Path | Image.Image,
    *,
    rows: int,
    columns: int,
    gutter_px: int,
    frame_count: int,
    min_transparent_ratio: float = 0.05,
    min_border_transparent_ratio: float = 0.98,
    max_foreground_border_ratio: float = 0.01,
    alpha_threshold: int = 8,
) -> AlphaInspection:
    """Inspect each logical cell so adjacent poses do not count as fragmentation."""

    source = Image.open(image) if not isinstance(image, Image.Image) else image
    width, height = source.size
    if rows < 1 or columns < 1 or frame_count < 1 or rows * columns < frame_count:
        raise ValueError("Invalid native sheet alpha layout")
    if gutter_px < 0:
        raise ValueError("Native sheet alpha gutter must be non-negative")
    content_width = width - gutter_px * (columns - 1)
    content_height = height - gutter_px * (rows - 1)
    if content_width < columns or content_height < rows:
        raise ValueError("Native sheet alpha layout leaves no positive cell area")

    inspections: list[AlphaInspection] = []
    for index in range(frame_count):
        row, column = divmod(index, columns)
        x0 = round(column * content_width / columns) + column * gutter_px
        x1 = round((column + 1) * content_width / columns) + column * gutter_px
        y0 = round(row * content_height / rows) + row * gutter_px
        y1 = round((row + 1) * content_height / rows) + row * gutter_px
        inspections.append(
            inspect_native_alpha(
                source,
                min_transparent_ratio=min_transparent_ratio,
                min_border_transparent_ratio=min_border_transparent_ratio,
                max_foreground_border_ratio=max_foreground_border_ratio,
                alpha_threshold=alpha_threshold,
                region=(x0, y0, x1 - x0, y1 - y0),
            )
        )

    reasons = tuple(dict.fromkeys(reason for item in inspections for reason in item.reasons))
    if any(item.status == "missing" for item in inspections):
        status: AlphaStatus = "missing"
    elif any(item.status == "reject" for item in inspections):
        status = "reject"
    elif any(item.status == "review" for item in inspections):
        status = "review"
    else:
        status = "pass"
    return AlphaInspection(
        status=status,
        reasons=reasons,
        has_alpha_channel=all(item.has_alpha_channel for item in inspections),
        transparent_ratio=float(np.mean([item.transparent_ratio for item in inspections])),
        partial_alpha_ratio=float(np.mean([item.partial_alpha_ratio for item in inspections])),
        border_transparent_ratio=float(
            np.mean([item.border_transparent_ratio for item in inspections])
        ),
        foreground_border_ratio=float(
            np.mean([item.foreground_border_ratio for item in inspections])
        ),
        foreground_components=sum(item.foreground_components for item in inspections),
        largest_component_ratio=min(item.largest_component_ratio for item in inspections),
        hidden_rgb_ratio=float(np.mean([item.hidden_rgb_ratio for item in inspections])),
    )


def sanitize_transparent_rgb(
    image: str | Path | Image.Image, *, alpha_threshold: int = 8
) -> Image.Image:
    """Zero invisible RGB so later resampling cannot pull a hidden matte into edges."""

    source = Image.open(image) if not isinstance(image, Image.Image) else image
    rgba = np.asarray(source.convert("RGBA")).copy()
    rgba[rgba[:, :, 3] <= alpha_threshold, :3] = 0
    return Image.fromarray(rgba, "RGBA")
