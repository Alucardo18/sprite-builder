from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class TorsoCalibration:
    anchor: tuple[float, float]
    torso_width: float
    torso_height: float
    template_rgba: np.ndarray
    template_anchor: tuple[float, float]


@dataclass(frozen=True)
class AnchorDetection:
    anchor: tuple[float, float]
    confidence: float
    template_score: float
    flow_inlier_ratio: float
    core_score: float
    source: str = "automatic"


@dataclass(frozen=True)
class BodyAnchorEstimate:
    anchor: tuple[float, float]
    confidence: float
    body_bbox: tuple[int, int, int, int]
    component_area: int
    torso_width: float
    torso_height: float
    # Robust central-quantile dimensions used for character-scale
    # normalization. Thin extensions such as a raised staff contribute little
    # area and therefore do not dominate this measurement.
    scale_reference_width: float
    scale_reference_height: float


@dataclass(frozen=True)
class FeetAnchorEstimate:
    """Ground-contact anchor inferred from the lower body silhouette.

    The support search is restricted to the robust body corridor so a staff,
    raised hand, cape tip, or other extended geometry cannot pull the anchor.
    """

    anchor: tuple[float, float]
    confidence: float
    body_bbox: tuple[int, int, int, int]
    support_bbox: tuple[int, int, int, int]
    ground_y: int
    support_width: float


def _array(image: str | Path | Image.Image | np.ndarray) -> np.ndarray:
    if isinstance(image, (str, Path)):
        image = Image.open(image)
    if isinstance(image, Image.Image):
        return np.asarray(image.convert("RGBA")).copy()
    arr = np.asarray(image)
    if arr.shape[-1] == 3:
        arr = np.dstack((arr, np.full(arr.shape[:2], 255, np.uint8)))
    return arr.astype(np.uint8)


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    ordered_values = values[order]
    ordered_weights = weights[order]
    cutoff = float(ordered_weights.sum()) / 2
    index = int(np.searchsorted(np.cumsum(ordered_weights), cutoff, side="left"))
    return float(ordered_values[min(index, len(ordered_values) - 1)])


def estimate_body_anchor(
    image: str | Path | Image.Image | np.ndarray,
    *,
    alpha_threshold: int = 8,
    min_component_ratio: float = 0.0005,
) -> BodyAnchorEstimate:
    """Estimate a body/torso anchor without using the full foreground bbox center.

    The distance-transform core suppresses thin weapons, VFX, hair tips, and
    extended limbs. The source sprite is never modified.
    """

    arr = _array(image)
    mask = (arr[:, :, 3] > alpha_threshold).astype(np.uint8)
    if not mask.any():
        raise ValueError("Cannot estimate a body anchor on an empty frame")

    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    minimum = max(4, int(round(mask.size * min_component_ratio)))
    candidates: list[tuple[float, int]] = []
    total_area = 0
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < minimum:
            continue
        component = (labels == label).astype(np.uint8)
        thickness = float(cv2.distanceTransform(component, cv2.DIST_L2, 3).max())
        score = area * (1 + min(thickness, 12.0) / 12.0)
        candidates.append((score, label))
        total_area += area
    if not candidates:
        raise ValueError("No body-sized foreground component was found")

    _, selected = max(candidates)
    component = (labels == selected).astype(np.uint8)
    ys, xs = np.where(component > 0)
    x_lo, x_hi = np.quantile(xs, (0.10, 0.90))
    y_lo, y_hi = np.quantile(ys, (0.10, 0.90))
    # A thin staff can be connected to the body and still stretch across many
    # rows. Use row occupancy to recover the broad body silhouette first; only
    # fall back to central quantiles for very sparse/non-character shapes.
    row_counts = np.bincount(ys, minlength=arr.shape[0])
    broad_rows = np.where(row_counts >= max(3, int(np.ceil(row_counts.max() * 0.20))))[0]
    if len(broad_rows) >= 3:
        body_y0, body_y1 = int(broad_rows[0]), int(broad_rows[-1]) + 1
        robust_height = max(2.0, float(body_y1 - body_y0))
    else:
        robust_height = max(2.0, float(y_hi - y_lo + 1))
    torso_y0 = y_lo + 0.28 * robust_height
    torso_y1 = y_lo + 0.72 * robust_height

    distance = cv2.distanceTransform(component, cv2.DIST_L2, 3)
    positive = distance[component > 0]
    core_threshold = max(1.0, float(np.quantile(positive, 0.55)))
    core = (
        (component > 0)
        & (distance >= core_threshold)
        & (np.indices(component.shape)[0] >= torso_y0)
        & (np.indices(component.shape)[0] <= torso_y1)
    )
    core_ys, core_xs = np.where(core)
    if len(core_xs) < 3:
        torso_band = (component > 0) & (np.indices(component.shape)[0] >= torso_y0) & (
            np.indices(component.shape)[0] <= torso_y1
        )
        core_ys, core_xs = np.where(torso_band)
    if not len(core_xs):
        core_ys, core_xs = ys, xs

    weights = np.maximum(distance[core_ys, core_xs], 1.0) ** 2
    anchor = (
        _weighted_median(core_xs.astype(float), weights),
        _weighted_median(core_ys.astype(float), weights),
    )
    body_bbox = (
        int(xs.min()),
        int(ys.min()),
        int(xs.max()) + 1,
        int(ys.max()) + 1,
    )
    torso_width = max(4.0, float(x_hi - x_lo + 1) * 0.55)
    torso_height = max(4.0, robust_height * 0.40)
    dominance = int(stats[selected, cv2.CC_STAT_AREA]) / max(total_area, 1)
    core_support = min(1.0, len(core_xs) / max(8.0, len(xs) * 0.08))
    thickness_score = min(1.0, float(distance.max()) / max(2.0, min(arr.shape[:2]) * 0.08))
    confidence = float(
        np.clip(
            0.45 * dominance + 0.30 * core_support + 0.25 * thickness_score,
            0,
            1,
        )
    )
    return BodyAnchorEstimate(
        anchor=anchor,
        confidence=confidence,
        body_bbox=body_bbox,
        component_area=int(stats[selected, cv2.CC_STAT_AREA]),
        torso_width=torso_width,
        torso_height=torso_height,
        scale_reference_width=max(2.0, float(x_hi - x_lo + 1)),
        scale_reference_height=robust_height,
    )


