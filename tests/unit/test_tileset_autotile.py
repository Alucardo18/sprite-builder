"""Tests for the autotiling engine (Dual Grid 15 and Blob 47)."""

from __future__ import annotations

from PIL import Image

from sprite_builder.tilesets.autotile import (
    autotile_blob47,
    autotile_dual_grid,
    generate_dungeon_map,
    generate_empty_map,
    generate_filled_map,
    generate_island_map,
    generate_noise_map,
)
from sprite_builder.tilesets.patterns import _GODOT_PATTERN_LAYOUTS


def test_map_generators_produce_correct_dimensions_and_types() -> None:
    w, h = 12, 8
    empty = generate_empty_map(w, h)
    assert len(empty) == h
    assert len(empty[0]) == w
    assert not any(any(row) for row in empty)

    filled = generate_filled_map(w, h)
    assert len(filled) == h
    assert len(filled[0]) == w
    assert all(all(row) for row in filled)

    island = generate_island_map(w, h)
    assert len(island) == h
    assert len(island[0]) == w
    assert any(any(row) for row in island)

    dungeon = generate_dungeon_map(w, h)
    assert len(dungeon) == h
    assert len(dungeon[0]) == w
    assert any(any(row) for row in dungeon)

    noise = generate_noise_map(w, h, density=0.5, seed=42)
    assert len(noise) == h
    assert len(noise[0]) == w


def test_autotile_dual_grid_renders_correct_dimensions() -> None:
    tile_w, tile_h = 16, 16
    grid = [
        [True, True, False],
        [True, False, False],
    ]
    # Grid is 3 wide by 2 high -> dual grid visual map is 4 wide by 3 high
    pattern_image = Image.new("RGBA", (4 * tile_w, 4 * tile_h), (50, 100, 150, 255))
    rendered = autotile_dual_grid(grid, pattern_image, (tile_w, tile_h))

    assert rendered.size == (4 * tile_w, 3 * tile_h)
    assert rendered.mode == "RGBA"


def test_autotile_blob47_renders_correct_dimensions() -> None:
    tile_w, tile_h = 16, 16
    grid = [
        [False, True, False],
        [True, True, True],
        [False, True, False],
    ]
    # Grid is 3 wide by 3 high -> Blob visual map is 3 wide by 3 high
    pattern_image = Image.new("RGBA", (12 * tile_w, 4 * tile_h), (80, 120, 200, 255))
    rendered = autotile_blob47(grid, pattern_image, (tile_w, tile_h))

    assert rendered.size == (3 * tile_w, 3 * tile_h)
    assert rendered.mode == "RGBA"
