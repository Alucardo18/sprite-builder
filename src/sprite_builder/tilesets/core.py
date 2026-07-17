"""Deterministic, nearest-neighbor tileset processing."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True, slots=True)
class TilesetGrid:
    """Grid used to slice a tileset atlas."""

    tile_width: int = 16
    tile_height: int = 16
    offset_x: int = 0
    offset_y: int = 0
    spacing_x: int = 0
    spacing_y: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.tile_width <= 64 or not 1 <= self.tile_height <= 64:
            raise ValueError("Tile width and height must be between 1 and 64 pixels")
        if min(self.offset_x, self.offset_y, self.spacing_x, self.spacing_y) < 0:
            raise ValueError("Grid offsets and spacing cannot be negative")


@dataclass(frozen=True, slots=True)
class TilesetSlice:
    """A row-major atlas slice with duplicate lineage."""

    index: int
    column: int
    row: int
    bounds: tuple[int, int, int, int]
    sha256: str
    duplicate_of: int | None
    empty: bool


def resize_tileset(
    image: Image.Image,
    size: tuple[int, int],
) -> Image.Image:
    """Resize an atlas without introducing interpolated pixels."""

    width, height = map(int, size)
    if width < 1 or height < 1:
        raise ValueError("Tileset dimensions must be positive")
    return image.convert("RGBA").resize((width, height), Image.Resampling.NEAREST)


def resize_tileset_canvas(
    image: Image.Image,
    size: tuple[int, int],
    *,
    anchor: str = "top-left",
) -> Image.Image:
    """Resize the transparent canvas without scaling the atlas pixels."""

    width, height = map(int, size)
    if width < 1 or height < 1:
        raise ValueError("Canvas dimensions must be positive")
    horizontal, vertical = {
        "top-left": ("left", "top"),
        "top": ("center", "top"),
        "top-right": ("right", "top"),
        "left": ("left", "center"),
        "center": ("center", "center"),
        "right": ("right", "center"),
        "bottom-left": ("left", "bottom"),
        "bottom": ("center", "bottom"),
        "bottom-right": ("right", "bottom"),
    }.get(anchor, (None, None))
    if horizontal is None or vertical is None:
        raise ValueError(f"Unsupported canvas anchor: {anchor}")

    source = image.convert("RGBA")
    offset_x = {
        "left": 0,
        "center": (width - source.width) // 2,
        "right": width - source.width,
    }[horizontal]
    offset_y = {
        "top": 0,
        "center": (height - source.height) // 2,
        "bottom": height - source.height,
    }[vertical]
    destination_x = max(0, offset_x)
    destination_y = max(0, offset_y)
    source_x = max(0, -offset_x)
    source_y = max(0, -offset_y)
    copy_width = min(source.width - source_x, width - destination_x)
    copy_height = min(source.height - source_y, height - destination_y)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if copy_width > 0 and copy_height > 0:
        region = source.crop(
            (source_x, source_y, source_x + copy_width, source_y + copy_height)
        )
        canvas.alpha_composite(region, (destination_x, destination_y))
    return canvas


def _grid_axis_positions(
    total: int,
    *,
    offset: int,
    tile: int,
    spacing: int,
) -> tuple[int, ...]:
    if offset >= total:
        return ()
    step = tile + spacing
    return tuple(range(offset, total - tile + 1, step))


def slice_tileset(
    image: Image.Image,
    grid: TilesetGrid,
) -> tuple[TilesetSlice, ...]:
    """Slice complete tiles and identify exact duplicates and empty cells."""

    rgba = image.convert("RGBA")
    xs = _grid_axis_positions(
        rgba.width,
        offset=grid.offset_x,
        tile=grid.tile_width,
        spacing=grid.spacing_x,
    )
    ys = _grid_axis_positions(
        rgba.height,
        offset=grid.offset_y,
        tile=grid.tile_height,
        spacing=grid.spacing_y,
    )
    first_by_digest: dict[str, int] = {}
    slices: list[TilesetSlice] = []
    for row, y in enumerate(ys):
        for column, x in enumerate(xs):
            bounds = (x, y, x + grid.tile_width, y + grid.tile_height)
            tile = rgba.crop(bounds)
            digest = hashlib.sha256(tile.tobytes()).hexdigest()
            duplicate_of = first_by_digest.get(digest)
            index = len(slices)
            if duplicate_of is None:
                first_by_digest[digest] = index
            slices.append(
                TilesetSlice(
                    index=index,
                    column=column,
                    row=row,
                    bounds=bounds,
                    sha256=digest,
                    duplicate_of=duplicate_of,
                    empty=tile.getbbox() is None,
                )
            )
    return tuple(slices)


def build_tileset_bundle(
    image: Image.Image,
    grid: TilesetGrid,
    *,
    source_name: str = "tileset.png",
) -> bytes:
    """Create a portable PNG + JSON + unique-tile bundle in memory."""

    rgba = image.convert("RGBA")
    tiles = slice_tileset(rgba, grid)
    columns = max((tile.column for tile in tiles), default=-1) + 1
    rows = max((tile.row for tile in tiles), default=-1) + 1
    atlas_bytes = io.BytesIO()
    rgba.save(atlas_bytes, format="PNG", optimize=False)
    atlas_sha256 = hashlib.sha256(atlas_bytes.getvalue()).hexdigest()
    metadata = {
        "schema_version": "1.0",
        "kind": "tileset",
        "source_name": source_name,
        "atlas": {
            "path": "tileset.png",
            "width": rgba.width,
            "height": rgba.height,
            "sha256": atlas_sha256,
        },
        "grid": {
            "tile_width": grid.tile_width,
            "tile_height": grid.tile_height,
            "offset_x": grid.offset_x,
            "offset_y": grid.offset_y,
            "spacing_x": grid.spacing_x,
            "spacing_y": grid.spacing_y,
            "columns": columns,
            "rows": rows,
        },
        "tiles": [
            {
                "id": tile.index,
                "column": tile.column,
                "row": tile.row,
                "bounds": list(tile.bounds),
                "sha256": tile.sha256,
                "duplicate_of": tile.duplicate_of,
                "empty": tile.empty,
            }
            for tile in tiles
        ],
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("tileset.png", atlas_bytes.getvalue())
        bundle.writestr(
            "tileset.json",
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        )
        for tile in tiles:
            if tile.duplicate_of is not None:
                continue
            tile_image = rgba.crop(tile.bounds)
            tile_bytes = io.BytesIO()
            tile_image.save(tile_bytes, format="PNG", optimize=False)
            bundle.writestr(f"tiles/tile_{tile.index:04d}.png", tile_bytes.getvalue())
    return archive.getvalue()
