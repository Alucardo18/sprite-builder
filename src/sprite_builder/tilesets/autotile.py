"""Deterministic autotiling engines for Dual-Grid 15 and Blob 47 tilesets."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Any

from PIL import Image

from sprite_builder.tilesets.patterns import _GODOT_PATTERN_LAYOUTS, TerrainPatternKind


def _mask_to_layout_coord(
    layout: Sequence[Sequence[int | None]],
) -> dict[int, tuple[int, int]]:
    """Build a lookup mapping each integer mask to its (column, row) coordinate in the atlas."""
    lookup: dict[int, tuple[int, int]] = {}
    for row_idx, row in enumerate(layout):
        for col_idx, mask in enumerate(row):
            if mask is not None:
                lookup[mask] = (col_idx, row_idx)
    return lookup


def generate_empty_map(width: int, height: int) -> list[list[bool]]:
    """Generate an empty (all-background) boolean grid."""
    return [[False for _ in range(width)] for _ in range(height)]


def generate_filled_map(width: int, height: int) -> list[list[bool]]:
    """Generate a filled (all-foreground) boolean grid."""
    return [[True for _ in range(width)] for _ in range(height)]


def generate_island_map(width: int, height: int) -> list[list[bool]]:
    """Generate an organic island map with a central landmass and irregular shores."""
    grid = [[False for _ in range(width)] for _ in range(height)]
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    radius_x = max(1.0, width * 0.38)
    radius_y = max(1.0, height * 0.38)

    rng = random.Random(1337)
    for y in range(height):
        for x in range(width):
            dx = (x - center_x) / radius_x
            dy = (y - center_y) / radius_y
            dist = dx * dx + dy * dy
            jitter = (rng.random() - 0.5) * 0.25
            if dist + jitter < 0.75:
                grid[y][x] = True

    if width >= 10 and height >= 8:
        lake_cx = int(center_x + 1)
        lake_cy = int(center_y)
        for dy in (-1, 0):
            for dx in (-1, 0, 1):
                if 0 <= lake_cy + dy < height and 0 <= lake_cx + dx < width:
                    grid[lake_cy + dy][lake_cx + dx] = False

    return grid


def generate_dungeon_map(width: int, height: int) -> list[list[bool]]:
    """Generate a dungeon room-and-corridor structure."""
    grid = [[False for _ in range(width)] for _ in range(height)]

    r1_x1, r1_y1 = max(1, 1), max(1, 1)
    r1_x2, r1_y2 = min(width - 2, max(2, width // 3)), min(height - 2, max(2, height - 2))
    for y in range(r1_y1, r1_y2 + 1):
        for x in range(r1_x1, r1_x2 + 1):
            grid[y][x] = True

    r2_x1 = min(width - 2, max(r1_x2 + 3, (2 * width) // 3))
    r2_y1 = max(1, height // 4)
    r2_x2 = min(width - 2, width - 2)
    r2_y2 = min(height - 2, (3 * height) // 4)
    for y in range(r2_y1, r2_y2 + 1):
        for x in range(r2_x1, r2_x2 + 1):
            grid[y][x] = True

    corridor_y = height // 2
    for x in range(r1_x2, r2_x1 + 1):
        if 0 <= corridor_y < height:
            grid[corridor_y][x] = True
            if corridor_y + 1 < height:
                grid[corridor_y + 1][x] = True

    return grid


def generate_noise_map(
    width: int,
    height: int,
    density: float = 0.45,
    seed: int = 42,
) -> list[list[bool]]:
    """Generate a cave-like cellular automata terrain."""
    rng = random.Random(seed)
    grid = [[rng.random() < density for _ in range(width)] for _ in range(height)]

    for y in range(height):
        grid[y][0] = False
        grid[y][width - 1] = False
    for x in range(width):
        grid[0][x] = False
        grid[height - 1][x] = False

    for _ in range(2):
        next_grid = [[False for _ in range(width)] for _ in range(height)]
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                neighbors = sum(
                    1
                    for dy in (-1, 0, 1)
                    for dx in (-1, 0, 1)
                    if not (dx == 0 and dy == 0) and grid[y + dy][x + dx]
                )
                next_grid[y][x] = neighbors >= 4
        grid = next_grid

    return grid


def autotile_dual_grid(
    grid: Sequence[Sequence[int | bool]],
    pattern_image: Image.Image,
    tile_size: tuple[int, int],
    layout: Sequence[Sequence[int | None]] | None = None,
) -> Image.Image:
    """Render a visual map using Godot 2x2 corner / Dual-Grid 15 autotiling.

    The visual map has dimensions (width + 1, height + 1) in tiles because
    each visual tile is shifted by half a cell and evaluates the 4 logical corners:
    Top-Left (bit 0 = 1), Top-Right (bit 1 = 2), Bottom-Right (bit 2 = 4), Bottom-Left (bit 3 = 8).
    """
    map_h = len(grid)
    map_w = len(grid[0]) if map_h > 0 else 0
    if map_w == 0 or map_h == 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    tile_w, tile_h = tile_size
    disp_w = map_w + 1
    disp_h = map_h + 1

    active_layout = layout if layout is not None else _GODOT_PATTERN_LAYOUTS["dual_grid_15"]
    coord_lookup = _mask_to_layout_coord(active_layout)

    pattern_rgba = pattern_image.convert("RGBA")
    cached_tiles: dict[int, Image.Image] = {}

    output = Image.new("RGBA", (disp_w * tile_w, disp_h * tile_h), (0, 0, 0, 0))

    def _is_on(x: int, y: int) -> bool:
        if 0 <= x < map_w and 0 <= y < map_h:
            return bool(grid[y][x])
        return False

    for vy in range(disp_h):
        for vx in range(disp_w):
            tl = 1 if _is_on(vx - 1, vy - 1) else 0
            tr = 2 if _is_on(vx, vy - 1) else 0
            br = 4 if _is_on(vx, vy) else 0
            bl = 8 if _is_on(vx - 1, vy) else 0
            mask = tl | tr | br | bl

            if mask not in cached_tiles:
                pos = coord_lookup.get(mask)
                if pos is None:
                    pos = coord_lookup.get(0, (0, 3))
                cx, cy = pos
                tile_box = (cx * tile_w, cy * tile_h, (cx + 1) * tile_w, (cy + 1) * tile_h)
                cached_tiles[mask] = pattern_rgba.crop(tile_box)

            output.paste(cached_tiles[mask], (vx * tile_w, vy * tile_h))

    return output


def autotile_blob47(
    grid: Sequence[Sequence[int | bool]],
    pattern_image: Image.Image,
    tile_size: tuple[int, int],
    layout: Sequence[Sequence[int | None]] | None = None,
) -> Image.Image:
    """Render a visual map using Godot 3x3 minimal / Blob 47 autotiling."""
    map_h = len(grid)
    map_w = len(grid[0]) if map_h > 0 else 0
    if map_w == 0 or map_h == 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    tile_w, tile_h = tile_size
    active_layout = layout if layout is not None else _GODOT_PATTERN_LAYOUTS["blob_47"]
    coord_lookup = _mask_to_layout_coord(active_layout)

    pattern_rgba = pattern_image.convert("RGBA")
    cached_tiles: dict[int, Image.Image] = {}

    output = Image.new("RGBA", (map_w * tile_w, map_h * tile_h), (0, 0, 0, 0))

    def _is_on(x: int, y: int) -> bool:
        if 0 <= x < map_w and 0 <= y < map_h:
            return bool(grid[y][x])
        return False

    for y in range(map_h):
        for x in range(map_w):
            if not _is_on(x, y):
                continue

            n = _is_on(x, y - 1)
            e = _is_on(x + 1, y)
            s = _is_on(x, y + 1)
            w = _is_on(x - 1, y)

            mask = 0
            if n:
                mask |= 1
            if e:
                mask |= 4
            if s:
                mask |= 16
            if w:
                mask |= 64

            if n and e and _is_on(x + 1, y - 1):
                mask |= 2
            if e and s and _is_on(x + 1, y + 1):
                mask |= 8
            if s and w and _is_on(x - 1, y + 1):
                mask |= 32
            if w and n and _is_on(x - 1, y - 1):
                mask |= 128

            if mask not in cached_tiles:
                pos = coord_lookup.get(mask)
                if pos is None:
                    pos = coord_lookup.get(255, (9, 2))
                cx, cy = pos
                tile_box = (cx * tile_w, cy * tile_h, (cx + 1) * tile_w, (cy + 1) * tile_h)
                cached_tiles[mask] = pattern_rgba.crop(tile_box)

            output.paste(cached_tiles[mask], (x * tile_w, y * tile_h))

    return output
