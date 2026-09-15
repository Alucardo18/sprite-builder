"""Tests for animated autotiles, frame synthesis, vertical stacking, and engine exports."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from sprite_builder.tilesets import (
    TerrainAnimationConfig,
    build_tilesetter_terrain_pattern,
    render_godot_terrain_installer,
    render_tiled_wangset_tsx,
    synthesize_animated_tile_frame,
    terrain_pattern_manifest,
)


def _sample_sources(size: int = 16) -> tuple[Image.Image, list[dict[str, object]], dict[str, object]]:
    atlas = Image.new("RGBA", (size * 2, size), (60, 150, 50, 255))
    water = Image.new("RGBA", (size, size), (30, 80, 180, 255))
    atlas.paste(water, (size, 0))
    sources: list[dict[str, object]] = [
        {"id": "grass", "rect": [0, 0, size, size]},
        {"id": "water", "rect": [size, 0, size, size]},
    ]
    config: dict[str, object] = {
        "baseSource": "grass",
        "secondarySource": "water",
        "terrainProfile": "grass_over_water",
        "edgeVariation": 1,
    }
    return atlas, sources, config


def test_synthesize_animated_tile_frame_preserves_land_perimeter() -> None:
    size = 16
    pixels = np.zeros((size, size, 4), dtype=np.uint8)
    pixels[:8, :, :3] = [60, 150, 50]  # Land
    pixels[8:, :, :3] = [30, 80, 180]  # Water
    pixels[..., 3] = 255
    owned = np.zeros((size, size), dtype=bool)
    owned[:8, :] = True

    # Frame 0 is unchanged
    frame0 = synthesize_animated_tile_frame(pixels, owned, frame_index=0, frame_count=4)
    assert np.array_equal(frame0, pixels)

    # Frames 1, 2, 3 must animate water and shore foam, but never change the top land border
    for f in (1, 2, 3):
        frame_f = synthesize_animated_tile_frame(pixels, owned, frame_index=f, frame_count=4, style="shore_ripples")
        assert not np.array_equal(frame_f, pixels)
        # Top row (land) must remain identical to original pixels
        assert np.array_equal(frame_f[0, :], pixels[0, :])
        # Water area must have changed
        assert not np.array_equal(frame_f[8:, :], pixels[8:, :])


def test_animated_autotile_builds_vertical_stack() -> None:
    atlas, sources, config = _sample_sources(16)
    config.update(
        animated=True,
        animationFrames=4,
        animationFps=8.0,
        animationStyle="shore_ripples",
    )
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )

    assert result.complete
    assert result.is_animated is True
    assert result.animation_frames == 4
    assert result.animation_fps == 8.0
    assert result.animation_style == "shore_ripples"
    assert result.animation_frames_images is not None
    assert len(result.animation_frames_images) == 4

    # The base block has 4 rows (4 * 16 = 64px)
    # The 4-frame vertical stack has 4 * 4 = 16 rows (16 * 16 = 256px)
    assert result.base_rows == 4
    assert result.rows == 16
    assert result.image.size == (12 * 16, 16 * 16)


def test_animated_autotile_manifest() -> None:
    atlas, sources, config = _sample_sources(16)
    config.update(
        animated=True,
        animationFrames=4,
        animationFps=10.0,
        animationStyle="water_waves",
    )
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )

    manifest = terrain_pattern_manifest(result)
    assert "animation" in manifest
    anim = manifest["animation"]
    assert anim["is_animated"] is True
    assert anim["frame_count"] == 4
    assert anim["fps"] == 10.0
    assert anim["style"] == "water_waves"
    assert anim["layout"] == "vertical_stack"
    assert anim["base_rows"] == 4
    assert anim["frame_height"] == 64


def test_godot_installer_configures_animation_properties() -> None:
    atlas, sources, config = _sample_sources(16)
    config.update(
        animated=True,
        animationFrames=4,
        animationFps=8.0,
    )
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )

    gdscript = render_godot_terrain_installer(result)
    assert "atlas.set_tile_animation_columns(coords, 1)" in gdscript
    assert "atlas.set_tile_animation_separation(coords, Vector2i(0, 3))" in gdscript
    assert "atlas.set_tile_animation_frames_count(coords, 4)" in gdscript
    assert "atlas.set_tile_animation_speed(coords, 8.00)" in gdscript


def test_tiled_tsx_contains_animation_tags() -> None:
    atlas, sources, config = _sample_sources(16)
    config.update(
        animated=True,
        animationFrames=4,
        animationFps=8.0,
    )
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )

    tsx = render_tiled_wangset_tsx(result)
    assert "<animation>" in tsx
    assert '<frame tileid="0" duration="125"/>' in tsx
    assert "</animation>" in tsx
