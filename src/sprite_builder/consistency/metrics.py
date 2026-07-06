from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class FrameMetrics:
    index: int
    palette_coverage: float
    silhouette_iou: float
    body_height_deviation: float
    temporal_edge_change: float
    drift_score: float
    status: str


@dataclass(frozen=True)
class ConsistencyReport:
    frames: list[FrameMetrics]
    mean_drift: float
    status: str

    def to_dict(self) -> dict:
        return {
            "frames": [asdict(x) for x in self.frames],
            "mean_drift": self.mean_drift,
            "status": self.status,
        }


def _arr(value) -> np.ndarray:
    if not isinstance(value, Image.Image):
        value = Image.open(value)
    return np.asarray(value.convert("RGBA"))


def validate_sprite_consistency(
    frames: Sequence[str | Path | Image.Image],
    *,
    canonical: str | Path | Image.Image,
    palette: list[tuple[int, int, int]],
    palette_lab_tolerance: float = 16.0,
) -> ConsistencyReport:
    if not frames:
        raise ValueError("At least one frame is required")
    canon = _arr(canonical)
    canon_mask = canon[:, :, 3] > 8
    canon_height = max(1, np.ptp(np.where(canon_mask)[0]) + 1)
    pal = (
        cv2.cvtColor(np.uint8(palette).reshape(-1, 1, 3), cv2.COLOR_RGB2LAB)
        .reshape(-1, 3)
        .astype(float)
    )
    results, previous_edges = [], None
    for i, value in enumerate(frames):
        arr = _arr(value)
        if arr.shape[:2] != canon.shape[:2]:
            raise ValueError("Consistency comparison requires aligned equal-size frames")
        mask = arr[:, :, 3] > 8
        pixels = (
            cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2LAB)
            .reshape(-1, 3)
            .astype(float)[mask.ravel()]
        )
        coverage = (
            float(
                (
                    np.min(((pixels[:, None] - pal[None]) ** 2).sum(2), axis=1) ** 0.5
                    <= palette_lab_tolerance
                ).mean()
            )
            if len(pixels)
            else 0.0
        )
        union = np.logical_or(mask, canon_mask).sum()
        iou = float(np.logical_and(mask, canon_mask).sum() / union) if union else 1.0
        height = np.ptp(np.where(mask)[0]) + 1 if mask.any() else 0
        height_dev = float(abs(height - canon_height) / canon_height)
        edges = cv2.Canny((mask * 255).astype(np.uint8), 50, 150) > 0
        temporal = (
            float(np.logical_xor(edges, previous_edges).mean())
            if previous_edges is not None
            else 0.0
        )
        previous_edges = edges
        drift = 100 * (
            0.35 * (1 - coverage)
            + 0.35 * (1 - iou)
            + 0.20 * min(1, height_dev)
            + 0.10 * min(1, temporal * 10)
        )
        status = "pass" if drift < 15 else "review" if drift < 30 else "reject"
        results.append(FrameMetrics(i, coverage, iou, height_dev, temporal, float(drift), status))
    mean = float(np.mean([x.drift_score for x in results]))
    status = (
        "reject"
        if any(x.status == "reject" for x in results)
        else "review"
        if any(x.status == "review" for x in results)
        else "pass"
    )
    return ConsistencyReport(results, mean, status)
