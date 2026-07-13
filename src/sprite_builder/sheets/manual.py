"""Manual pixel-editing helpers shared by the background workflow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

import cv2
import numpy as np
from PIL import Image, ImageDraw

ManualEditKind = Literal["erase_similar", "erase_brush"]


def sample_pixel(image: Image.Image, point: tuple[int, int]) -> tuple[int, int, int, int]:
    rgba = image.convert("RGBA")
    x = min(max(int(point[0]), 0), rgba.width - 1)
    y = min(max(int(point[1]), 0), rgba.height - 1)
    pixel = rgba.getpixel((x, y))
    return int(pixel[0]), int(pixel[1]), int(pixel[2]), int(pixel[3])


def erase_similar_pixels(
    image: Image.Image,
    *,
    seed_point: tuple[int, int],
    tolerance: float,
    contiguous: bool = True,
    target_rgb: tuple[int, int, int] | None = None,
) -> Image.Image:
    if tolerance < 0:
        raise ValueError("Tolerance must be non-negative")
    rgba = np.asarray(image.convert("RGBA")).copy()
    if not rgba.size:
        return image.convert("RGBA")
    height, width = rgba.shape[:2]
    x = min(max(int(seed_point[0]), 0), width - 1)
    y = min(max(int(seed_point[1]), 0), height - 1)
    target = np.asarray(
        target_rgb if target_rgb is not None else rgba[y, x, :3],
        dtype=np.float32,
    )
    rgb = rgba[:, :, :3].astype(np.float32)
    distance = np.linalg.norm(rgb - target, axis=2)
    candidate = (distance <= float(tolerance)).astype(np.uint8)
    if contiguous:
        _, labels = cv2.connectedComponents(candidate, connectivity=8)
        label = labels[y, x]
        if label == 0:
            return Image.fromarray(rgba, "RGBA")
        mask = labels == label
    else:
        mask = candidate.astype(bool)
    rgba[mask, 3] = 0
    return Image.fromarray(rgba, "RGBA")


def erase_with_brush(
    image: Image.Image,
    *,
    center: tuple[int, int],
    radius: int,
    path: Sequence[tuple[int, int]] | None = None,
) -> Image.Image:
    if radius < 1:
        raise ValueError("Brush radius must be positive")
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    draw = ImageDraw.Draw(alpha)

    def _stroke_points() -> tuple[tuple[int, int], ...]:
        if not path:
            return ((int(center[0]), int(center[1])),)

        points = [tuple(map(int, point)) for point in path]
        if len(points) == 1:
            return (points[0],)

        rasterized: list[tuple[int, int]] = []

        def _line_points(
            start: tuple[int, int],
            end: tuple[int, int],
        ) -> tuple[tuple[int, int], ...]:
            x0, y0 = start
            x1, y1 = end
            dx = abs(x1 - x0)
            dy = abs(y1 - y0)
            sx = 1 if x0 < x1 else -1
            sy = 1 if y0 < y1 else -1
            err = dx - dy
            output: list[tuple[int, int]] = []
            while True:
                output.append((x0, y0))
                if x0 == x1 and y0 == y1:
                    break
                twice_err = err * 2
                if twice_err > -dy:
                    err -= dy
                    x0 += sx
                if twice_err < dx:
                    err += dx
                    y0 += sy
            return tuple(output)

        for start, end in zip(points, points[1:]):
            segment = _line_points(start, end)
            if rasterized and segment and rasterized[-1] == segment[0]:
                rasterized.extend(segment[1:])
            else:
                rasterized.extend(segment)
        return tuple(rasterized)

    for x, y in _stroke_points():
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=0)
    rgba.putalpha(alpha)
    return rgba


def select_similar_pixels(
    image: Image.Image,
    *,
    seed_point: tuple[int, int],
    tolerance: float,
    contiguous: bool = True,
    target_rgb: tuple[int, int, int] | None = None,
) -> np.ndarray:
    if tolerance < 0:
        raise ValueError("Tolerance must be non-negative")
    rgba = np.asarray(image.convert("RGBA")).copy()
    if not rgba.size:
        return np.zeros((0, 0), dtype=bool)
    height, width = rgba.shape[:2]
    x = min(max(int(seed_point[0]), 0), width - 1)
    y = min(max(int(seed_point[1]), 0), height - 1)
    target = np.asarray(
        target_rgb if target_rgb is not None else rgba[y, x, :3],
        dtype=np.float32,
    )
    rgb = rgba[:, :, :3].astype(np.float32)
    distance = np.linalg.norm(rgb - target, axis=2)
    candidate = (distance <= float(tolerance)).astype(np.uint8)
    if contiguous:
        _, labels = cv2.connectedComponents(candidate, connectivity=8)
        label = labels[y, x]
        if label == 0:
            return np.zeros((height, width), dtype=bool)
        return labels == label
    return candidate.astype(bool)


def combine_selection_masks(
    current: np.ndarray | None,
    incoming: np.ndarray,
    *,
    mode: Literal["replace", "add", "subtract", "intersect"] = "replace",
) -> np.ndarray:
    if current is None or current.size == 0 or mode == "replace":
        return incoming.astype(bool, copy=True)
    if current.shape != incoming.shape:
        raise ValueError("Selection masks must have the same shape")
    if mode == "add":
        return np.logical_or(current, incoming)
    if mode == "subtract":
        return np.logical_and(current, ~incoming)
    if mode == "intersect":
        return np.logical_and(current, incoming)
    raise ValueError(f"Unsupported selection mode: {mode}")


def clear_selection(image: Image.Image, mask: np.ndarray) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA")).copy()
    if mask.shape != rgba.shape[:2]:
        raise ValueError("Selection mask must match image size")
    rgba[mask, 3] = 0
    return Image.fromarray(rgba, "RGBA")


def encode_mask(mask: np.ndarray) -> dict[str, Any]:
    if mask.ndim != 2:
        raise ValueError("Mask must be 2D")
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return {"bbox": [0, 0, 0, 0], "rows": []}
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    cropped = mask[y0:y1, x0:x1]
    rows: list[list[list[int]]] = []
    for row in cropped:
        spans: list[list[int]] = []
        start: int | None = None
        for index, value in enumerate(row.tolist() + [False]):
            if value and start is None:
                start = index
            elif not value and start is not None:
                spans.append([start, index])
                start = None
        rows.append(spans)
    return {"bbox": [x0, y0, x1, y1], "rows": rows}


def decode_mask(payload: Mapping[str, Any], size: tuple[int, int]) -> np.ndarray:
    width, height = size
    mask = np.zeros((height, width), dtype=bool)
    bbox = payload.get("bbox", (0, 0, 0, 0))
    rows = payload.get("rows", ())
    if (
        not isinstance(bbox, (list, tuple))
        or len(bbox) != 4
        or not isinstance(rows, (list, tuple))
    ):
        return mask
    x0, y0, x1, y1 = map(int, bbox)
    crop_width = max(0, x1 - x0)
    crop_height = max(0, y1 - y0)
    for row_index, spans in enumerate(rows[:crop_height]):
        target_y = y0 + row_index
        if not 0 <= target_y < height or not isinstance(spans, (list, tuple)):
            continue
        for span in spans:
            if not isinstance(span, (list, tuple)) or len(span) != 2:
                continue
            start, end = map(int, span)
            start_x = min(width, max(0, x0 + start))
            end_x = min(width, max(0, x0 + end))
            if start_x < end_x:
                mask[target_y, start_x:end_x] = True
    return mask


def render_selection_overlay(
    size: tuple[int, int],
    mask: np.ndarray | None,
) -> Image.Image:
    width, height = size
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    if mask is None or not mask.size:
        return Image.fromarray(overlay, "RGBA")
    if mask.shape != (height, width):
        raise ValueError("Selection overlay mask must match the canvas size")
    overlay[mask] = np.array((91, 223, 255, 64), dtype=np.uint8)
    mask_u8 = mask.astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.morphologyEx(mask_u8, cv2.MORPH_GRADIENT, kernel).astype(bool)
    rows, columns = np.indices((height, width))
    light_ants = edges & (((rows + columns) // 2) % 2 == 0)
    dark_ants = edges & ~light_ants
    overlay[light_ants] = np.array((255, 255, 255, 255), dtype=np.uint8)
    overlay[dark_ants] = np.array((12, 16, 24, 255), dtype=np.uint8)
    return Image.fromarray(overlay, "RGBA")


def apply_manual_background_edits(
    frames: Sequence[Image.Image],
    operations_by_frame: Mapping[int, Sequence[Mapping[str, Any]]],
) -> tuple[Image.Image, ...]:
    output: list[Image.Image] = []
    for index, frame in enumerate(frames):
        edited = frame.convert("RGBA")
        for operation in operations_by_frame.get(index, ()):
            kind = str(operation.get("kind", ""))
            if kind == "erase_similar":
                edited = erase_similar_pixels(
                    edited,
                    seed_point=tuple(map(int, operation.get("point", (0, 0)))),
                    tolerance=float(operation.get("tolerance", 0)),
                    contiguous=bool(operation.get("contiguous", True)),
                    target_rgb=(
                        tuple(map(int, operation["target_rgb"]))
                        if operation.get("target_rgb") is not None
                        else None
                    ),
                )
            elif kind == "erase_brush":
                stroke = operation.get("path")
                path = None
                if isinstance(stroke, (list, tuple)) and stroke:
                    path = tuple(
                        tuple(map(int, point))
                        for point in stroke
                        if isinstance(point, (list, tuple)) and len(point) == 2
                    )
                edited = erase_with_brush(
                    edited,
                    center=tuple(map(int, operation.get("point", (0, 0)))),
                    radius=int(operation.get("radius", 1)),
                    path=path,
                )
            elif kind == "erase_mask":
                edited = clear_selection(
                    edited,
                    decode_mask(operation, edited.size),
                )
            else:
                raise ValueError(f"Unsupported manual background edit: {kind}")
        output.append(edited)
    return tuple(output)
