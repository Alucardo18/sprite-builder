"""Unit tests for procedural Dual Grid generation and error recovery."""

from __future__ import annotations

import numpy as np
from PIL import Image

from sprite_builder.tilesets import (
    build_tilesetter_terrain_pattern,
    generate_procedural_material,
)
from sprite_builder.ui.app import _build_terrain_pattern_safely


def test_procedural_dual_grid_without_atlas_generates_all_tiles() -> None:
    """Procedural Dual Grid with no atlas must paint all 16 cells without missing pixels."""
    tile_size = (16, 16)
    ephemeral_image = Image.new("RGBA", tile_size, (0, 0, 0, 0))
    set_config = {
        "id": "test_dual_set",
        "name": "Procedural Grass/Dirt",
        "kind": "dual_grid_15",
        "blobMaterialMode": "procedural",
        "primaryColor": "#22C55E",
        "secondaryColor": "#8B5A2B",
        "insideMaterial": "grass",
        "outsideMaterial": "dirt",
        "terrainProfile": "grass_over_dirt",
        "cornerRadius": 3,
        "edgeVariation": 1,
    }

    result = build_tilesetter_terrain_pattern(
        ephemeral_image,
        tile_size=tile_size,
        sources=[],
        set_config=set_config,
        kind="dual_grid_15",
    )

    assert result is not None
    assert result.kind == "dual_grid_15"
    assert result.columns == 4
    assert result.rows == 4
    assert len(result.tiles) == 15
    for tile in result.tiles:
        assert tile.source_index == 0, f"Role for mask {tile.mask} should be ready"

    # Verify that the full 4x4 atlas is non-empty and non-transparent
    arr = np.asarray(result.image)
    assert arr.shape == (64, 64, 4)
    # Every single pixel across all 16 cells must be fully opaque
    assert np.all(arr[..., 3] == 255), "Atlas image should contain zero transparent pixels"

    # Verify specifically the background cell at (col 0, row 3)
    bg_tile = arr[3 * 16 : 4 * 16, 0 * 16 : 1 * 16]
    assert np.all(bg_tile[..., 3] == 255), "Cell (0, 3) must be fully painted"
    # Verify dirt color range in background tile
    mean_color = bg_tile[..., :3].mean(axis=(0, 1))
    assert mean_color[0] > 50  # non-black dirt tone


def test_dual_grid_with_single_base_source_and_fallback_secondary() -> None:
    """Dual Grid with only baseSource provided should synthesize secondary without crashing."""
    tile_size = (16, 16)
    # Create an atlas containing 1 tile
    atlas = Image.new("RGBA", (16, 16), (34, 197, 94, 255))
    sources = [
        {
            "id": "src_base",
            "name": "Base Grass",
            "x": 0,
            "y": 0,
            "width": 16,
            "height": 16,
            "rect": [0, 0, 16, 16],
        }
    ]
    set_config = {
        "id": "test_single_base",
        "name": "Single Base Set",
        "kind": "dual_grid_15",
        "baseSource": "src_base",
        "secondarySource": None,
        "outsideColor": "#6B4423",
        "terrainProfile": "grass_over_dirt",
    }

    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=tile_size,
        sources=sources,
        set_config=set_config,
        kind="dual_grid_15",
    )

    assert result is not None
    assert len(result.tiles) == 15
    arr = np.asarray(result.image)
    assert np.all(arr[..., 3] == 255), "All tiles must be fully composited without missing borders"


def test_out_of_bounds_sources_handled_safely() -> None:
    """Sources whose bounds exceed atlas dimensions must not raise uncaught ValueError."""
    tile_size = (16, 16)
    small_atlas = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    # Source pointing way outside the 16x16 atlas
    sources = [
        {
            "id": "src_out_of_bounds",
            "name": "OOB Source",
            "x": 64,
            "y": 64,
            "width": 16,
            "height": 16,
            "rect": [64, 64, 16, 16],
        }
    ]
    set_config = {
        "id": "test_oob",
        "name": "OOB Set",
        "kind": "dual_grid_15",
        "baseSource": "src_out_of_bounds",
        "secondarySource": None,
        "primaryColor": "#10B981",
        "secondaryColor": "#3B82F6",
    }

    # Must complete safely via procedural fallback rather than raising ValueError
    result = build_tilesetter_terrain_pattern(
        small_atlas,
        tile_size=tile_size,
        sources=sources,
        set_config=set_config,
        kind="dual_grid_15",
    )
    assert result is not None
    assert result.image.size == (64, 64)


def test_build_terrain_pattern_safely_with_ephemeral_token() -> None:
    """Safe builder must cache and return valid result for ephemeral images."""
    tile_size = (16, 16)
    ephemeral = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    ephemeral._cache_token = "ephemeral:16x16"

    set_config = {
        "id": "set_cache_test",
        "kind": "dual_grid_15",
        "blobMaterialMode": "procedural",
        "primaryColor": "#22C55E",
        "secondaryColor": "#8B5A2B",
    }

    pattern1, error1 = _build_terrain_pattern_safely(
        ephemeral,
        tile_size=tile_size,
        sources=[],
        set_config=set_config,
        kind="dual_grid_15",
    )
    assert error1 is None
    assert pattern1 is not None

    pattern2, error2 = _build_terrain_pattern_safely(
        ephemeral,
        tile_size=tile_size,
        sources=[],
        set_config=set_config,
        kind="dual_grid_15",
    )
    assert pattern1 is pattern2, "Should return cached result"


def test_generate_procedural_material_helper() -> None:
    """Test procedural material synthesis helper with various materials and custom colors."""
    tile = generate_procedural_material((32, 32), "grass", base_color="#34D399", seed=42)
    assert isinstance(tile, Image.Image)
    assert tile.size == (32, 32)
    arr = np.asarray(tile)
    assert arr.shape == (32, 32, 4)
    assert np.all(arr[..., 3] == 255)

    dirt = generate_procedural_material((16, 16), "dirt", base_color="invalid_hex", seed=7)
    assert dirt.size == (16, 16)
    assert np.all(np.asarray(dirt)[..., 3] == 255)