def estimate_feet_anchor(
    image: str | Path | Image.Image | np.ndarray,
    *,
    alpha_threshold: int = 8,
) -> FeetAnchorEstimate:
    """Estimate the character ground contact without using full-frame bounds.

    A robust torso estimate defines a horizontal body corridor. Within that
    corridor, the last sufficiently broad foreground row is treated as the
    ground line. This rejects narrow vertical props that extend below the feet.
    The returned anchor is a translation target only; no resize is performed.
    """

    arr = _array(image)
    mask = arr[:, :, 3] > alpha_threshold
    if not mask.any():
        raise ValueError("Cannot estimate a feet anchor on an empty frame")

    body = estimate_body_anchor(arr, alpha_threshold=alpha_threshold)
    corridor_half_width = max(4.0, body.scale_reference_width * 0.68)
    x0 = max(0, int(np.floor(body.anchor[0] - corridor_half_width)))
    x1 = min(arr.shape[1], int(np.ceil(body.anchor[0] + corridor_half_width)) + 1)
    corridor = mask[:, x0:x1]
    row_counts = corridor.sum(axis=1)
    maximum_row_support = int(row_counts.max())
    if maximum_row_support <= 0:
        raise ValueError("No lower-body support was found")

    broad_threshold = max(2, int(np.ceil(maximum_row_support * 0.20)))
    broad_rows = np.where(row_counts >= broad_threshold)[0]
    if not len(broad_rows):
        broad_rows = np.where(row_counts == maximum_row_support)[0]
    ground_y = int(broad_rows[-1])

    band_height = max(3, int(np.ceil(body.scale_reference_height * 0.18)))
    band_y0 = max(0, ground_y - band_height + 1)
    support_band = corridor[band_y0 : ground_y + 1]
    row_weight = np.linspace(0.35, 1.0, support_band.shape[0], dtype=np.float64)
    column_weights = (support_band * row_weight[:, None]).sum(axis=0)
    support_columns = np.where(column_weights > 0)[0]
    if not len(support_columns):
        raise ValueError("No foot pixels were found in the support band")

    anchor_x = _weighted_median(
        support_columns.astype(float) + float(x0),
        column_weights[support_columns],
    )
    support_points_y, support_points_x = np.where(support_band)
    support_bbox = (
        int(support_points_x.min()) + x0,
        int(support_points_y.min()) + band_y0,
        int(support_points_x.max()) + x0 + 1,
        int(support_points_y.max()) + band_y0 + 1,
    )
    support_width = float(support_bbox[2] - support_bbox[0])
    broadness = min(
        1.0,
        float(row_counts[ground_y]) / max(float(broad_threshold), 1.0),
    )
    width_support = min(
        1.0,
        support_width / max(body.scale_reference_width * 0.45, 1.0),
    )
    center_offset = abs(anchor_x - body.anchor[0]) / max(
        body.scale_reference_width,
        1.0,
    )
    confidence = float(
        np.clip(
            0.55 * body.confidence
            + 0.25 * broadness
            + 0.20 * width_support
            - 0.20 * min(1.0, center_offset),
            0,
            1,
        )
    )
    return FeetAnchorEstimate(
        anchor=(anchor_x, float(ground_y)),
        confidence=confidence,
        body_bbox=body.body_bbox,
        support_bbox=support_bbox,
        ground_y=ground_y,
        support_width=support_width,
    )


