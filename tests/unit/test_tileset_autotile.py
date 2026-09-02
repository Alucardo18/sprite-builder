"""Tests for the autotiling engine (Dual Grid 15 and Blob 47)."""

from __future__ import annotations

from PIL import Image

from sprite_builder.tilesets.autotile import (
    autotile_blob47,
    autotile_dual_grid,
    clear_tile_matrix,
    flood_fill_matrix,
    generate_dungeon_map,
    generate_empty_map,
    generate_filled_map,
    generate_island_map,
    generate_noise_map,
    generate_paths_map,
    generate_rooms_map,
    invert_tile_matrix,
    paint_tile_matrix,
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


def test_paths_and_rooms_generators() -> None:
    w, h = 16, 12
    paths = generate_paths_map(w, h, seed=42)
    assert len(paths) == h
    assert len(paths[0]) == w
    assert any(any(row) for row in paths)

    rooms = generate_rooms_map(w, h, room_count=3, seed=42)
    assert len(rooms) == h
    assert len(rooms[0]) == w
    assert any(any(row) for row in rooms)


def test_paint_tile_matrix_brush_sizes() -> None:
    w, h = 10, 10
    base = generate_empty_map(w, h)

    # 1x1 brush
    painted_1 = paint_tile_matrix(base, 5, 5, True, brush_size=1)
    assert painted_1[5][5] is True
    assert painted_1[5][6] is False

    # 3x3 brush
    painted_3 = paint_tile_matrix(base, 5, 5, True, brush_size=3)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            assert painted_3[5 + dy][5 + dx] is True


def test_flood_fill_matrix() -> None:
    grid = [
        [False, False, False],
        [False, False, False],
        [False, False, False],
    ]
    filled = flood_fill_matrix(grid, 0, 0, True)
    assert all(all(row) for row in filled)


def test_invert_and_clear_tile_matrix() -> None:
    grid = [[True, False], [False, True]]
    inverted = invert_tile_matrix(grid)
    assert inverted == [[False, True], [True, False]]

    cleared = clear_tile_matrix(4, 4)
    assert len(cleared) == 4
    assert not any(any(row) for row in cleared)

