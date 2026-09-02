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


def generate_paths_map(width: int, height: int, seed: int = 42) -> list[list[bool]]:
    """Generate organic winding crossroads / paths terrain."""
    grid = [[False for _ in range(width)] for _ in range(height)]
    rng = random.Random(seed)

    curr_y = height // 2
    for x in range(width):
        for offset_y in (-1, 0):
            py = curr_y + offset_y
            if 0 <= py < height:
                grid[py][x] = True
        if rng.random() < 0.35 and 1 <= curr_y < height - 2:
            curr_y += rng.choice((-1, 1))

    curr_x = width // 2
    for y in range(height):
        for offset_x in (-1, 0):
            px = curr_x + offset_x
            if 0 <= px < width:
                grid[y][px] = True
        if rng.random() < 0.35 and 1 <= curr_x < width - 2:
            curr_x += rng.choice((-1, 1))

    return grid


def generate_rooms_map(
    width: int,
    height: int,
    room_count: int = 3,
    seed: int = 42,
) -> list[list[bool]]:
    """Generate multiple connected rectangular rooms and corridors."""
    grid = [[False for _ in range(width)] for _ in range(height)]
    rng = random.Random(seed)

    rooms: list[tuple[int, int, int, int]] = []
    for _ in range(room_count):
        rw = rng.randint(max(3, width // 5), max(4, width // 3))
        rh = rng.randint(max(3, height // 5), max(4, height // 3))
        rx = rng.randint(1, max(1, width - rw - 1))
        ry = rng.randint(1, max(1, height - rh - 1))
        rooms.append((rx, ry, rw, rh))
        for y in range(ry, ry + rh):
            for x in range(rx, rx + rw):
                if 0 <= y < height and 0 <= x < width:
                    grid[y][x] = True

    for i in range(len(rooms) - 1):
        x1 = rooms[i][0] + rooms[i][2] // 2
        y1 = rooms[i][1] + rooms[i][3] // 2
        x2 = rooms[i + 1][0] + rooms[i + 1][2] // 2
        y2 = rooms[i + 1][1] + rooms[i + 1][3] // 2

        for x in range(min(x1, x2), max(x1, x2) + 1):
            if 0 <= y1 < height and 0 <= x < width:
                grid[y1][x] = True
        for y in range(min(y1, y2), max(y1, y2) + 1):
            if 0 <= y < height and 0 <= x2 < width:
                grid[y][x2] = True

    return grid


def paint_tile_matrix(
    matrix: Sequence[Sequence[bool | int]],
    center_x: int,
    center_y: int,
    value: bool,
    *,
    brush_size: int = 1,
) -> list[list[bool]]:
    """Paint into a 2D boolean grid using a square brush of size 1, 2, or 3."""
    h = len(matrix)
    w = len(matrix[0]) if h > 0 else 0
    grid = [[bool(c) for c in row] for row in matrix]
    if w == 0 or h == 0:
        return grid

    radius = max(0, (brush_size - 1) // 2)
    extra = 1 if brush_size % 2 == 0 else 0
    x_min = max(0, center_x - radius)
    x_max = min(w - 1, center_x + radius + extra)
    y_min = max(0, center_y - radius)
    y_max = min(h - 1, center_y + radius + extra)

    for y in range(y_min, y_max + 1):
        for x in range(x_min, x_max + 1):
            grid[y][x] = value
    return grid


def flood_fill_matrix(
    matrix: Sequence[Sequence[bool | int]],
    start_x: int,
    start_y: int,
    fill_value: bool,
) -> list[list[bool]]:
    """Perform a 4-connected flood fill on a 2D boolean map matrix."""
    h = len(matrix)
    w = len(matrix[0]) if h > 0 else 0
    grid = [[bool(c) for c in row] for row in matrix]
    if not (0 <= start_x < w and 0 <= start_y < h):
        return grid

    target_value = grid[start_y][start_x]
    if target_value == fill_value:
        return grid

    queue = [(start_x, start_y)]
    grid[start_y][start_x] = fill_value

    while queue:
        cx, cy = queue.pop(0)
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == target_value:
                grid[ny][nx] = fill_value
                queue.append((nx, ny))

    return grid


def invert_tile_matrix(matrix: Sequence[Sequence[bool | int]]) -> list[list[bool]]:
    """Invert all boolean cells in a terrain matrix."""
    return [[not bool(c) for c in row] for row in matrix]


def clear_tile_matrix(width: int, height: int) -> list[list[bool]]:
    """Return an empty (all-false) terrain matrix."""
    return [[False for _ in range(width)] for _ in range(height)]


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
