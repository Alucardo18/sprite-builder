"""Unit tests for procedural rounded corners, retro outlines, and up to 128px tile dimensions."""

from __future__ import annotations

import numpy as np
from PIL import Image

from sprite_builder.tilesets import (
    build_tilesetter_terrain_pattern,
    generate_procedural_reference_tile,
    terrain_edge_profiles,
)
from sprite_builder.tilesets.patterns import (
    _apply_retro_outline,
    _rounded_corner_coverage,
    _wang_bitmap_coverage,
)


def test_rounded_corner_coverage_radius_zero_matches_base() -> None:
    mask = 1  # Top-left corner
    width, height = 32, 32
    base = _wang_bitmap_coverage(mask, width, height)
    rounded = _rounded_corner_coverage(mask, width, height, radius=0, kind="dual_grid_15")

    assert np.allclose(base, rounded)


def test_rounded_corner_coverage_rounds_outer_corner_tip() -> None:
    mask = 1  # Top-left outer corner in Wang/DualGrid
    width, height = 32, 32
    radius = 6
    rounded = _rounded_corner_coverage(mask, width, height, radius=radius, kind="dual_grid_15")

    # In standard Wang coverage, (0, 0) has coverage ~1.0
    # With rounded outer corner of radius 6, distance from (6, 6) is > 6, so tip is reduced
    assert rounded[0, 0] <= 0.2


def test_rounded_corner_coverage_blob_47_outer_and_inner() -> None:
    # Outer corner tile in Blob 47 (mask = 28: only bottom and right connected, top & left free)
    width, height = 32, 32
    radius = 5
    cov = _rounded_corner_coverage(28, width, height, radius=radius, kind="blob_47")

    assert cov.shape == (32, 32)
    # The top-left corner tip is outer, so it should be shaved off (0.0)
    assert cov[0, 0] == 0.0
    # Inside the landmass (e.g. bottom-right center) it should remain solid
    assert cov[20, 20] >= 0.5


def test_apply_retro_outline_darkens_border_only() -> None:
    size = 16
    img = Image.new("RGBA", (size, size), (100, 200, 100, 255))
    # Create circular mask
    mask = np.zeros((size, size), dtype=bool)
    yy, xx = np.indices((size, size))
    mask[(xx - 8) ** 2 + (yy - 8) ** 2 <= 6 ** 2] = True

    outlined = _apply_retro_outline(img, mask, outline_color=(20, 20, 20, 255), strength=0.7)
    arr = np.asarray(outlined)

    # Center pixel (8, 8) is deep interior: must remain unchanged (100, 200, 100)
    assert tuple(arr[8, 8, :3]) == (100, 200, 100)

    # Border pixel at (8, 2) is on the edge: must be darker
    assert arr[8, 2, 1] < 150


def test_build_tilesetter_terrain_pattern_with_rounded_corners_and_outline() -> None:
    tile_w, tile_h = 32, 32
    atlas = Image.new("RGBA", (tile_w * 2, tile_h), (80, 160, 60, 255))
    # Right half is secondary
    atlas.paste(Image.new("RGBA", (tile_w, tile_h), (140, 90, 50, 255)), (tile_w, 0))

    sources = [
        {"id": "src_base", "name": "Base", "rect": [0, 0, tile_w, tile_h]},
        {"id": "src_sec", "name": "Sec", "rect": [tile_w, 0, tile_w, tile_h]},
    ]
    set_config = {
        "baseSource": "src_base",
        "secondarySource": "src_sec",
        "cornerRadius": 5,
        "retroOutline": True,
        "terrainProfile": "rounded_clean",
    }

    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(tile_w, tile_h),
        sources=sources,
        set_config=set_config,
        kind="dual_grid_15",
    )

    assert result.complete
    assert result.corner_radius == 5
    assert result.retro_outline is True
    assert result.image.size == (4 * tile_w, 4 * tile_h)


def test_build_tilesetter_blob_47_with_large_dimensions_128px() -> None:
    tile_w, tile_h = 128, 128
    base_tile = generate_procedural_reference_tile("grass_meadow", (tile_w, tile_h), seed=42)
    sec_tile = generate_procedural_reference_tile("dirt_earth", (tile_w, tile_h), seed=42)

    atlas = Image.new("RGBA", (tile_w * 2, tile_h))
    atlas.paste(base_tile, (0, 0))
    atlas.paste(sec_tile, (tile_w, 0))

    sources = [
        {"id": "src_grass", "name": "Grass", "rect": [0, 0, tile_w, tile_h]},
        {"id": "src_dirt", "name": "Dirt", "rect": [tile_w, 0, tile_w, tile_h]},
    ]
    set_config = {
        "baseSource": "src_grass",
        "secondarySource": "src_dirt",
        "cornerRadius": 16,
        "retroOutline": True,
        "terrainProfile": "rounded_grass_tufts",
    }

    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(tile_w, tile_h),
        sources=sources,
        set_config=set_config,
        kind="blob_47",
    )

    assert result.tile_width == 128
    assert result.tile_height == 128
    assert result.corner_radius == 16
    assert result.retro_outline is True
    assert len(result.tiles) == 47


def test_new_profiles_available_in_terrain_edge_profiles() -> None:
    profiles = terrain_edge_profiles()
    assert "rounded_clean" in profiles
    assert "rounded_grass_tufts" in profiles
    assert "rounded_dither" in profiles
