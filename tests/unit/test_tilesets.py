from __future__ import annotations

import io
import json
import zipfile

from PIL import Image

from sprite_builder.tilesets import (
    TilesetGrid,
    build_tileset_bundle,
    resize_tileset,
    resize_tileset_canvas,
    slice_tileset,
)


def test_resize_tileset_is_nearest_neighbor() -> None:
    source = Image.new("RGBA", (2, 1))
    source.putdata([(255, 0, 0, 255), (0, 0, 255, 255)])

    resized = resize_tileset(source, (4, 2))

    assert resized.size == (4, 2)
    assert list(resized.get_flattened_data()) == [
        (255, 0, 0, 255),
        (255, 0, 0, 255),
        (0, 0, 255, 255),
        (0, 0, 255, 255),
    ] * 2


def test_resize_tileset_canvas_expands_without_scaling_pixels() -> None:
    source = Image.new("RGBA", (2, 1))
    source.putdata([(255, 0, 0, 255), (0, 0, 255, 255)])

    resized = resize_tileset_canvas(source, (4, 3), anchor="center")

    assert resized.size == (4, 3)
    assert resized.getpixel((1, 1)) == (255, 0, 0, 255)
    assert resized.getpixel((2, 1)) == (0, 0, 255, 255)
    assert resized.getpixel((0, 0)) == (0, 0, 0, 0)


def test_resize_tileset_canvas_crops_from_selected_anchor() -> None:
    source = Image.new("RGBA", (3, 1))
    source.putdata(
        [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]
    )

    resized = resize_tileset_canvas(source, (2, 1), anchor="top-right")

    assert list(resized.get_flattened_data()) == [
        (0, 255, 0, 255),
        (0, 0, 255, 255),
    ]


def test_resize_tileset_canvas_rejects_unknown_anchor() -> None:
    source = Image.new("RGBA", (1, 1))

    try:
        resize_tileset_canvas(source, (2, 2), anchor="unknown")
    except ValueError as exc:
        assert "Unsupported canvas anchor" in str(exc)
    else:
        raise AssertionError("Unknown anchors must be rejected")


def test_slice_tileset_respects_offset_spacing_and_duplicates() -> None:
    image = Image.new("RGBA", (7, 3))
    red = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
    image.alpha_composite(red, (1, 1))
    image.alpha_composite(red, (4, 1))
    grid = TilesetGrid(
        tile_width=2,
        tile_height=2,
        offset_x=1,
        offset_y=1,
        spacing_x=1,
    )

    tiles = slice_tileset(image, grid)

    assert len(tiles) == 2
    assert tiles[0].bounds == (1, 1, 3, 3)
    assert tiles[1].duplicate_of == 0
    assert not tiles[0].empty


def test_bundle_contains_atlas_metadata_and_unique_tiles() -> None:
    image = Image.new("RGBA", (4, 2), (30, 60, 90, 255))
    bundle = build_tileset_bundle(
        image,
        TilesetGrid(tile_width=2, tile_height=2),
        source_name="terrain.png",
    )

    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert set(archive.namelist()) == {
            "tileset.png",
            "tileset.json",
            "tiles/tile_0000.png",
        }
        metadata = json.loads(archive.read("tileset.json"))

    assert metadata["source_name"] == "terrain.png"
    assert metadata["grid"]["columns"] == 2
    assert metadata["tiles"][1]["duplicate_of"] == 0
