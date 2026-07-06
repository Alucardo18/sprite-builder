"""Local, deterministic Character Bible bootstrapping.

This module measures references; it deliberately does not infer cultural,
costume, weapon, or identity claims that require human/art-direction review.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from PIL import Image

from sprite_builder.postprocess import remove_background


@dataclass(frozen=True, slots=True)
class PaletteColor:
    hex: str
    rgb: tuple[int, int, int]
    weight: float


@dataclass(frozen=True, slots=True)
class ReferenceAnalysis:
    source: str
    image_size: tuple[int, int]
    content_bbox: tuple[int, int, int, int]
    component_bboxes: tuple[tuple[int, int, int, int], ...]
    frame_bboxes: tuple[tuple[int, int, int, int], ...]
    palette: tuple[PaletteColor, ...]
    proportions: dict[str, float]
    background_removed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CharacterFiles:
    directory: Path
    bible: Path
    palette: Path
    analysis: ReferenceAnalysis | None


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    points = np.argwhere(mask)
    if not len(points):
        raise ValueError("Reference contains no visible foreground")
    y0, x0 = points.min(axis=0)
    y1, x1 = points.max(axis=0) + 1
    return int(x0), int(y0), int(x1), int(y1)


def _foreground(image: Image.Image) -> tuple[np.ndarray, bool]:
    rgba = np.asarray(image.convert("RGBA")).copy()
    alpha = rgba[:, :, 3]
    opaque_ratio = float((alpha >= 250).mean())
    if opaque_ratio > 0.98:
        # Generated/reference sheets often encode transparency as a uniform,
        # opaque chroma/black border. Border-connected removal preserves any
        # enclosed occurrence of the same colour.
        removed = remove_background(image, lab_tolerance=10, feather_px=0)
        if removed.foreground_mask.any() and removed.foreground_mask.mean() < 0.9:
            return np.asarray(removed.image), True
    return rgba, False


def _components(mask: np.ndarray) -> tuple[tuple[int, int, int, int], ...]:
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    minimum = max(4, round(mask.size * 0.00005))
    boxes = []
    for label in range(1, count):
        x, y, width, height, area = (int(v) for v in stats[label])
        if area >= minimum:
            boxes.append((x, y, x + width, y + height))
    return tuple(sorted(boxes, key=lambda value: (value[0], value[1])))


def _frame_bboxes(mask: np.ndarray) -> tuple[tuple[int, int, int, int], ...]:
    """Split a sheet on meaningful empty vertical gutters.

    Detached shadows/effects remain with their character because grouping is
    performed from the complete foreground projection, not per component.
    """
    occupied = mask.any(axis=0)
    indices = np.where(occupied)[0]
    if not len(indices):
        return ()
    gap_threshold = max(2, round(mask.shape[1] * 0.012))
    ranges: list[tuple[int, int]] = []
    start = previous = int(indices[0])
    for raw in indices[1:]:
        current = int(raw)
        if current - previous > gap_threshold:
            ranges.append((start, previous + 1))
            start = current
        previous = current
    ranges.append((start, previous + 1))
    result = []
    for x0, x1 in ranges:
        local = mask[:, x0:x1]
        y = np.where(local)[0]
        if len(y):
            result.append((x0, int(y.min()), x1, int(y.max()) + 1))
    return tuple(result)


def _extract_palette(
    rgba: np.ndarray, mask: np.ndarray, color_count: int
) -> tuple[PaletteColor, ...]:
    rgb = rgba[:, :, :3][mask]
    if not len(rgb):
        return ()
    unique = np.unique(rgb, axis=0)
    count = max(1, min(color_count, len(unique)))
    lab = cv2.cvtColor(rgb.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3)
    cv2.setRNGSeed(1337)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.2)
    samples = np.asarray(lab, dtype=np.float32)
    initial_labels = np.empty((len(samples), 1), dtype=np.int32)
    _, labels, centers = cv2.kmeans(
        samples,
        count,
        initial_labels,
        criteria,
        5,
        cv2.KMEANS_PP_CENTERS,
    )
    label_ids = np.asarray(labels, dtype=np.int64).ravel()
    frequencies = np.bincount(label_ids, minlength=count)
    order = np.argsort(-frequencies)
    colors: list[PaletteColor] = []
    for index in order:
        center = np.asarray([[np.clip(centers[index], 0, 255)]], dtype=np.uint8)
        value = cv2.cvtColor(center, cv2.COLOR_LAB2RGB)[0, 0]
        channels = (int(value[0]), int(value[1]), int(value[2]))
        colors.append(
            PaletteColor(
                hex="#" + "".join(f"{channel:02X}" for channel in channels),
                rgb=channels,
                weight=round(float(frequencies[index] / len(rgb)), 6),
            )
        )
    return tuple(colors)


def analyze_reference(
    reference: str | Path,
    *,
    palette_colors: int = 16,
) -> ReferenceAnalysis:
    """Measure a sprite/reference sheet without calling a model or service."""
    if palette_colors < 1 or palette_colors > 256:
        raise ValueError("palette_colors must be between 1 and 256")
    path = Path(reference).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    with Image.open(path) as source_image:
        rgba, removed = _foreground(source_image)
    mask = rgba[:, :, 3] > 8
    content = _bbox(mask)
    frames = _frame_bboxes(mask)
    widths = [x1 - x0 for x0, _, x1, _ in frames]
    heights = [y1 - y0 for _, y0, _, y1 in frames]
    content_width, content_height = content[2] - content[0], content[3] - content[1]
    proportions = {
        "content_width_ratio": round(content_width / rgba.shape[1], 6),
        "content_height_ratio": round(content_height / rgba.shape[0], 6),
        "foreground_occupancy": round(float(mask.mean()), 6),
        "mean_frame_width_px": round(float(np.mean(widths)), 3) if widths else 0.0,
        "mean_frame_height_px": round(float(np.mean(heights)), 3) if heights else 0.0,
        "mean_frame_aspect_ratio": (
            round(float(np.mean(np.divide(widths, heights))), 6) if widths and all(heights) else 0.0
        ),
    }
    return ReferenceAnalysis(
        source=str(path),
        image_size=(rgba.shape[1], rgba.shape[0]),
        content_bbox=content,
        component_bboxes=_components(mask),
        frame_bboxes=frames,
        palette=_extract_palette(rgba, mask, palette_colors),
        proportions=proportions,
        background_removed=removed,
    )


def _character_id(value: str) -> str:
    result = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-")
    if not result:
        raise ValueError("character_id must contain letters or numbers")
    return result


def create_character_skeleton(
    character_id: str,
    description: str,
    *,
    workspace: str | Path,
    reference: str | Path | None = None,
    palette_colors: int = 16,
) -> CharacterFiles:
    """Create reviewable Bible/palette files, refusing destructive overwrite."""
    identity = _character_id(character_id)
    if not description.strip():
        raise ValueError("description must not be empty")
    directory = Path(workspace).expanduser().resolve() / "characters" / identity
    bible_path = directory / "bible.yaml"
    palette_path = directory / "palette.json"
    collisions = [path for path in (bible_path, palette_path) if path.exists()]
    if collisions:
        names = ", ".join(str(path) for path in collisions)
        raise FileExistsError(f"Character files already exist; refusing to overwrite: {names}")

    analysis = analyze_reference(reference, palette_colors=palette_colors) if reference else None
    bible: dict[str, Any] = {
        "schema_version": "1.0",
        "identity": {
            "id": identity,
            "name": character_id.strip(),
            "description": description.strip(),
        },
        "review": {
            "required": True,
            "status": "draft",
            "note": "Complete immutable features and forbidden changes before generation.",
        },
        "visual_rules": {
            "immutable_features": [],
            "optional_features": [],
            "forbidden_changes": [],
            "silhouette_notes": "",
            "lighting": "",
            "outline": "",
        },
        "equipment": {"default_weapon": None, "attachment_rules": {}},
        "palette": {"locked": False, "file": "palette.json", "tolerance_delta_e00": 8},
        "reference": (
            {
                "source": analysis.source,
                "frame_count_detected": len(analysis.frame_bboxes),
                "frame_bboxes": [list(value) for value in analysis.frame_bboxes],
                "proportions": analysis.proportions,
            }
            if analysis
            else None
        ),
    }
    palette = {
        "schema_version": "1.0",
        "character_id": identity,
        "locked": False,
        "color_space": "sRGB",
        "extraction": "CIELAB k-means" if analysis else "manual",
        "colors": [asdict(color) for color in analysis.palette] if analysis else [],
    }
    directory.mkdir(parents=True, exist_ok=False)
    try:
        bible_path.write_text(
            yaml.safe_dump(bible, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        palette_path.write_text(
            json.dumps(palette, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except Exception:
        # Do not leave a misleading half-created character.
        for path in (bible_path, palette_path):
            path.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return CharacterFiles(directory, bible_path, palette_path, analysis)
