from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageSequence

from sprite_builder.export import (
    build_metadata,
    build_spritesheet,
    export_godot_bundle,
    render_sprite_frames_tres,
)
from sprite_builder.preview import (
    create_anchor_overlay,
    create_animation_gif,
    create_contact_sheet,
)


def _frames(directory: Path, count: int = 4) -> list[Path]:
    result = []
    for index in range(count):
        path = directory / f"{index:03d}.png"
        image = Image.new("RGBA", (8, 10), (0, 0, 0, 0))
        image.putpixel((index % 8, 5), (255, 100, 0, 255))
        image.save(path)
        result.append(path)
    return result


def test_horizontal_sheet_and_metadata(tmp_path: Path) -> None:
    frames = _frames(tmp_path)
    result = build_spritesheet(frames, tmp_path / "sheet.png", cell_size=(12, 12))
    assert result.sheet_size == (48, 12)
    assert result.regions[2] == (24, 0, 12, 12)

    metadata = build_metadata(
        result,
        frames,
        animation="walk_right",
        fps=8,
        anchors=[[6, 7]] * 4,
    )
    assert metadata["frames"][0]["torso_anchor"] == [6.0, 7.0]
    assert metadata["frames"][0]["duration_seconds"] == 0.125


def test_grid_sheet_regions_are_row_major(tmp_path: Path) -> None:
    frames = _frames(tmp_path, 3)
    result = build_spritesheet(
        frames,
        tmp_path / "grid.png",
        layout="grid",
        columns=2,
        cell_size=(8, 10),
    )
    assert result.sheet_size == (16, 20)
    assert result.layout == "grid"
    assert result.regions == (
        (0, 0, 8, 10),
        (8, 0, 8, 10),
        (0, 10, 8, 10),
    )


def test_vertical_sheet_regions_are_column_major(tmp_path: Path) -> None:
    frames = _frames(tmp_path, 3)
    result = build_spritesheet(
        frames,
        tmp_path / "vertical.png",
        layout="vertical",
        cell_size=(8, 10),
    )
    assert result.sheet_size == (8, 30)
    assert result.regions == (
        (0, 0, 8, 10),
        (0, 10, 8, 10),
        (0, 20, 8, 10),
    )


def test_sheet_rejects_overflow_instead_of_scaling(tmp_path: Path) -> None:
    frames = _frames(tmp_path, 1)
    with pytest.raises(ValueError, match="CELL_OVERFLOW"):
        build_spritesheet(frames, tmp_path / "bad.png", cell_size=(7, 10))


def test_godot_bundle_uses_atlas_textures_and_never_import(tmp_path: Path) -> None:
    frames = _frames(tmp_path, 2)
    sheet = build_spritesheet(frames, tmp_path / "walk.png")
    metadata_path, tres_path = export_godot_bundle(
        sheet=sheet,
        frame_paths=frames,
        output_directory=tmp_path / "out",
        texture_resource_path="res://assets/generated/walk.png",
        animation="walk_right",
        fps=8,
    )
    text = tres_path.read_text(encoding="utf-8")
    assert '[gd_resource type="SpriteFrames"' in text
    assert text.count('[sub_resource type="AtlasTexture"') == 2
    assert '"speed": 8.0' in text
    assert ".import" not in text
    assert not list(tmp_path.rglob("*.import"))
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert data["animation"] == "walk_right"


def test_godot_resource_requires_res_path() -> None:
    with pytest.raises(ValueError, match="res://"):
        render_sprite_frames_tres(
            texture_resource_path="/tmp/sheet.png",
            regions=[(0, 0, 8, 8)],
            animation="idle",
            fps=4,
        )


def test_previews_are_created_with_expected_geometry(tmp_path: Path) -> None:
    frames = _frames(tmp_path)
    gif_path = create_animation_gif(frames, tmp_path / "preview.gif", fps=8, scale=2)
    contact_path = create_contact_sheet(frames, tmp_path / "contact.png", columns=2, scale=2)
    overlay_path = create_anchor_overlay(
        frames, [[4, 5]] * 4, tmp_path / "anchors.png", columns=2, scale=2
    )
    with Image.open(gif_path) as gif:
        assert len(list(ImageSequence.Iterator(gif))) == 4
        assert gif.size == (16, 20)
    with Image.open(contact_path) as contact:
        assert contact.size == (32, 40)
    with Image.open(overlay_path) as overlay:
        assert overlay.size == (32, 40)
