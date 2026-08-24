"""Deterministic silhouette and ground-support quality gates.

These measurements deliberately use alpha geometry rather than colour names.
They cannot prove anatomy, but they can reject clipping and route suspicious,
flat terminal silhouettes to manual review even when transparent gutter exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from sprite_builder.domain.models import SemanticIntegritySpec


@dataclass(frozen=True, slots=True)
class SemanticFrameMetrics:
    index: int
    status: str
    reasons: tuple[str, ...]
    bottom_gutter_px: int
    support_y: int
    support_y_delta_px: float
    support_component_count: int
    terminal_width_px: int
    support_band_max_width_px: int
    terminal_taper_ratio: float
    flat_terminal_suspected: bool
    body_roi: tuple[int, int, int, int]
    full_foreground_bbox: tuple[int, int, int, int]
    landmarks: dict[str, tuple[float, float]]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        value["body_roi"] = list(self.body_roi)
        value["full_foreground_bbox"] = list(self.full_foreground_bbox)
        value["landmarks"] = {
            key: list(point) for key, point in self.landmarks.items()
        }
        return value


@dataclass(frozen=True, slots=True)
class SemanticIntegrityReport:
    status: str
    reference_support_y: float
    frames: tuple[SemanticFrameMetrics, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reference_support_y": self.reference_support_y,
            "frames": [frame.to_dict() for frame in self.frames],
        }


def _rgba(value: str | Path | Image.Image | np.ndarray) -> np.ndarray:
    if isinstance(value, (str, Path)):
        with Image.open(value) as image:
            return np.asarray(image.convert("RGBA")).copy()
    if isinstance(value, Image.Image):
        return np.asarray(value.convert("RGBA")).copy()
    array = np.asarray(value)
    if array.ndim != 3 or array.shape[2] not in (3, 4):
        raise ValueError("Expected an RGB or RGBA image")
    if array.shape[2] == 3:
        array = np.dstack((array, np.full(array.shape[:2], 255, np.uint8)))
    return array.astype(np.uint8, copy=False)


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    if not len(xs):
        raise ValueError("Semantic integrity cannot inspect an empty frame")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def measure_semantic_frame(
    frame: str | Path | Image.Image | np.ndarray,
    config: SemanticIntegritySpec,
    *,
    index: int = 0,
) -> SemanticFrameMetrics:
    array = _rgba(frame)
    height, width = array.shape[:2]
    full_mask = array[:, :, 3] > config.alpha_threshold
    full_bbox = _bbox(full_mask)
    roi_x0 = max(0, min(width - 1, round(width * config.body_roi_x[0])))
    roi_x1 = max(roi_x0 + 1, min(width, round(width * config.body_roi_x[1])))
    body_mask = full_mask[:, roi_x0:roi_x1]
    if not body_mask.any():
        raise ValueError("Configured body_roi_x contains no foreground")

    ys = np.where(body_mask)[0]
    support_y = int(ys.max())
    bottom_gutter = height - support_y - 1
    band_y0 = max(0, support_y - config.support_band_height_px + 1)
    band = body_mask[band_y0 : support_y + 1]
    row_widths = np.count_nonzero(band, axis=1)
    band_max_width = max(1, int(row_widths.max()))
    terminal_row = body_mask[support_y]
    terminal_width = int(np.count_nonzero(terminal_row))
    taper_ratio = float(terminal_width / band_max_width)

    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(
        band.astype(np.uint8), 8
    )
    components: list[tuple[int, float, float]] = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < 2:
            continue
        cx, cy = centroids[label]
        components.append((area, float(cx + roi_x0), float(cy + band_y0)))
    components.sort(key=lambda item: item[1])

    top_y = int(ys.min())
    top_band = body_mask[top_y : min(height, top_y + config.support_band_height_px)]
    top_ys, top_xs = np.where(top_band)
    torso_y0 = int(np.quantile(ys, 0.30))
    torso_y1 = int(np.quantile(ys, 0.62))
    torso_band = body_mask[torso_y0 : torso_y1 + 1]
    torso_ys, torso_xs = np.where(torso_band)
    support_xs = np.where(terminal_row)[0]
    landmarks: dict[str, tuple[float, float]] = {
        "ground_support": (float(np.median(support_xs) + roi_x0), float(support_y)),
        "top_extent": (
            float(np.median(top_xs) + roi_x0),
            float(np.median(top_ys) + top_y),
        ),
        "body_core": (
            float(np.median(torso_xs) + roi_x0),
            float(np.median(torso_ys) + torso_y0),
        ),
    }
    if components:
        landmarks["left_support"] = (components[0][1], components[0][2])
        landmarks["right_support"] = (components[-1][1], components[-1][2])

    flat_terminal = taper_ratio > config.max_terminal_taper_ratio
    reasons: list[str] = []
    status = "pass"
    if bottom_gutter < config.min_bottom_gutter_px:
        status = "reject"
        reasons.append("bottom_gutter_below_minimum")
    if len(components) < config.required_support_components:
        if status != "reject":
            status = "review"
        reasons.append("support_components_below_required")
    if flat_terminal:
        if status != "reject":
            status = "review"
        reasons.append("flat_terminal_silhouette")
    return SemanticFrameMetrics(
        index=index,
        status=status,
        reasons=tuple(reasons),
        bottom_gutter_px=bottom_gutter,
        support_y=support_y,
        support_y_delta_px=0.0,
        support_component_count=len(components),
        terminal_width_px=terminal_width,
        support_band_max_width_px=band_max_width,
        terminal_taper_ratio=taper_ratio,
        flat_terminal_suspected=flat_terminal,
        body_roi=(roi_x0, 0, roi_x1, height),
        full_foreground_bbox=full_bbox,
        landmarks=landmarks,
    )


def validate_semantic_integrity(
    frames: Sequence[str | Path | Image.Image | np.ndarray],
    config: SemanticIntegritySpec,
) -> SemanticIntegrityReport:
    if not frames:
        raise ValueError("At least one frame is required")
    measured = [
        measure_semantic_frame(frame, config, index=index)
        for index, frame in enumerate(frames)
    ]
    reference_y = float(np.median([frame.support_y for frame in measured]))
    finalized: list[SemanticFrameMetrics] = []
    for frame in measured:
        delta = abs(frame.support_y - reference_y)
        reasons = list(frame.reasons)
        status = frame.status
        if delta > config.max_support_y_jitter_px:
            if status != "reject":
                status = "review"
            reasons.append("ground_support_jitter")
        finalized.append(
            replace(
                frame,
                status=status,
                reasons=tuple(reasons),
                support_y_delta_px=float(delta),
            )
        )
    status = (
        "reject"
        if any(frame.status == "reject" for frame in finalized)
        else "review"
        if any(frame.status == "review" for frame in finalized)
        else "pass"
    )
    return SemanticIntegrityReport(status, reference_y, tuple(finalized))
