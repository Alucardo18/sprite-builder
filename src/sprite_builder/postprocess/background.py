from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

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
    metrics: dict[str, Any] = field(default_factory=dict)


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


def _key_channel_split(chroma_rgb: tuple[int, int, int]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    keyed = tuple(index for index, value in enumerate(chroma_rgb) if value >= 192)
    unkeyed = tuple(index for index, value in enumerate(chroma_rgb) if value < 64)
    return keyed, unkeyed


def _key_tint_score(rgb: tuple[int, int, int], chroma_rgb: tuple[int, int, int]) -> float:
    keyed, unkeyed = _key_channel_split(chroma_rgb)
    if not keyed or not unkeyed:
        return 0.0
    keyed_mean = sum(rgb[index] for index in keyed) / len(keyed)
    unkeyed_mean = sum(rgb[index] for index in unkeyed) / len(unkeyed)
    return keyed_mean - unkeyed_mean


def _despill_rgb(
    rgb: tuple[int, int, int],
    chroma_rgb: tuple[int, int, int],
    key_tint: float,
    tint: float,
) -> tuple[float, tuple[int, int, int]]:
    if key_tint <= 0:
        return 1.0, rgb
    key_fraction = min(max(tint / key_tint, 0.0), 1.0)
    coverage = 1.0 - key_fraction
    if coverage <= 0:
        return 0.0, (0, 0, 0)
    despilled = tuple(
        min(255, max(0, round((rgb[index] - key_fraction * chroma_rgb[index]) / coverage)))
        for index in range(3)
    )
    return coverage, despilled  # type: ignore[return-value]


def _apply_rgb_unmix(
    rgb: np.ndarray,
    alpha: np.ndarray,
    *,
    background: np.ndarray,
    foreground: np.ndarray,
    distance: np.ndarray,
    declared_key: tuple[int, int, int],
    observed_key: tuple[int, int, int],
    hard_cut_tolerance: float,
    fringe_tolerance: float,
    tint_threshold: float,
    reach: int,
    spill_max_fraction: float,
) -> tuple[int, int, list[str]]:
    """Apply the opt-in SpriteGen-style spatial fringe and spill passes.

    The existing connected hard cut remains authoritative. Only foreground pixels
    near that cut are eligible for soft unmix; interior spill is colour-only and
    never changes alpha.
    """
    warnings: list[str] = []
    if reach <= 0:
        return 0, 0, warnings
    key_tint = _key_tint_score(observed_key, declared_key)
    if key_tint <= 0:
        warnings.append("rgb_unmix_disabled: declared and observed key have no tint axis")
        return 0, 0, warnings

    # DIST_C is the Chebyshev metric: a small ring around a connected matte,
    # including enclosed holes, matches the spatial guard in SpriteGen.
    depth = cv2.distanceTransform((~background).astype(np.uint8), cv2.DIST_C, 3)
    source_tint = np.zeros(distance.shape, dtype=np.float32)
    keyed_channels, unkeyed_channels = _key_channel_split(declared_key)
    if keyed_channels and unkeyed_channels:
        keyed_sum = rgb[..., keyed_channels].sum(axis=-1, dtype=np.int32)
        unkeyed_sum = rgb[..., unkeyed_channels].sum(axis=-1, dtype=np.int32)
        source_tint = keyed_sum / len(keyed_channels) - unkeyed_sum / len(unkeyed_channels)

    fringe = (
        foreground
        & (depth > 0)
        & (depth <= reach)
        & (distance > hard_cut_tolerance)
        & (distance <= hard_cut_tolerance + fringe_tolerance)
        & (source_tint >= tint_threshold)
    )
    partial_alpha_pixels = 0
    despill_pixels = 0
    for y, x in zip(*np.nonzero(fringe), strict=False):
        color = tuple(int(value) for value in rgb[y, x])
        coverage, despilled = _despill_rgb(
            color,
            observed_key,
            key_tint,
            _key_tint_score(color, declared_key),
        )
        if coverage <= 0:
            continue
        original_alpha = int(alpha[y, x])
        updated_alpha = min(original_alpha, round(original_alpha * coverage))
        if 0 < updated_alpha < 255:
            partial_alpha_pixels += 1
        rgb[y, x] = despilled
        alpha[y, x] = updated_alpha
        despill_pixels += 1

    if spill_max_fraction <= 0:
        return partial_alpha_pixels, despill_pixels, warnings
    subject_count = int(np.count_nonzero(foreground))
    spill_limit = max(32, round(subject_count * spill_max_fraction))
    current_tint = np.zeros(distance.shape, dtype=np.float32)
    if keyed_channels and unkeyed_channels:
        keyed_sum = rgb[..., keyed_channels].sum(axis=-1, dtype=np.int32)
        unkeyed_sum = rgb[..., unkeyed_channels].sum(axis=-1, dtype=np.int32)
        current_tint = keyed_sum / len(keyed_channels) - unkeyed_sum / len(unkeyed_channels)
    # Exact near-key pixels remain governed by the connected hard-cut path. This
    # exclusion is what preserves a deliberately enclosed key-coloured island.
    spill_candidates = (
        foreground
        & (alpha > 0)
        & (distance > hard_cut_tolerance)
        & (current_tint >= max(tint_threshold, 40.0))
    ).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(spill_candidates, 8)
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area > spill_limit:
            continue
        points = np.argwhere(labels == label)
        if not len(points) or float(current_tint[labels == label].max()) < 40.0:
            continue
        for y, x in points:
            color = tuple(int(value) for value in rgb[y, x])
            coverage, despilled = _despill_rgb(
                color,
                observed_key,
                key_tint,
                _key_tint_score(color, declared_key),
            )
            if coverage > 0:
                rgb[y, x] = despilled
                despill_pixels += 1
    return partial_alpha_pixels, despill_pixels, warnings


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
    unmix_enabled: bool = False,
    unmix_reach: int = 2,
    unmix_fringe_tolerance: float = 160.0,
    unmix_tint_threshold: float = 18.0,
    spill_max_fraction: float = 0.005,
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
    if unmix_reach < 0:
        raise ValueError("Unmix reach must be non-negative")
    if unmix_fringe_tolerance < 0 or unmix_tint_threshold < 0:
        raise ValueError("Unmix tolerances must be non-negative")
    if spill_max_fraction < 0:
        raise ValueError("Spill fraction must be non-negative")
    if unmix_enabled and color_space != "rgb":
        raise ValueError("RGB unmix requires color_space='rgb'")

    declared_key = tuple(int(value) for value in (chroma_rgb or bg))
    observed_bg = _dominant_border_rgb(rgb) if unmix_enabled else bg

    if color_space == "lab":
        sample = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        target = cv2.cvtColor(np.uint8([[bg]]), cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
    elif color_space == "rgb":
        sample = rgb.astype(np.float32)
        target = np.asarray(bg, dtype=np.float32)
    else:
        raise ValueError(f"Unsupported color space: {color_space}")
    distance = np.linalg.norm(sample - target, axis=2)
    if unmix_enabled:
        observed_target = np.asarray(observed_bg, dtype=np.float32)
        observed_distance = np.linalg.norm(
            rgb.astype(np.float32) - observed_target, axis=2
        )
        distance = np.minimum(distance, observed_distance)
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

    partial_alpha_pixels = int(np.count_nonzero((alpha > 0) & (alpha < 255)))
    despill_pixels = 0
    warnings: list[str] = []
    if unmix_enabled:
        partial_alpha_pixels, despill_pixels, warnings = _apply_rgb_unmix(
            rgb,
            alpha,
            background=background.astype(bool),
            foreground=foreground,
            distance=distance,
            declared_key=declared_key,
            observed_key=tuple(int(value) for value in observed_bg),
            hard_cut_tolerance=threshold,
            fringe_tolerance=unmix_fringe_tolerance,
            tint_threshold=unmix_tint_threshold,
            reach=unmix_reach,
            spill_max_fraction=spill_max_fraction,
        )
        rgb[alpha == 0] = 0

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
    metrics = {
        "method": "rgb_unmix_candidate" if unmix_enabled else "connected_color_distance",
        "declared_key": list(declared_key),
        "observed_background_rgb": [int(value) for value in observed_bg],
        "unmix_reach": int(unmix_reach),
        "hard_cut_tolerance": float(threshold),
        "fringe_tolerance": float(unmix_fringe_tolerance),
        "tint_threshold": float(unmix_tint_threshold),
        "spill_max_fraction": float(spill_max_fraction),
        "hard_cut_pixels": int(np.count_nonzero(background)),
        "partial_alpha_pixels": int(np.count_nonzero((alpha > 0) & (alpha < 255))),
        "despill_pixels": int(despill_pixels),
        "warnings": warnings,
    }
    return BackgroundRemovalResult(
        Image.fromarray(out, "RGBA"), mask.astype(bool), bg, confidence, metrics
    )