def calibrate_torso_automatically(
    image: str | Path | Image.Image | np.ndarray,
) -> tuple[TorsoCalibration, BodyAnchorEstimate]:
    estimate = estimate_body_anchor(image)
    x, y = estimate.anchor
    half_width = estimate.torso_width / 2
    half_height = estimate.torso_height / 2
    shoulders = ((x - half_width, y - half_height), (x + half_width, y - half_height))
    hips = (
        (x - half_width * 0.62, y + half_height),
        (x + half_width * 0.62, y + half_height),
    )
    return calibrate_torso(image, shoulders, hips), estimate


def calibrate_torso(
    image: str | Path | Image.Image | np.ndarray,
    shoulders: tuple[tuple[float, float], tuple[float, float]],
    hips: tuple[tuple[float, float], tuple[float, float]],
) -> TorsoCalibration:
    arr = _array(image)
    points = np.asarray((*shoulders, *hips), dtype=float)
    anchor = tuple(points.mean(axis=0))
    width = float(np.linalg.norm(np.subtract(*shoulders)))
    shoulder_mid, hip_mid = np.mean(shoulders, axis=0), np.mean(hips, axis=0)
    height = float(np.linalg.norm(hip_mid - shoulder_mid))
    if width < 2 or height < 2:
        raise ValueError("Torso calibration points are degenerate")
    roi_w, roi_h = max(4, round(width * 1.4)), max(4, round(height * 1.5))
    x0 = max(0, round(anchor[0] - roi_w / 2))
    y0 = max(0, round(anchor[1] - roi_h / 2))
    x1, y1 = min(arr.shape[1], x0 + roi_w), min(arr.shape[0], y0 + roi_h)
    template = arr[y0:y1, x0:x1].copy()
    return TorsoCalibration(anchor, width, height, template, (anchor[0] - x0, anchor[1] - y0))


def _flow_prediction(previous: np.ndarray, current: np.ndarray, anchor: tuple[float, float]):
    if previous.shape[:2] != current.shape[:2]:
        return anchor, 0.0
    old = cv2.cvtColor(previous[:, :, :3], cv2.COLOR_RGB2GRAY)
    new = cv2.cvtColor(current[:, :, :3], cv2.COLOR_RGB2GRAY)
    mask = (previous[:, :, 3] > 8).astype(np.uint8) * 255
    features = cv2.goodFeaturesToTrack(old, 50, 0.01, 3, mask=mask)
    if features is None:
        return anchor, 0.0
    try:
        nxt, status, _ = cv2.calcOpticalFlowPyrLK(old, new, features, None)
        back, status2, _ = cv2.calcOpticalFlowPyrLK(new, old, nxt, None)
    except cv2.error:
        return anchor, 0.0
    if nxt is None or back is None or status is None or status2 is None:
        return anchor, 0.0
    error = np.linalg.norm(features - back, axis=2).ravel()
    valid = (status.ravel() == 1) & (status2.ravel() == 1) & (error <= 1.5)
    if not valid.any():
        return anchor, 0.0
    delta = np.median((nxt - features)[valid], axis=0).ravel()
    return (anchor[0] + float(delta[0]), anchor[1] + float(delta[1])), float(valid.mean())


