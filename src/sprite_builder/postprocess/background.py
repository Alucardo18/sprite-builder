from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from PIL import Image

ImageInput = str | Path | Image.Image | np.ndarray


@dataclass(frozen=True)
class BackgroundRemovalResult:
    image: Image.Image
    foreground_mask: np.ndarray
    background_rgb: tuple[int, int, int]
    confidence: float


def _rgba(value: ImageInput) -> np.ndarray:
    if isinstance(value, (str, Path)):
        value = Image.open(value)
    if isinstance(value, Image.Image):
        return np.asarray(value.convert("RGBA")).copy()
    array = np.asarray(value)
    if array.ndim != 3 or array.shape[2] not in (3, 4):
        raise ValueError("Expected an RGB/RGBA image")
    if array.shape[2] == 3:
        array = np.dstack((array, np.full(array.shape[:2], 255, np.uint8)))
    return array.astype(np.uint8, copy=True)


def _dominant_border_rgb(rgb: np.ndarray) -> tuple[int, int, int]:
    border = np.concatenate((rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]))
    if len(border) < 4:
        return tuple(int(x) for x in np.median(border, axis=0))
    data = cv2.cvtColor(border.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    count = min(3, len(np.unique(data, axis=0)))
    _, labels, centers = cv2.kmeans(
        data.astype(np.float32), count, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    winning = int(np.argmax(np.bincount(labels.ravel(), minlength=count)))
    lab = np.uint8([[np.clip(centers[winning], 0, 255)]])
    return tuple(int(x) for x in cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)[0, 0])


def remove_background(
    image: ImageInput,
    *,
    chroma_rgb: tuple[int, int, int] | None = None,
    lab_tolerance: float = 24.0,
    tolerance: float | None = None,
    color_space: Literal["lab", "rgb"] = "lab",
    feather_px: int = 1,
    min_component_ratio: float = 0.0005,
    cleanup_enabled: bool = True,
    fringe_cleanup_strength: int = 1,
    remove_near_transparent: bool = False,
    near_transparent_threshold: int = 8,
    preserve_outline: bool = False,
    border_connected_only: bool = True,
) -> BackgroundRemovalResult:
    """Remove a flat/chroma background connected to the canvas border.

    Colour similarity alone never deletes enclosed pixels: only candidate
    pixels connected to a border seed become background by default.

    Existing callers keep the LAB/feathered behaviour. Pixel-art tools should
    use ``color_space="rgb"``, ``feather_px=0`` and ``preserve_outline=True``.
    """
    rgba = _rgba(image)
    rgb = rgba[:, :, :3]
    bg = chroma_rgb or _dominant_border_rgb(rgb)
    threshold = float(lab_tolerance if tolerance is None else tolerance)
    if threshold < 0:
        raise ValueError("Background tolerance must be non-negative")
    if fringe_cleanup_strength < 0:
        raise ValueError("Fringe cleanup strength must be non-negative")
    if not 0 <= near_transparent_threshold <= 255:
        raise ValueError("Near-transparent threshold must be between 0 and 255")

    if color_space == "lab":
        sample = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        target = cv2.cvtColor(np.uint8([[bg]]), cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
    elif color_space == "rgb":
        sample = rgb.astype(np.float32)
        target = np.asarray(bg, dtype=np.float32)
    else:
        raise ValueError(f"Unsupported color space: {color_space}")
    distance = np.linalg.norm(sample - target, axis=2)
    candidate = (distance <= threshold).astype(np.uint8)

    # Connected components plus explicit border labels are an efficient
    # multi-source flood fill.
    if border_connected_only:
        _, labels = cv2.connectedComponents(candidate, connectivity=8)
        border_labels = np.unique(
            np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1]))
        )
        border_labels = border_labels[border_labels != 0]
        background = np.isin(labels, border_labels)
    else:
        background = candidate.astype(bool)
    foreground = (~background) & (rgba[:, :, 3] > 0)

    mask = foreground.astype(np.uint8)
    if cleanup_enabled and not preserve_outline:
        radius = max(1, int(round(min(rgba.shape[:2]) * 0.003)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1,) * 2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    if cleanup_enabled and min_component_ratio > 0:
        # Remove tiny disconnected dirt. Outline-preserving mode keeps the
        # original geometry of every component that survives this area gate.
        count, comp, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        keep = np.zeros_like(mask)
        min_area = max(1, int(mask.size * min_component_ratio))
        for label in range(1, count):
            if stats[label, cv2.CC_STAT_AREA] >= min_area:
                keep[comp == label] = 1
        mask = keep

    if feather_px > 0:
        signed = cv2.distanceTransform(mask, cv2.DIST_L2, 3) - cv2.distanceTransform(
            1 - mask, cv2.DIST_L2, 3
        )
        alpha = np.clip((signed + feather_px) * 255 / (2 * feather_px), 0, 255)
    else:
        alpha = mask * 255
    alpha = np.minimum(alpha.astype(np.uint8), rgba[:, :, 3])
    if remove_near_transparent:
        alpha[alpha <= near_transparent_threshold] = 0

    # Defringe without blur. Semitransparent pixels and suspicious hard-edge
    # pixels in a narrow matte band inherit colour from the nearest interior
    # foreground pixel. Alpha values are never softened here.
    solid = alpha >= 240
    if cleanup_enabled and fringe_cleanup_strength > 0 and solid.any():
        expanded_tolerance = threshold + 8.0 * fringe_cleanup_strength
        # Exact chroma islands that were deliberately preserved because they
        # are enclosed are not fringe. Only the narrow band just outside the
        # chroma candidate range is eligible for RGB cleanup.
        fringe = (alpha > 0) & (candidate == 0) & (distance <= expanded_tolerance)
        if feather_px > 0:
            fringe |= (alpha > 0) & (alpha < 240)
        interior = solid & ~fringe
        if not interior.any():
            interior = solid
        _, nearest = cv2.distanceTransformWithLabels(
            (~interior).astype(np.uint8),
            cv2.DIST_L2,
            5,
            labelType=cv2.DIST_LABEL_PIXEL,
        )
        coords = np.argwhere(interior)
        if coords.size and fringe.any():
            idx = np.clip(nearest[fringe] - 1, 0, len(coords) - 1)
            rgb[fringe] = rgb[coords[idx, 0], coords[idx, 1]]

    out = np.dstack((rgb, alpha)).astype(np.uint8)
    border_candidate_ratio = float(
        candidate[
            np.r_[np.zeros(rgb.shape[1], int), np.full(rgb.shape[1], rgb.shape[0] - 1)],
            np.tile(np.arange(rgb.shape[1]), 2),
        ].mean()
    )
    confidence = float(np.clip(0.55 + 0.35 * border_candidate_ratio + 0.1 * (mask.any()), 0, 1))
    return BackgroundRemovalResult(Image.fromarray(out, "RGBA"), mask.astype(bool), bg, confidence)
