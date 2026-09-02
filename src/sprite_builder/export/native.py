"""Native full-sheet export without cropping, padding, or resampling.

This module is intentionally separate from the regular frame/cell exporter.
The native mode keeps the manually cleaned full PNG byte-for-byte intact and
stores only logical atlas regions for consumers such as Godot.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from .godot import render_sprite_frames_tres
from .metadata import write_metadata

Region = tuple[int, int, int, int]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_regions(
    regions: Sequence[Sequence[int]],
    *,
    sheet_size: tuple[int, int],
) -> tuple[Region, ...]:
    width, height = sheet_size
    validated: list[Region] = []
    for region in regions:
        if len(region) != 4:
            raise ValueError(f"Invalid native atlas region: {region}")
        x, y, region_width, region_height = (int(value) for value in region)
        if min(x, y) < 0 or min(region_width, region_height) <= 0:
            raise ValueError(f"Invalid native atlas region: {region}")
        if x + region_width > width or y + region_height > height:
            raise ValueError(
                f"NATIVE_REGION_OVERFLOW: region={region} sheet={(width, height)}"
            )
        validated.append((x, y, region_width, region_height))
    if not validated:
        raise ValueError("At least one native atlas region is required")
    return tuple(validated)


@dataclass(frozen=True, slots=True)
class NativeSheetResult:
    """Evidence for one native full-sheet export and its logical regions."""

    source_path: Path
    output_path: Path
    sheet_size: tuple[int, int]
    source_sha256: str
    output_sha256: str
    regions: tuple[Region, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "output_path": str(self.output_path),
            "sheet_size": list(self.sheet_size),
            "source_sha256": self.source_sha256,
            "output_sha256": self.output_sha256,
            "regions": [list(region) for region in self.regions],
            "source_preserved_byte_for_byte": self.source_sha256 == self.output_sha256,
            "transformations": [],
        }


def preserve_native_sheet(
    source_path: str | Path,
    output_path: str | Path,
    *,
    regions: Sequence[Sequence[int]],
) -> NativeSheetResult:
    """Copy a manually cleaned RGBA PNG without changing any source bytes.

    Region validation is metadata-only: no crop or resize is written. Existing
    outputs are replaced atomically, and the output hash must match the source
    hash before returning.
    """

    source = Path(source_path)
    destination = Path(output_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    with Image.open(source) as image:
        image.verify()
    with Image.open(source) as image:
        if image.format != "PNG":
            raise ValueError("Native sheet source must be a PNG")
        if image.mode != "RGBA":
            raise ValueError(
                f"NATIVE_EXPORT_BLOCKED: manual sheet must be RGBA, got {image.mode}"
            )
        sheet_size = image.size
    checked_regions = _validate_regions(regions, sheet_size=sheet_size)
    source_sha256 = _sha256(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".png",
            dir=destination.parent,
        )
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    output_sha256 = _sha256(destination)
    if output_sha256 != source_sha256:
        raise RuntimeError("NATIVE_EXPORT_INTEGRITY: output bytes differ from source")
    return NativeSheetResult(
        source_path=source,
        output_path=destination,
        sheet_size=sheet_size,
        source_sha256=source_sha256,
        output_sha256=output_sha256,
        regions=checked_regions,
    )


def build_native_metadata(
    sheet: NativeSheetResult,
    *,
    animation: str,
    fps: float,
    loop: bool = True,
    frame_indices: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Build metadata that describes regions while explicitly forbidding transforms."""

    if fps <= 0:
        raise ValueError("FPS must be positive")
    indices = (
        tuple(range(len(sheet.regions)))
        if frame_indices is None
        else tuple(int(index) for index in frame_indices)
    )
    if len(indices) != len(sheet.regions):
        raise ValueError("Native frame-index count and region count differ")
    if len(set(indices)) != len(indices) or any(index < 0 for index in indices):
        raise ValueError("Native frame indices must be unique and non-negative")
    frames = [
        {
            "index": output_index,
            "native_frame_index": source_index,
            "source": str(sheet.source_path),
            "source_sha256": sheet.source_sha256,
            "region": list(region),
            "duration_seconds": 1.0 / fps,
            "scale_factor": 1.0,
            "alignment_translation": [0, 0],
            "crop": False,
            "resampling": "none",
        }
        for output_index, (source_index, region) in enumerate(
            zip(indices, sheet.regions, strict=True)
        )
    ]
    return {
        "schema_version": "1.0",
        "export_mode": "native_full_sheet",
        "animation": animation,
        "fps": fps,
        "loop": loop,
        "source": {
            "path": str(sheet.source_path),
            "sha256": sheet.source_sha256,
            "size": list(sheet.sheet_size),
            "mode": "RGBA",
        },
        "sheet": {
            "path": str(sheet.output_path),
            "size": list(sheet.sheet_size),
            "cell_size": None,
            "layout": {
                "type": "native_regions",
                "columns": None,
                "rows": None,
            },
            "source_preserved_byte_for_byte": True,
        },
        "transformations": {
            "crop": False,
            "pad": False,
            "resample": False,
            "alignment": "none",
            "alpha": "manual_preserved",
        },
        "frames": frames,
    }


def export_native_godot_bundle(
    *,
    sheet: NativeSheetResult,
    output_directory: str | Path,
    texture_resource_path: str,
    animation: str,
    fps: float,
    loop: bool = True,
    frame_indices: Sequence[int] | None = None,
) -> tuple[Path, Path]:
    """Write native metadata and a Godot SpriteFrames resource."""

    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    metadata = build_native_metadata(
        sheet,
        animation=animation,
        fps=fps,
        loop=loop,
        frame_indices=frame_indices,
    )
    metadata_path = write_metadata(metadata, destination / f"{animation}.metadata.json")
    tres_path = destination / f"{animation}.sprite_frames.tres"
    tres_path.write_text(
        render_sprite_frames_tres(
            texture_resource_path=texture_resource_path,
            regions=sheet.regions,
            animation=animation,
            fps=fps,
            loop=loop,
        ),
        encoding="utf-8",
    )
    return metadata_path, tres_path


def write_native_manifest(
    sheet: NativeSheetResult,
    output_path: str | Path,
    *,
    animation: str,
    metadata_path: str | Path,
    tres_path: str | Path,
    texture_resource_path: str,
    frame_indices: Sequence[int],
) -> Path:
    """Persist a compact, auditable native-export manifest."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "schema_version": "1.0",
        "export_mode": "native_full_sheet",
        "animation": animation,
        "texture_resource_path": texture_resource_path,
        "frame_indices": [int(index) for index in frame_indices],
        "metadata_path": str(metadata_path),
        "sprite_frames_path": str(tres_path),
        "native_sheet": sheet.as_dict(),
        "invariants": {
            "physical_crops_written": False,
            "resampling_applied": False,
            "manual_alpha_reprocessed": False,
        },
    }
    destination.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination
