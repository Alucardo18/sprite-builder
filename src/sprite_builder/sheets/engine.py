"""Reusable processing engine shared by UI, CLI helpers, and skills."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw

from sprite_builder.alignment import (
    AnchorDetection,
    align_frames_by_anchor,
    calibrate_torso_automatically,
    detect_torso_anchor,
    estimate_body_anchor,
)
from sprite_builder.export import SheetResult, build_spritesheet
from sprite_builder.postprocess import remove_background
from sprite_builder.sheets.models import (
    AutoCenterConfig,
    BackgroundRemovalConfig,
    ExportCropConfig,
    FrameAdjustment,
)


@dataclass(frozen=True, slots=True)
class CenteringResult:
    frames: tuple[Image.Image, ...]
    adjustments: tuple[FrameAdjustment, ...]
    jitter_report: dict[str, float]
    status: str


@dataclass(frozen=True, slots=True)
class ExportCropResult:
    frames: tuple[Image.Image, ...]
    bbox: tuple[int, int, int, int]
    source_size: tuple[int, int]


OverflowStrategy = Literal["strict", "clamp"]


def apply_background_removal(
    frames: Sequence[Image.Image],
    config: BackgroundRemovalConfig,
) -> tuple[Image.Image, ...]:
    return tuple(
        remove_background(
            frame,
            chroma_rgb=config.color,
            tolerance=config.tolerance,
            color_space=config.color_space,
            feather_px=0,
            min_component_ratio=0 if config.preserve_outline else 0.0005,
            cleanup_enabled=config.cleanup_enabled,
            fringe_cleanup_strength=config.fringe_cleanup_strength,
            remove_near_transparent=config.remove_near_transparent,
            near_transparent_threshold=config.near_transparent_threshold,
            preserve_outline=config.preserve_outline,
            border_connected_only=config.border_connected_only,
        ).image
        for frame in frames
    )


def pad_frames_to_common_canvas(
    frames: Sequence[Image.Image],
) -> tuple[Image.Image, ...]:
    if not frames:
        raise ValueError("At least one frame is required")
    rgba_frames = tuple(frame.convert("RGBA") for frame in frames)
    max_width = max(frame.width for frame in rgba_frames)
    max_height = max(frame.height for frame in rgba_frames)
    if all(frame.size == (max_width, max_height) for frame in rgba_frames):
        return rgba_frames
    padded: list[Image.Image] = []
    for frame in rgba_frames:
        canvas = Image.new("RGBA", (max_width, max_height), (0, 0, 0, 0))
        canvas.paste(frame, (0, 0))
        padded.append(canvas)
    return tuple(padded)


def trim_transparent_frames(
    frames: Sequence[Image.Image],
    config: ExportCropConfig,
) -> ExportCropResult:
    if not frames:
        raise ValueError("At least one frame is required")
    rgba_frames = pad_frames_to_common_canvas(frames)
    source_size = rgba_frames[0].size
    if not config.enabled:
        return ExportCropResult(rgba_frames, (0, 0, source_size[0], source_size[1]), source_size)
    if config.padding < 0:
        raise ValueError("Crop padding must be non-negative")
    if config.alpha_threshold < 0:
        raise ValueError("Alpha threshold must be non-negative")

    union_mask: np.ndarray | None = None
    for frame in rgba_frames:
        alpha = np.asarray(frame)[:, :, 3] > config.alpha_threshold
        union_mask = alpha if union_mask is None else np.logical_or(union_mask, alpha)
    if union_mask is None or not union_mask.any():
        raise ValueError("Cannot crop an empty frame set")
    ys, xs = np.where(union_mask)
    x0 = max(0, int(xs.min()) - config.padding)
    y0 = max(0, int(ys.min()) - config.padding)
    x1 = min(source_size[0], int(xs.max()) + 1 + config.padding)
    y1 = min(source_size[1], int(ys.max()) + 1 + config.padding)
    bbox = (x0, y0, x1, y1)
    cropped = tuple(frame.crop(bbox) for frame in rgba_frames)
    return ExportCropResult(cropped, bbox, source_size)


def _bbox_detection(frame: Image.Image) -> tuple[AnchorDetection, tuple[int, int, int, int]]:
    alpha = np.asarray(frame.convert("RGBA"))[:, :, 3]
    ys, xs = np.where(alpha > 8)
    if not len(xs):
        raise ValueError("Cannot align an empty frame")
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    anchor = ((bbox[0] + bbox[2] - 1) / 2, (bbox[1] + bbox[3] - 1) / 2)
    return AnchorDetection(anchor, 0.5, 0, 0, 0, "bounding_box"), bbox


def _body_detections(
    frames: Sequence[Image.Image],
) -> tuple[list[AnchorDetection], list[tuple[int, int, int, int]]]:
    calibration, seed = calibrate_torso_automatically(frames[0])
    detections = [
        AnchorDetection(
            seed.anchor,
            seed.confidence,
            seed.confidence,
            0,
            seed.confidence,
            "body_core",
        )
    ]
    bboxes = [seed.body_bbox]
    previous_frame: Image.Image | None = frames[0]
    previous_anchor = seed.anchor

    for frame in frames[1:]:
        robust = estimate_body_anchor(frame)
        tracked = detect_torso_anchor(
            frame,
            calibration,
            previous_frame=previous_frame,
            previous_anchor=previous_anchor,
        )
        disagreement = float(np.linalg.norm(np.subtract(tracked.anchor, robust.anchor)))
        allowed = max(3.0, robust.torso_height * 0.35)
        if tracked.confidence < 0.45 or disagreement > allowed:
            selected = AnchorDetection(
                robust.anchor,
                robust.confidence * 0.9,
                tracked.template_score,
                tracked.flow_inlier_ratio,
                robust.confidence,
                "body_core_fallback",
            )
        else:
            agreement = float(np.exp(-disagreement / max(allowed, 1)))
            selected = AnchorDetection(
                tracked.anchor,
                float(np.clip(0.8 * tracked.confidence + 0.2 * agreement, 0, 1)),
                tracked.template_score,
                tracked.flow_inlier_ratio,
                tracked.core_score,
                "torso_hybrid",
            )
        detections.append(selected)
        bboxes.append(robust.body_bbox)
        previous_frame = frame
        previous_anchor = selected.anchor
    return detections, bboxes


def auto_center_frames(
    frames: Sequence[Image.Image],
    config: AutoCenterConfig,
    *,
    manual_offsets: Sequence[tuple[int, int]] | None = None,
    locked: Sequence[bool] | None = None,
    notes: Sequence[str] | None = None,
    overflow_strategy: OverflowStrategy = "strict",
) -> CenteringResult:
    if not frames:
        raise ValueError("At least one frame is required")
    if config.canvas_width <= 0 or config.canvas_height <= 0:
        raise ValueError("Canvas dimensions must be positive")
    if not 0 <= config.confidence_threshold <= 1:
        raise ValueError("Confidence threshold must be between 0 and 1")

    offsets = tuple(manual_offsets or ((0, 0),) * len(frames))
    locks = tuple(locked or (False,) * len(frames))
    frame_notes = tuple(notes or ("",) * len(frames))
    if not (len(offsets) == len(locks) == len(frame_notes) == len(frames)):
        raise ValueError("Frame adjustment counts differ")

    if config.method == "body":
        detections, bboxes = _body_detections(frames)
    elif config.method == "bounding_box":
        pairs = [_bbox_detection(frame) for frame in frames]
        detections = [item[0] for item in pairs]
        bboxes = [item[1] for item in pairs]
    else:
        raise ValueError(f"Unsupported center method: {config.method}")

    applied_translations: list[tuple[int, int]] | None = None
    canvas_shift_x = 0
    canvas_shift_y = 0
    if overflow_strategy == "strict":
        aligned = align_frames_by_anchor(
            frames,
            detections,
            canvas_size=(config.canvas_width, config.canvas_height),
            target_anchor=config.canonical_anchor,
            manual_offsets=offsets,
        )
    elif overflow_strategy == "clamp":
        aligned = []
        applied_translations = []
        frame_data = []
        min_canvas_x = 0
        min_canvas_y = 0
        max_canvas_x = config.canvas_width
        max_canvas_y = config.canvas_height
        for index, frame in enumerate(frames):
            arr = np.asarray(frame.convert("RGBA"))
            alpha_points = np.argwhere(arr[:, :, 3] > 0)
            if not len(alpha_points):
                raise ValueError(f"Frame {index} is empty")
            y0, x0 = alpha_points.min(axis=0)
            y1, x1 = alpha_points.max(axis=0) + 1
            detection = detections[index]
            manual = offsets[index]
            ideal_dx = round(config.canonical_anchor[0] - detection.anchor[0]) + int(manual[0])
            ideal_dy = round(config.canonical_anchor[1] - detection.anchor[1]) + int(manual[1])
            translated_x0 = int(x0) + ideal_dx
            translated_y0 = int(y0) + ideal_dy
            translated_x1 = int(x1) + ideal_dx
            translated_y1 = int(y1) + ideal_dy
            min_canvas_x = min(min_canvas_x, translated_x0)
            min_canvas_y = min(min_canvas_y, translated_y0)
            max_canvas_x = max(max_canvas_x, translated_x1)
            max_canvas_y = max(max_canvas_y, translated_y1)
            frame_data.append(
                (
                    arr,
                    ideal_dx,
                    ideal_dy,
                )
            )
        canvas_shift_x = -min_canvas_x
        canvas_shift_y = -min_canvas_y
        canvas_width = max_canvas_x - min_canvas_x
        canvas_height = max_canvas_y - min_canvas_y
        for arr, ideal_dx, ideal_dy in frame_data:
            dx = ideal_dx + canvas_shift_x
            dy = ideal_dy + canvas_shift_y
            applied_translations.append((dx, dy))
            canvas = np.zeros((canvas_height, canvas_width, 4), np.uint8)
            yy, xx = np.where(arr[:, :, 3] > 0)
            if len(yy):
                target_y = yy + dy
                target_x = xx + dx
                valid = (
                    (0 <= target_y)
                    & (target_y < canvas_height)
                    & (0 <= target_x)
                    & (target_x < canvas_width)
                )
                if np.any(valid):
                    canvas[target_y[valid], target_x[valid]] = arr[yy[valid], xx[valid]]
            aligned.append(Image.fromarray(canvas, "RGBA"))
    else:
        raise ValueError(f"Unsupported overflow strategy: {overflow_strategy}")
    adjustments: list[FrameAdjustment] = []
    residuals: list[float] = []
    source_deltas: list[float] = []
    manual_deltas: list[float] = []
    for index, (detection, offset, bbox) in enumerate(
        zip(detections, offsets, bboxes, strict=True)
    ):
        dx = round(config.canonical_anchor[0] - detection.anchor[0]) + offset[0]
        dy = round(config.canonical_anchor[1] - detection.anchor[1]) + offset[1]
        if applied_translations is not None:
            dx, dy = applied_translations[index]
        transformed = (detection.anchor[0] + dx, detection.anchor[1] + dy)
        expected = (
            config.canonical_anchor[0] + offset[0] + canvas_shift_x,
            config.canonical_anchor[1] + offset[1] + canvas_shift_y,
        )
        residuals.append(float(np.linalg.norm(np.subtract(transformed, expected))))
        if index:
            source_deltas.append(
                float(
                    np.linalg.norm(
                        np.subtract(detection.anchor, detections[index - 1].anchor)
                    )
                )
            )
            manual_deltas.append(
                float(np.linalg.norm(np.subtract(offset, offsets[index - 1])))
            )
        adjustments.append(
            FrameAdjustment(
                frame_index=index,
                auto_anchor=detection.anchor,
                auto_confidence=detection.confidence,
                manual_offset_x=offset[0],
                manual_offset_y=offset[1],
                final_anchor=expected,
                applied_translation=(dx, dy),
                body_bbox=bbox,
                locked=locks[index],
                notes=frame_notes[index],
                manual_review=(
                    (
                        detection.confidence < config.confidence_threshold
                        or overflow_strategy == "clamp"
                    )
                    and not locks[index]
                ),
            )
        )

    status = (
        "manual_review"
        if any(item.manual_review for item in adjustments)
        else "passed"
    )
    jitter = {
        "source_anchor_mean_delta": float(np.mean(source_deltas)) if source_deltas else 0.0,
        "source_anchor_max_delta": max(source_deltas, default=0.0),
        "manual_offset_max_delta": max(manual_deltas, default=0.0),
        "final_anchor_mean_error": float(np.mean(residuals)),
        "final_anchor_max_error": max(residuals, default=0.0),
        "minimum_confidence": min(item.auto_confidence for item in adjustments),
        "mean_confidence": float(np.mean([item.auto_confidence for item in adjustments])),
    }
    return CenteringResult(tuple(aligned), tuple(adjustments), jitter, status)


def checkerboard(
    size: tuple[int, int],
    *,
    square: int = 8,
    light: tuple[int, int, int, int] = (64, 70, 84, 255),
    dark: tuple[int, int, int, int] = (38, 43, 55, 255),
) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, light)
    draw = ImageDraw.Draw(image)
    for y in range(0, height, square):
        for x in range(0, width, square):
            if (x // square + y // square) % 2:
                draw.rectangle(
                    (x, y, min(width - 1, x + square - 1), min(height - 1, y + square - 1)),
                    fill=dark,
                )
    return image


def render_frame_overlay(
    frame: Image.Image,
    adjustment: FrameAdjustment | None = None,
    *,
    scale: int = 4,
    show_bbox: bool = True,
    show_center_axes: bool = True,
    show_frame_border: bool = True,
    origin_offset: tuple[int, int] = (0, 0),
) -> Image.Image:
    if scale < 1:
        raise ValueError("Scale must be positive")
    rgba = frame.convert("RGBA")
    preview = checkerboard(rgba.size)
    preview.alpha_composite(rgba)
    draw = ImageDraw.Draw(preview)
    origin_x, origin_y = origin_offset
    if show_center_axes:
        center = (rgba.width // 2, rgba.height // 2)
        draw.line((center[0], 0, center[0], rgba.height - 1), fill=(255, 255, 255, 150), width=1)
        draw.line((0, center[1], rgba.width - 1, center[1]), fill=(255, 255, 255, 150), width=1)
    if adjustment is not None:
        target_x = round(
            adjustment.auto_anchor[0] + adjustment.applied_translation[0] - origin_x
        )
        target_y = round(
            adjustment.auto_anchor[1] + adjustment.applied_translation[1] - origin_y
        )
        radius = max(2, min(rgba.size) // 24)
        draw.line(
            (target_x - radius, target_y, target_x + radius, target_y),
            fill=(255, 76, 160, 255),
            width=1,
        )
        draw.line(
            (target_x, target_y - radius, target_x, target_y + radius),
            fill=(255, 76, 160, 255),
            width=1,
        )
        if show_bbox:
            x0, y0, x1, y1 = adjustment.body_bbox
            dx, dy = adjustment.applied_translation
            draw.rectangle(
                (x0 + dx - origin_x, y0 + dy - origin_y, x1 + dx - origin_x - 1, y1 + dy - origin_y - 1),
                outline=(255, 190, 72, 255),
                width=1,
            )
    if show_frame_border:
        draw.rectangle((0, 0, rgba.width - 1, rgba.height - 1), outline=(91, 223, 255, 255))
    return preview.resize((rgba.width * scale, rgba.height * scale), Image.Resampling.NEAREST)


def render_contact_sheet(
    frames: Sequence[Image.Image],
    *,
    adjustments: Sequence[FrameAdjustment] | None = None,
    columns: int = 4,
    scale: int = 2,
    origin_offset: tuple[int, int] = (0, 0),
    show_cell_guides: bool = False,
    show_center_axes: bool = False,
    show_anchor_guides: bool = True,
    show_bbox: bool = True,
    guide_padding: int = 0,
) -> Image.Image:
    if not frames:
        raise ValueError("At least one frame is required")
    if columns < 1 or scale < 1:
        raise ValueError("Columns and scale must be positive")
    width = max(frame.width for frame in frames)
    height = max(frame.height for frame in frames)
    rows = ceil(len(frames) / columns)
    padding = max(0, int(guide_padding)) * scale
    output = Image.new(
        "RGBA",
        (
            columns * width * scale + padding * 2,
            rows * height * scale + padding * 2,
        ),
        (18, 22, 32, 255),
    )
    for index, frame in enumerate(frames):
        adjustment = adjustments[index] if adjustments else None
        rendered = render_frame_overlay(
            frame,
            None,
            scale=scale,
            origin_offset=origin_offset,
            show_bbox=show_bbox,
            show_center_axes=False,
            show_frame_border=False,
        )
        x = padding + (index % columns) * width * scale
        y = padding + (index // columns) * height * scale
        output.alpha_composite(rendered, (x, y))
        draw = ImageDraw.Draw(output)
        draw.text((x + 4, y + 3), str(index), fill=(255, 255, 255, 255))
    if show_cell_guides or show_center_axes or show_anchor_guides:
        guided = output.convert("RGB")
        guide_draw = ImageDraw.Draw(guided)
        for index, _frame in enumerate(frames):
            adjustment = adjustments[index] if adjustments else None
            x = padding + (index % columns) * width * scale
            y = padding + (index // columns) * height * scale
            cell_x1 = x + width * scale - 1
            cell_y1 = y + height * scale - 1
            axis_x = x + (width // 2) * scale
            axis_y = y + (height // 2) * scale
            if show_cell_guides:
                guide_draw.rectangle(
                    (x + 1, y + 1, cell_x1 - 1, cell_y1 - 1),
                    outline=(91, 223, 255),
                    width=max(1, min(2, scale)),
                )
            if show_center_axes:
                axis_width = max(2, min(3, scale + 1))
                guide_draw.line(
                    (axis_x, y + 1, axis_x, cell_y1 - 1),
                    fill=(255, 255, 255),
                    width=axis_width,
                )
                guide_draw.line(
                    (x + 1, axis_y, cell_x1 - 1, axis_y),
                    fill=(255, 255, 255),
                    width=axis_width,
                )
            if show_anchor_guides and adjustment is not None:
                anchor_x = x + round(
                    (
                        adjustment.auto_anchor[0]
                        + adjustment.applied_translation[0]
                        - origin_offset[0]
                    )
                    * scale
                )
                anchor_y = y + round(
                    (
                        adjustment.auto_anchor[1]
                        + adjustment.applied_translation[1]
                        - origin_offset[1]
                    )
                    * scale
                )
                radius = max(3, 4 * scale)
                anchor_width = max(2, min(3, scale + 1))
                guide_draw.line(
                    (anchor_x - radius, anchor_y, anchor_x + radius, anchor_y),
                    fill=(7, 8, 14),
                    width=anchor_width + 2,
                )
                guide_draw.line(
                    (anchor_x, anchor_y - radius, anchor_x, anchor_y + radius),
                    fill=(7, 8, 14),
                    width=anchor_width + 2,
                )
                guide_draw.line(
                    (anchor_x - radius, anchor_y, anchor_x + radius, anchor_y),
                    fill=(255, 76, 160),
                    width=anchor_width,
                )
                guide_draw.line(
                    (anchor_x, anchor_y - radius, anchor_x, anchor_y + radius),
                    fill=(255, 76, 160),
                    width=anchor_width,
                )
        output = guided.convert("RGBA")
    return output


def export_sheet(
    frames: Sequence[Image.Image],
    output_path: str | Path,
    *,
    layout: str = "horizontal",
    columns: int | None = None,
    cell_size: tuple[int, int] | None = None,
) -> SheetResult:
    if layout not in {"horizontal", "vertical", "grid"}:
        raise ValueError(f"Unsupported export layout: {layout}")
    return build_spritesheet(
        frames,
        output_path,
        layout=layout,  # type: ignore[arg-type]
        columns=columns,
        cell_size=cell_size,
    )
