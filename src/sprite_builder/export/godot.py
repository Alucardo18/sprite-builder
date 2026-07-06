"""Generate Godot 4 SpriteFrames resources backed by AtlasTexture regions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .metadata import build_metadata, write_metadata
from .spritesheet import SheetResult


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _validate_resource_path(path: str) -> None:
    if not path.startswith("res://"):
        raise ValueError("Godot texture path must start with res://")
    if path.endswith(".import"):
        raise ValueError("Do not reference or generate .import files")


def render_sprite_frames_tres(
    *,
    texture_resource_path: str,
    regions: Sequence[Sequence[int]],
    animation: str,
    fps: float,
    loop: bool = True,
) -> str:
    """Render a text SpriteFrames resource compatible with Godot 4.x."""

    _validate_resource_path(texture_resource_path)
    if not regions:
        raise ValueError("At least one region is required")
    if fps <= 0:
        raise ValueError("FPS must be positive")
    for region in regions:
        if len(region) != 4 or any(int(value) < 0 for value in region):
            raise ValueError(f"Invalid atlas region: {region}")
        if int(region[2]) == 0 or int(region[3]) == 0:
            raise ValueError(f"Region width and height must be positive: {region}")

    lines = [
        f'[gd_resource type="SpriteFrames" load_steps={len(regions) + 2} format=3]',
        "",
        (f'[ext_resource type="Texture2D" path={_quote(texture_resource_path)} id="1_atlas"]'),
        "",
    ]
    for index, region in enumerate(regions):
        resource_id = f"AtlasTexture_{index:04d}"
        x, y, width, height = (int(value) for value in region)
        lines.extend(
            [
                f'[sub_resource type="AtlasTexture" id="{resource_id}"]',
                'atlas = ExtResource("1_atlas")',
                f"region = Rect2({x}, {y}, {width}, {height})",
                "",
            ]
        )
    frame_entries = []
    for index in range(len(regions)):
        frame_entries.append(
            f'{{\n"duration": 1.0,\n"texture": SubResource("AtlasTexture_{index:04d}")\n}}'
        )
    animation_dict = (
        "[{\n"
        f'"frames": [{", ".join(frame_entries)}],\n'
        f'"loop": {str(loop).lower()},\n'
        f'"name": &{_quote(animation)},\n'
        f'"speed": {float(fps)}\n'
        "}]"
    )
    lines.extend(["[resource]", f"animations = {animation_dict}", ""])
    return "\n".join(lines)


def export_godot_bundle(
    *,
    sheet: SheetResult,
    frame_paths: Sequence[str | Path],
    output_directory: str | Path,
    texture_resource_path: str,
    animation: str,
    fps: float,
    loop: bool = True,
    anchors: Sequence[Mapping[str, Any] | Sequence[float] | None] | None = None,
) -> tuple[Path, Path]:
    """Write metadata JSON and a SpriteFrames ``.tres``; never writes .import."""

    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    metadata = build_metadata(
        sheet,
        frame_paths,
        animation=animation,
        fps=fps,
        loop=loop,
        anchors=anchors,
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
