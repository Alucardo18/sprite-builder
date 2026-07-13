"""Pixel-exact sprite-sheet segmentation and guide rendering."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from sprite_builder.postprocess import remove_background
from sprite_builder.sheets.engine import analyze_center_frames
from sprite_builder.sheets.models import AutoCenterConfig, SegmentationConfig

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

    manual_width_partition = bool(
        config.manual_cut_positions_x
        or (config.orientation == "horizontal" and config.manual_cut_positions)
    )
    manual_height_partition = bool(
        config.manual_cut_positions_y
        or (config.orientation == "vertical" and config.manual_cut_positions)
    )
    cell_width = config.cell_width or _auto_dimension(
        available_width,
        columns,
        "width",
        [] if manual_width_partition else warnings,
    )
    cell_height = config.cell_height or _auto_dimension(
        available_height,
        rows,
        "height",
        [] if manual_height_partition else warnings,
    )
    if cell_width <= 0 or cell_height <= 0:
        raise ValueError("Cell dimensions must be positive")

    manual_cut_positions = tuple(int(value) for value in config.manual_cut_positions)
    manual_cut_positions_x = tuple(int(value) for value in config.manual_cut_positions_x)
    manual_cut_positions_y = tuple(int(value) for value in config.manual_cut_positions_y)

    def validate_cuts(
        cuts: tuple[int, ...],
        expected: int,
        line_start: int,
        line_end: int,
        label: str,
    ) -> None:
        if not cuts:
            return
        if len(cuts) != expected:
            raise ValueError(f"{label} must match the number of frame boundaries")
        if list(cuts) != sorted(cuts):
            raise ValueError(f"{label} must be sorted")
        if cuts[0] < line_start + 1 or cuts[-1] > line_end - 1:
            raise ValueError(f"{label} must stay within the sheet bounds")
        if any(right - left < 1 for left, right in zip(cuts, cuts[1:], strict=False)):
            raise ValueError(f"{label} must be strictly increasing")

    horizontal_end = (
        width
        if config.cell_width is None
        else config.offset_x
        + cell_width * columns
        + max(0, columns - 1) * config.spacing_x
    )
    vertical_end = (
        height
        if config.cell_height is None
        else config.offset_y
        + cell_height * rows
        + max(0, rows - 1) * config.spacing_y
    )
    if config.orientation in {"horizontal", "vertical"}:
        if config.orientation == "horizontal" and not manual_cut_positions:
            manual_cut_positions = manual_cut_positions_x
        if config.orientation == "vertical" and not manual_cut_positions:
            manual_cut_positions = manual_cut_positions_y
        expected_cuts = config.frame_count - 1
        line_start = config.offset_x if config.orientation == "horizontal" else config.offset_y
        line_end = horizontal_end if config.orientation == "horizontal" else vertical_end
        validate_cuts(manual_cut_positions, expected_cuts, line_start, line_end, "Manual cut positions")
    else:
        if manual_cut_positions:
            raise ValueError("Manual cut positions only apply to linear layouts")
        validate_cuts(
            manual_cut_positions_x,
            columns - 1,
            config.offset_x,
            horizontal_end,
            "Horizontal manual cut positions",
        )
        validate_cuts(
            manual_cut_positions_y,
            rows - 1,
            config.offset_y,
            vertical_end,
            "Vertical manual cut positions",
        )

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
        manual_cut_positions=manual_cut_positions,
        manual_cut_positions_x=manual_cut_positions_x,
        manual_cut_positions_y=manual_cut_positions_y,
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

    manual_cut_positions = tuple(int(value) for value in resolved.manual_cut_positions)
    use_manual_cuts = bool(manual_cut_positions) and resolved.orientation in {
        "horizontal",
        "vertical",
    }
    if use_manual_cuts and len(manual_cut_positions) != resolved.frame_count - 1:
        raise ValueError("Manual cut positions must match frame_count - 1")
    if use_manual_cuts:
        boundary_start = (
            resolved.offset_x if resolved.orientation == "horizontal" else resolved.offset_y
        )
        boundary_end = (
            rgba.width
            if resolved.orientation == "horizontal" and config.cell_width is None
            else rgba.height
            if resolved.orientation == "vertical" and config.cell_height is None
            else resolved.offset_x
            + resolved.cell_width * resolved.frame_count
            + max(0, resolved.frame_count - 1) * resolved.spacing_x
            if resolved.orientation == "horizontal"
            else resolved.offset_y
            + resolved.cell_height * resolved.frame_count
            + max(0, resolved.frame_count - 1) * resolved.spacing_y
        )
        boundaries = (boundary_start, *manual_cut_positions, boundary_end)

    grid_x_cuts = tuple(int(value) for value in resolved.manual_cut_positions_x)
    grid_y_cuts = tuple(int(value) for value in resolved.manual_cut_positions_y)
    use_manual_grid_cuts = resolved.orientation == "grid" and bool(grid_x_cuts or grid_y_cuts)
    if use_manual_grid_cuts:
        x_end = (
            rgba.width
            if config.cell_width is None
            else resolved.offset_x + resolved.cell_width * resolved.columns + max(
                0, resolved.columns - 1
            ) * resolved.spacing_x
        )
        y_end = (
            rgba.height
            if config.cell_height is None
            else resolved.offset_y + resolved.cell_height * resolved.rows + max(
                0, resolved.rows - 1
            ) * resolved.spacing_y
        )
        x_boundaries = (
            (resolved.offset_x, *grid_x_cuts, x_end)
            if grid_x_cuts
            else tuple(
                resolved.offset_x
                + min(column, resolved.columns) * resolved.cell_width
                + min(column, max(0, resolved.columns - 1)) * resolved.spacing_x
                for column in range(resolved.columns + 1)
            )
        )
        y_boundaries = (
            (resolved.offset_y, *grid_y_cuts, y_end)
            if grid_y_cuts
            else tuple(
                resolved.offset_y
                + min(row, resolved.rows) * resolved.cell_height
                + min(row, max(0, resolved.rows - 1)) * resolved.spacing_y
                for row in range(resolved.rows + 1)
            )
        )

    for index in range(resolved.frame_count):
        if use_manual_cuts and resolved.orientation == "horizontal":
            x0 = boundaries[index]
            x1 = boundaries[index + 1]
            y0 = resolved.offset_y
            y1 = resolved.offset_y + resolved.cell_height
            region = (x0, y0, x1, y1)
        elif use_manual_cuts and resolved.orientation == "vertical":
            y0 = boundaries[index]
            y1 = boundaries[index + 1]
            x0 = resolved.offset_x
            x1 = resolved.offset_x + resolved.cell_width
            region = (x0, y0, x1, y1)
        elif use_manual_grid_cuts:
            row = index // resolved.columns
            column = index % resolved.columns
            region = (
                x_boundaries[column],
                y_boundaries[row],
                x_boundaries[column + 1],
                y_boundaries[row + 1],
            )
        else:
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


def auto_cut_positions(
    image: ImageInput,
    config: SegmentationConfig,
    anchor_config: AutoCenterConfig,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Find cut boundaries from torso anchors in a provisional uniform segmentation."""
    rgba = _image(image)
    resolved, _ = resolve_segmentation_config(
        rgba.size,
        replace(
            config,
            manual_cut_positions=(),
            manual_cut_positions_x=(),
            manual_cut_positions_y=(),
        ),
    )
    provisional = segment_sheet(
        rgba,
        replace(
            resolved,
            manual_cut_positions=(),
            manual_cut_positions_x=(),
            manual_cut_positions_y=(),
        ),
    )
    try:
        analysis = analyze_center_frames(
            provisional.frames,
            replace(anchor_config, method="body"),
        )
    except (ValueError, IndexError):
        analysis = None

    def uniform_boundaries(start: int, cell: int, count: int, spacing: int) -> list[int]:
        return [start + index * (cell + spacing) for index in range(count)] + [
            start + cell * count + max(0, count - 1) * spacing
        ]

    x_boundaries = uniform_boundaries(
        resolved.offset_x,
        resolved.cell_width,
        resolved.columns,
        resolved.spacing_x,
    )
    y_boundaries = uniform_boundaries(
        resolved.offset_y,
        resolved.cell_height,
        resolved.rows,
        resolved.spacing_y,
    )
    if analysis is None or any(item.confidence <= 0 for item in analysis.detections):
        return tuple(x_boundaries[1:-1]), tuple(y_boundaries[1:-1])

    target_x = max(0.0, min(float(resolved.cell_width), float(anchor_config.canonical_anchor[0])))
    target_y = max(0.0, min(float(resolved.cell_height), float(anchor_config.canonical_anchor[1])))
    anchors = [item.anchor for item in analysis.detections]

    def bounded_midpoint(candidate: float, lower: int, upper: int) -> int:
        return max(lower + 1, min(upper - 1, int(round(candidate))))

    if resolved.orientation == "horizontal":
        global_x = [
            resolved.offset_x + index * (resolved.cell_width + resolved.spacing_x) + anchor[0]
            for index, anchor in enumerate(anchors)
        ]
        x_boundaries = [resolved.offset_x]
        source_end = resolved.offset_x + resolved.cell_width * resolved.frame_count + max(
            0, resolved.frame_count - 1
        ) * resolved.spacing_x
        for index in range(len(global_x) - 1):
            left_edge = x_boundaries[-1]
            right_edge = source_end
            candidate = ((global_x[index] + resolved.cell_width - target_x) + (global_x[index + 1] - target_x)) / 2
            x_boundaries.append(bounded_midpoint(candidate, left_edge, right_edge))
        x_boundaries.append(source_end)
        return tuple(x_boundaries[1:-1]), ()

    if resolved.orientation == "vertical":
        global_y = [
            resolved.offset_y + index * (resolved.cell_height + resolved.spacing_y) + anchor[1]
            for index, anchor in enumerate(anchors)
        ]
        y_boundaries = [resolved.offset_y]
        source_end = resolved.offset_y + resolved.cell_height * resolved.frame_count + max(
            0, resolved.frame_count - 1
        ) * resolved.spacing_y
        for index in range(len(global_y) - 1):
            top_edge = y_boundaries[-1]
            bottom_edge = source_end
            candidate = ((global_y[index] + resolved.cell_height - target_y) + (global_y[index + 1] - target_y)) / 2
            y_boundaries.append(bounded_midpoint(candidate, top_edge, bottom_edge))
        y_boundaries.append(source_end)
        return (), tuple(y_boundaries[1:-1])

    x_anchor_columns: list[float] = []
    for column in range(resolved.columns):
        values = [
            resolved.offset_x
            + column * (resolved.cell_width + resolved.spacing_x)
            + anchors[row * resolved.columns + column][0]
            for row in range(resolved.rows)
            if row * resolved.columns + column < len(anchors)
        ]
        x_anchor_columns.append(float(np.median(values)) if values else 0.0)
    y_anchor_rows: list[float] = []
    for row in range(resolved.rows):
        values = [
            resolved.offset_y
            + row * (resolved.cell_height + resolved.spacing_y)
            + anchors[row * resolved.columns + column][1]
            for column in range(resolved.columns)
            if row * resolved.columns + column < len(anchors)
        ]
        y_anchor_rows.append(float(np.median(values)) if values else 0.0)
    for index in range(len(x_anchor_columns) - 1):
        candidate = ((x_anchor_columns[index] + resolved.cell_width - target_x) + (x_anchor_columns[index + 1] - target_x)) / 2
        x_boundaries[index + 1] = bounded_midpoint(
            candidate,
            x_boundaries[index],
            x_boundaries[index + 2],
        )
    for index in range(len(y_anchor_rows) - 1):
        candidate = ((y_anchor_rows[index] + resolved.cell_height - target_y) + (y_anchor_rows[index + 1] - target_y)) / 2
        y_boundaries[index + 1] = bounded_midpoint(
            candidate,
            y_boundaries[index],
            y_boundaries[index + 2],
        )
    return tuple(x_boundaries[1:-1]), tuple(y_boundaries[1:-1])


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


def render_segmentation_guides(
    image: ImageInput,
    result: SegmentationResult,
    *,
    line_color: tuple[int, int, int, int] = (76, 224, 255, 255),
) -> Image.Image:
    return render_segmentation_region_guides(
        _image(image).size,
        result.regions,
        line_color=line_color,
    )


def render_segmentation_region_guides(
    image_size: tuple[int, int],
    regions: tuple[tuple[int, int, int, int], ...],
    *,
    line_color: tuple[int, int, int, int] = (76, 224, 255, 255),
) -> Image.Image:
    guide = Image.new("RGBA", image_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(guide)
    for index, (x0, y0, x1, y1) in enumerate(regions):
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=(8, 10, 18, 220), width=3)
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=line_color, width=1)
        draw.rectangle((x0 + 1, y0 + 1, x0 + 12, y0 + 9), fill=(10, 14, 25, 220))
        draw.text((x0 + 3, y0 + 1), str(index), fill=(255, 255, 255, 255))
    return guide