def detect_torso_anchor(
    frame: str | Path | Image.Image | np.ndarray,
    calibration: TorsoCalibration,
    *,
    previous_frame: str | Path | Image.Image | np.ndarray | None = None,
    previous_anchor: tuple[float, float] | None = None,
    override: tuple[float, float] | None = None,
    search_radius_ratio: float = 0.30,
) -> AnchorDetection:
    if override is not None:
        return AnchorDetection(tuple(map(float, override)), 1, 1, 1, 1, "manual")
    arr = _array(frame)
    predicted = previous_anchor or calibration.anchor
    flow_ratio = 0.0
    if previous_frame is not None and previous_anchor is not None:
        predicted, flow_ratio = _flow_prediction(_array(previous_frame), arr, previous_anchor)

    tpl = calibration.template_rgba
    th, tw = tpl.shape[:2]
    radius = max(
        2, round(max(calibration.torso_width, calibration.torso_height) * search_radius_ratio)
    )
    x0 = max(0, round(predicted[0] - calibration.template_anchor[0] - radius))
    y0 = max(0, round(predicted[1] - calibration.template_anchor[1] - radius))
    x1 = min(arr.shape[1], round(predicted[0] - calibration.template_anchor[0] + tw + radius))
    y1 = min(arr.shape[0], round(predicted[1] - calibration.template_anchor[1] + th + radius))
    search = arr[y0:y1, x0:x1]
    if search.shape[0] < th or search.shape[1] < tw:
        return AnchorDetection(predicted, 0.0, 0.0, flow_ratio, 0.0)

    # RGB template matching masked by canonical torso alpha. Extended weapons
    # outside this ROI cannot move the response.
    tpl_gray = cv2.cvtColor(tpl[:, :, :3], cv2.COLOR_RGB2GRAY)
    search_gray = cv2.cvtColor(search[:, :, :3], cv2.COLOR_RGB2GRAY)
    response = cv2.matchTemplate(search_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)

    fg = (arr[:, :, 3] > 8).astype(np.uint8)
    radius_open = max(1, round(min(calibration.torso_width, calibration.torso_height) * 0.08))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius_open + 1,) * 2)
    core = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel)
    dist = cv2.distanceTransform(core, cv2.DIST_L2, 3)
    best_score, best = -1e9, (0, 0)
    best_template, best_core = 0.0, 0.0
    max_dist = max(1.0, float(dist.max()))
    for yy in range(response.shape[0]):
        for xx in range(response.shape[1]):
            ax = x0 + xx + calibration.template_anchor[0]
            ay = y0 + yy + calibration.template_anchor[1]
            core_score = float(
                dist[min(arr.shape[0] - 1, round(ay)), min(arr.shape[1] - 1, round(ax))] / max_dist
            )
            prior = np.exp(
                -((ax - predicted[0]) ** 2 + (ay - predicted[1]) ** 2) / (2 * max(radius, 1) ** 2)
            )
            template_score = float((response[yy, xx] + 1) / 2)
            score = 0.60 * template_score + 0.20 * core_score + 0.20 * prior
            if score > best_score:
                best_score, best = score, (xx, yy)
                best_template, best_core = template_score, core_score
    anchor = (
        float(x0 + best[0] + calibration.template_anchor[0]),
        float(y0 + best[1] + calibration.template_anchor[1]),
    )
    agreement = float(np.exp(-np.linalg.norm(np.subtract(anchor, predicted)) / max(radius, 1)))
    confidence = float(
        np.clip(
            0.45 * best_template + 0.20 * best_core + 0.20 * agreement + 0.15 * flow_ratio, 0, 1
        )
    )
    return AnchorDetection(anchor, confidence, best_template, flow_ratio, best_core)


def load_anchor_overrides(path: str | Path) -> dict[int, tuple[float, float]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = data.get("frames", data) if isinstance(data, dict) else data
    if isinstance(records, dict):
        return {
            int(k): tuple(map(float, v["override"] if isinstance(v, dict) else v))
            for k, v in records.items()
        }
    return {int(v["frame"]): tuple(map(float, v["override"])) for v in records}


def align_frames_by_anchor(
    frames: Sequence[str | Path | Image.Image | np.ndarray],
    anchors: Sequence[tuple[float, float] | AnchorDetection],
    *,
    canvas_size: tuple[int, int],
    target_anchor: tuple[float, float],
    manual_offsets: Sequence[tuple[int, int]] | None = None,
) -> list[Image.Image]:
    if len(frames) != len(anchors):
        raise ValueError("Frame and anchor counts differ")
    offsets = tuple(manual_offsets or ((0, 0),) * len(frames))
    if len(offsets) != len(frames):
        raise ValueError("Frame and manual-offset counts differ")
    width, height = canvas_size
    outputs: list[Image.Image] = []
    for index, (frame, detected, manual) in enumerate(
        zip(frames, anchors, offsets, strict=True)
    ):
        arr = _array(frame)
        anchor = detected.anchor if isinstance(detected, AnchorDetection) else detected
        dx = round(target_anchor[0] - anchor[0]) + int(manual[0])
        dy = round(target_anchor[1] - anchor[1]) + int(manual[1])
        alpha_points = np.argwhere(arr[:, :, 3] > 0)
        if not len(alpha_points):
            raise ValueError(f"Frame {index} is empty")
        y0, x0 = alpha_points.min(axis=0)
        y1, x1 = alpha_points.max(axis=0) + 1
        if x0 + dx < 0 or y0 + dy < 0 or x1 + dx > width or y1 + dy > height:
            raise OverflowError(
                f"CELL_OVERFLOW frame={index} translated_bbox="
                f"{(x0 + dx, y0 + dy, x1 + dx, y1 + dy)} canvas={canvas_size}"
            )
        canvas = np.zeros((height, width, 4), np.uint8)
        yy, xx = np.where(arr[:, :, 3] > 0)
        canvas[yy + dy, xx + dx] = arr[yy, xx]
        outputs.append(Image.fromarray(canvas, "RGBA"))
    return outputs
