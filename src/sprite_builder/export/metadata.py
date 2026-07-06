"""Portable metadata shared by previews, tooling, and Godot integration."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .spritesheet import SheetResult


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_metadata(
    sheet: SheetResult,
    frame_paths: Sequence[str | Path],
    *,
    animation: str,
    fps: float,
    loop: bool = True,
    anchors: Sequence[Mapping[str, Any] | Sequence[float] | None] | None = None,
) -> dict[str, Any]:
    if fps <= 0:
        raise ValueError("FPS must be positive")
    paths = tuple(Path(path) for path in frame_paths)
    if len(paths) != len(sheet.regions):
        raise ValueError("Frame count and sheet region count differ")
    anchor_items = tuple(anchors or (None,) * len(paths))
    if len(anchor_items) != len(paths):
        raise ValueError("Anchor count and frame count differ")

    frames: list[dict[str, Any]] = []
    for index, (path, region, anchor) in enumerate(
        zip(paths, sheet.regions, anchor_items, strict=True)
    ):
        item: dict[str, Any] = {
            "index": index,
            "source": str(path),
            "source_sha256": _sha256(path),
            "region": list(region),
            "duration_seconds": 1.0 / fps,
        }
        if anchor is not None:
            if isinstance(anchor, Mapping):
                item.update(dict(anchor))
            else:
                item["torso_anchor"] = [float(anchor[0]), float(anchor[1])]
        frames.append(item)
    return {
        "schema_version": "1.0",
        "animation": animation,
        "fps": fps,
        "loop": loop,
        "sheet": {
            "path": str(sheet.output_path),
            "size": list(sheet.sheet_size),
            "cell_size": list(sheet.cell_size),
            "layout": {
                "type": sheet.layout,
                "columns": sheet.columns,
                "rows": sheet.rows,
            },
        },
        "frames": frames,
    }


def write_metadata(metadata: Mapping[str, Any], output_path: str | Path) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination
