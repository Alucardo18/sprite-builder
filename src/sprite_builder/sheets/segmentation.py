"""Pixel-exact sprite-sheet segmentation and guide rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from sprite_builder.postprocess import remove_background
from sprite_builder.sheets.models import SegmentationConfig

ImageInput = str | Path | Image.Image | np.ndarray


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    frames: tuple[Image.Image, ...]
    regions: tuple[tuple[int, int, int, int], ...]
    resolved_config: SegmentationConfig
    warnings: tuple[str, ...] = ()
    empty_frames: tuple[int, ...] = ()


def _image(value: ImageInput) -> Image.Image:
    if isinstance(value, (str, Path)):
        return Image.open(value).convert("RGBA")
    if isinstance(value, Image.Image):
        return value.convert("RGBA")
    array = np.asarray(value)
    if array.ndim != 3 or array.shape[2] not in (3, 4):
        raise ValueError("Expected an RGB or RGBA image")
    if array.shape[2] == 3:
        array = np.dstack((array, np.full(array.shape[:2], 255, np.uint8)))
    return Image.fromarray(array.astype(np.uint8), "RGBA")


def _auto_dimension(available: int, count: int, axis: str, warnings: list[str]) -> int:
    value, remainder = divmod(available, count)
    if value <= 0:
        raise ValueError(f"Not enough {axis} pixels for {count} frames")
    if remainder:
        warnings.append(
            f"{axis} leaves {remainder} unused pixel(s); set cell size manually to correct it"
        )
    return value


def resolve_segmentation_config(
    image_size: tuple[int, int],
    config: SegmentationConfig,
) -> tuple[SegmentationConfig, tuple[str, ...]]:
    width, height = image_size
    if config.frame_count < 1:
        raise ValueError("frame_count must be at least 1")
    if config.orientation not in {"horizontal", "vertical", "grid"}:
        raise ValueError(f"Unsupported orientation: {config.orientation}")
    if min(config.offset_x, config.offset_y, config.spacing_x, config.spacing_y) < 0:
        raise ValueError("Offsets and spacing must be non-negative")
    if config.offset_x >= width or config.offset_y >= height:
        raise ValueError("Initial offset lies outside the source image")

    warnings: list[str] = []
    rows = config.rows
    columns = config.columns
    if config.orientation == "horizontal":
        rows, columns = 1, config.frame_count
    elif config.orientation == "vertical":
        rows, columns = config.frame_count, 1
    else:
        if rows < 1 or columns < 1:
            raise ValueError("Grid rows and columns must be positive")
        if rows * columns < config.frame_count:
            raise ValueError("Grid capacity rows * columns is smaller than frame_count")
        if rows * columns > config.frame_count:
            warnings.append(f"Grid has {rows * columns - config.frame_count} unused cell(s)")

    available_width = width - config.offset_x - max(0, columns - 1) * config.spacing_x
    available_height = height - config.offset_y - max(0, rows - 1) * config.spacing_y
    if available_width <= 0 or available_height <= 0:
        raise ValueError("Offsets and spacing leave no usable image area")

    cell_width = config.cell_width or _auto_dimension(
        available_width, columns, "width", warnings
    )
    cell_height = config.cell_height or _auto_dimension(
        available_height, rows, "height", warnings
    )
    if cell_width <= 0 or cell_height <= 0:
        raise ValueError("Cell dimensions must be positive")

    resolved = SegmentationConfig(
        frame_count=config.frame_count,
        orientation=config.orientation,
        rows=rows,
        columns=columns,
        cell_width=cell_width,
        cell_height=cell_height,
        offset_x=config.offset_x,
        offset_y=config.offset_y,
        spacing_x=config.spacing_x,
        spacing_y=config.spacing_y,
    )
    return resolved, tuple(warnings)


def _frame_is_empty(frame: Image.Image, background_rgb: tuple[int, int, int]) -> bool:
    rgba = np.asarray(frame.convert("RGBA"))
    if np.any(rgba[:, :, 3] < 255):
        return not bool(np.any(rgba[:, :, 3] > 8))
    removed = remove_background(
        frame,
        chroma_rgb=background_rgb,
        tolerance=4.0,
        color_space="rgb",
        feather_px=0,
        min_component_ratio=0,
        cleanup_enabled=False,
        preserve_outline=True,
    )
    return not bool(removed.foreground_mask.any())


def segment_sheet(
    image: ImageInput,
    config: SegmentationConfig,
    *,
    background_rgb: tuple[int, int, int] | None = None,
) -> SegmentationResult:
    rgba = _image(image)
    resolved, warnings = resolve_segmentation_config(rgba.size, config)
    assert resolved.cell_width is not None
    assert resolved.cell_height is not None
    regions: list[tuple[int, int, int, int]] = []
    frames: list[Image.Image] = []
    empty: list[int] = []
    pixels = np.asarray(rgba)
    fallback_bg = background_rgb or (
        int(pixels[0, 0, 0]),
        int(pixels[0, 0, 1]),
        int(pixels[0, 0, 2]),
    )

    for index in range(resolved.frame_count):
        row = index // resolved.columns
        column = index % resolved.columns
        x = resolved.offset_x + column * (resolved.cell_width + resolved.spacing_x)
        y = resolved.offset_y + row * (resolved.cell_height + resolved.spacing_y)
        region = (x, y, x + resolved.cell_width, y + resolved.cell_height)
        if region[2] > rgba.width or region[3] > rgba.height:
            raise ValueError(
                f"CELL_OVERFLOW frame={index} region={region} image={rgba.size}"
            )
        frame = rgba.crop(region)
        regions.append(region)
        frames.append(frame)
        if _frame_is_empty(frame, fallback_bg):
            empty.append(index)

    all_warnings = list(warnings)
    if empty:
        all_warnings.append("Empty frame(s): " + ", ".join(map(str, empty)))
    return SegmentationResult(
        frames=tuple(frames),
        regions=tuple(regions),
        resolved_config=resolved,
        warnings=tuple(all_warnings),
        empty_frames=tuple(empty),
    )


def render_segmentation_preview(
    image: ImageInput,
    result: SegmentationResult,
    *,
    line_color: tuple[int, int, int, int] = (76, 224, 255, 255),
) -> Image.Image:
    preview = _image(image)
    draw = ImageDraw.Draw(preview)
    for index, (x0, y0, x1, y1) in enumerate(result.regions):
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=line_color, width=1)
        draw.rectangle((x0 + 1, y0 + 1, x0 + 12, y0 + 9), fill=(10, 14, 25, 220))
        draw.text((x0 + 3, y0 + 1), str(index), fill=(255, 255, 255, 255))
    return preview
