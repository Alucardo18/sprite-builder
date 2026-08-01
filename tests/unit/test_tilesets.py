from __future__ import annotations

import io
import json
import zipfile

from PIL import Image, ImageDraw

from sprite_builder.tilesets import (
    TilesetGrid,
    build_fragment_terrain_pattern,
    build_manual_terrain_pattern,
    build_smart_terrain_pattern,
    build_terrain_pattern_bundle,
    build_tileset_bundle,
    build_tilesetter_terrain_pattern,
    generate_terrain_pattern,
    render_godot_terrain_installer,
    render_terrain_bitmask_template,
    resize_tileset,
    resize_tileset_canvas,
    slice_tileset,
    terrain_pattern_layout,
    terrain_pattern_manifest,
    terrain_pattern_masks,
    terrain_pattern_set_layout,
)
from sprite_builder.tilesets.patterns import _tilesetter_blob_neighbor_matrix


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


def test_terrain_pattern_presets_have_canonical_role_counts() -> None:
    assert terrain_pattern_masks("wang_16") == tuple(range(16))
    assert terrain_pattern_masks("sides_16") == tuple(range(16))
    blob_masks = terrain_pattern_masks("blob_47")
    assert len(blob_masks) == 47
    assert blob_masks[0] == 0
    assert blob_masks[-1] == 255


def test_terrain_patterns_use_official_godot_bitmap_layouts() -> None:
    blob = terrain_pattern_layout("blob_47")
    wang = terrain_pattern_layout("wang_16")
    sides = terrain_pattern_layout("sides_16")

    assert len(blob) == 4
    assert all(len(row) == 12 for row in blob)
    assert blob[1][10] is None
    assert blob[3][0] == 0
    assert blob[2][9] == 255
    assert wang == (
        (8, 6, 13, 12),
        (5, 14, 15, 11),
        (2, 3, 7, 9),
        (0, 4, 10, 1),
    )
    assert sides[3] == (0, 2, 10, 8)


def test_blob_set_view_uses_tilesetter_visual_layout_without_changing_export() -> None:
    display = terrain_pattern_set_layout("blob_47")
    export = terrain_pattern_layout("blob_47")

    assert len(display) == 5
    assert all(len(row) == 11 for row in display)
    assert sum(mask is not None for row in display for mask in row) == 47
    assert {mask for row in display for mask in row if mask is not None} == set(
        terrain_pattern_masks("blob_47")
    )
    assert display == (
        (28, 124, 112, 16, 20, 116, 92, 80, 84, 221, None),
        (31, 255, 241, 17, 23, 247, 223, 209, 215, 119, None),
        (7, 199, 193, 1, 29, 253, 127, 113, 125, 93, 117),
        (4, 68, 64, 0, 5, 197, 71, 65, 69, 87, 213),
        (None, None, None, None, 21, 245, 95, 81, 85, None, None),
    )
    assert export[2][9] == 255
    assert len(export) == 4
    assert len(export[0]) == 12
    left_exposed = {
        (column, row)
        for row, layout_row in enumerate(display)
        for column, mask in enumerate(layout_row)
        if mask is not None and not (mask & 64)
    }
    assert left_exposed == {
        (0, 0),
        (3, 0),
        (4, 0),
        (0, 1),
        (3, 1),
        (4, 1),
        (0, 2),
        (3, 2),
        (4, 2),
        (0, 3),
        (3, 3),
        (4, 3),
        (4, 4),
    }


def test_tilesetter_blob_preserves_null_diagonals_from_generation_matrix() -> None:
    assert _tilesetter_blob_neighbor_matrix(0) == (
        None,
        False,
        None,
        False,
        None,
        False,
        None,
        False,
    )
    assert _tilesetter_blob_neighbor_matrix(65) == (
        False,
        True,
        None,
        False,
        None,
        False,
        None,
        True,
    )
    assert _tilesetter_blob_neighbor_matrix(255) == (
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    )


def test_blob_bitmask_reference_matches_official_12_by_4_template() -> None:
    guide = render_terrain_bitmask_template("blob_47", tile_size=48)

    assert guide.size == (576, 192)
    # Official unused slot at column 10, row 1 remains white.
    assert guide.getpixel((10 * 48 + 24, 1 * 48 + 24)) == (255, 255, 255, 255)
    # Mask 0 lives at column 0, row 3 and contains only the center bit.
    assert guide.getpixel((24, 3 * 48 + 24)) == (255, 57, 106, 255)
    assert guide.getpixel((8, 3 * 48 + 8)) == (255, 255, 255, 255)


def test_wang_pattern_composes_bitmap_sources_and_corner_roles() -> None:
    inside = Image.new("RGBA", (4, 4), (20, 180, 70, 255))
    outside = Image.new("RGBA", (4, 4), (30, 50, 120, 255))

    result = generate_terrain_pattern(inside, outside, kind="wang_16")

    assert result.image.size == (16, 16)
    assert result.mode == "match_corners"
    assert len(result.tiles) == 16
    empty_role = result.tiles[0]
    full_role = result.tiles[-1]
    assert result.image.getpixel(
        (empty_role.column * 4, empty_role.row * 4)
    ) == (30, 50, 120, 255)
    assert result.image.getpixel(
        (full_role.column * 4 + 3, full_role.row * 4 + 3)
    ) == (20, 180, 70, 255)
    assert result.tiles[-1].neighbors == (
        "top_left",
        "top_right",
        "bottom_right",
        "bottom_left",
    )


def test_blob_pattern_generates_47_godot_peering_roles() -> None:
    inside = Image.new("RGBA", (8, 8), (200, 140, 40, 255))
    outside = Image.new("RGBA", (8, 8), (0, 0, 0, 0))

    result = generate_terrain_pattern(inside, outside, kind="blob_47")
    manifest = terrain_pattern_manifest(result, terrain_name="Rock")

    assert result.image.size == (96, 32)
    assert len(result.tiles) == 47
    assert manifest["godot"]["mode"] == "match_corners_and_sides"
    assert manifest["atlas"]["sha256"]
    assert manifest["tiles"][0]["peering_bits"] == {
        "12": -1,
        "15": -1,
        "0": -1,
        "3": -1,
        "4": -1,
        "7": -1,
        "8": -1,
        "11": -1,
    }
    assert set(manifest["tiles"][-1]["peering_bits"].values()) == {0}


def test_godot_terrain_installer_uses_terrain_sets_not_legacy_bitmaps() -> None:
    result = generate_terrain_pattern(
        Image.new("RGBA", (4, 4), (255, 255, 255, 255)),
        Image.new("RGBA", (4, 4), (0, 0, 0, 0)),
        kind="blob_47",
    )

    script = render_godot_terrain_installer(result, terrain_name="Stone")

    assert "TERRAIN_MODE_MATCH_CORNERS_AND_SIDES" in script
    assert "set_terrain_peering_bit" in script
    assert "terrain_tileset.tres" in script
    assert ".import" not in script


def test_terrain_pattern_bundle_is_self_contained_and_godot_ready() -> None:
    result = generate_terrain_pattern(
        Image.new("RGBA", (4, 4), (255, 255, 255, 255)),
        Image.new("RGBA", (4, 4), (0, 0, 0, 0)),
    )

    payload = build_terrain_pattern_bundle(result, terrain_name="Grass")

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {
            "terrain_tiles.png",
            "terrain_bitmask_reference.png",
            "terrain_pattern.json",
            "install_terrain_tileset.gd",
            "README.txt",
        }
        assert all(not name.endswith(".import") for name in archive.namelist())
        manifest = json.loads(archive.read("terrain_pattern.json"))
    assert manifest["terrain_name"] == "Grass"
    assert manifest["pattern"] == "wang_16"


def test_manual_pattern_copies_assigned_tiles_and_marks_missing_roles() -> None:
    atlas = Image.new("RGBA", (8, 4))
    atlas.paste((220, 80, 60, 255), (0, 0, 4, 4))
    atlas.paste((50, 170, 210, 255), (4, 0, 8, 4))

    result = build_manual_terrain_pattern(
        atlas,
        TilesetGrid(tile_width=4, tile_height=4),
        {0: 1, 1: 0},
        kind="sides_16",
    )

    assert not result.complete
    assert len(result.unassigned_masks) == 14
    assert result.tiles[0].source_index == 1
    first = result.tiles[0]
    second = result.tiles[1]
    assert result.image.getpixel((first.column * 4, first.row * 4)) == (
        50,
        170,
        210,
        255,
    )
    assert result.image.getpixel((second.column * 4, second.row * 4)) == (
        220,
        80,
        60,
        255,
    )


def test_manual_pattern_bundle_requires_every_role_assignment() -> None:
    result = build_manual_terrain_pattern(
        Image.new("RGBA", (4, 4), (255, 255, 255, 255)),
        TilesetGrid(tile_width=4, tile_height=4),
        {0: 0},
        kind="wang_16",
    )

    try:
        build_terrain_pattern_bundle(result)
    except ValueError as exc:
        assert "15 unassigned roles" in str(exc)
    else:
        raise AssertionError("Incomplete manual patterns must not be exported")


def test_fragment_pattern_composes_arbitrary_crops_and_manual_overrides() -> None:
    atlas = Image.new("RGBA", (12, 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(atlas)
    draw.rectangle((0, 0, 7, 7), fill=(40, 170, 80, 255))
    draw.rectangle((8, 0, 11, 1), fill=(220, 190, 70, 255))
    fragments = [
        {"id": "center", "x": 0, "y": 0, "width": 8, "height": 8},
        {"id": "edge", "x": 8, "y": 0, "width": 4, "height": 2},
    ]
    center = {
        "id": "center-layer",
        "fragmentId": "center",
        "x": 0,
        "y": 0,
        "rotation": 0,
        "opacity": 1,
    }
    edge = {
        "id": "edge-layer",
        "fragmentId": "edge",
        "x": 2,
        "y": 0,
        "rotation": 0,
        "opacity": 1,
    }
    override = dict(center)
    override["id"] = "override-layer"
    override["x"] = 1
    result = build_fragment_terrain_pattern(
        atlas,
        tile_size=(8, 8),
        fragments=fragments,
        master_layers=[center, edge],
        semantic_roles={
            "center": "center-layer",
            "edge": "edge-layer",
            "outerCorner": None,
            "innerCorner": None,
        },
        variant_overrides={0: [override]},
        kind="sides_16",
    )

    assert result.complete
    assert len(result.tiles) == 16
    assert result.tiles[0].override_source_index == 0
    assert result.image.getpixel((1, 0)) == (40, 170, 80, 255)


def test_fragment_pattern_stays_incomplete_without_center_and_edge_roles() -> None:
    result = build_fragment_terrain_pattern(
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)),
        tile_size=(8, 8),
        fragments=[],
        master_layers=[],
        semantic_roles={},
        kind="wang_16",
    )

    assert not result.complete
    assert len(result.unassigned_masks) == 16


def test_tilesetter_blob_builds_from_base_and_directional_sources() -> None:
    atlas = Image.new("RGBA", (8, 4), (0, 0, 0, 0))
    atlas.paste((40, 160, 70, 255), (0, 0, 4, 4))
    edge = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    edge.paste((245, 210, 70, 255), (0, 0, 4, 1))
    atlas.alpha_composite(edge, (4, 0))
    sources = [
        {"id": "base", "x": 0, "y": 0, "width": 4, "height": 4},
        {"id": "edge", "x": 4, "y": 0, "width": 4, "height": 4},
    ]
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(4, 4),
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {
                "top": "edge",
                "right": "edge",
                "bottom": "edge",
                "left": "edge",
            },
            "edgeTransforms": {
                "top": {"rotation": 0},
                "right": {"rotation": 1},
                "bottom": {"rotation": 2},
                "left": {"rotation": 3},
            },
        },
        kind="blob_47",
    )

    assert result.complete
    assert len(result.tiles) == 47
    first = result.tiles[0]
    assert result.image.getpixel((first.column * 4, first.row * 4)) == (
        245,
        210,
        70,
        255,
    )


def test_tilesetter_blob_auto_orients_one_canonical_border_source() -> None:
    size = 8
    atlas = Image.new("RGBA", (size * 2, size), (40, 160, 70, 255))
    edge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    edge.putpixel((size // 2, 0), (245, 210, 70, 255))
    atlas.paste(edge, (size, 0))
    sources = [
        {"id": "base", "x": 0, "y": 0, "width": size, "height": size},
        {"id": "edge", "x": size, "y": 0, "width": size, "height": size},
    ]
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(size, size),
        sources=sources,
        set_config={
            "baseSource": "base",
            "autoOrientEdges": True,
            "edges": {direction: "edge" for direction in ("top", "right", "bottom", "left")},
            "cutoff": 0,
        },
        kind="blob_47",
    )

    top = next(role for role in result.tiles if role.mask == 124)
    top_rendered = result.image.crop(
        (top.column * size, top.row * size, (top.column + 1) * size, (top.row + 1) * size)
    )
    right = next(role for role in result.tiles if role.mask == 241)
    right_rendered = result.image.crop(
        (right.column * size, right.row * size, (right.column + 1) * size, (right.row + 1) * size)
    )
    assert top_rendered.getpixel((size // 2, 0)) == (245, 210, 70, 255)
    assert right_rendered.getpixel((size - 1, size // 2)) == (245, 210, 70, 255)


def test_tilesetter_blob_uses_complete_single_border_source() -> None:
    atlas = Image.new("RGBA", (12, 4), (0, 0, 0, 0))
    atlas.paste((40, 160, 70, 255), (0, 0, 4, 4))
    atlas.paste((20, 30, 45, 255), (4, 0, 8, 4))
    atlas.paste((235, 145, 55, 255), (4, 3, 8, 4))
    atlas.paste((70, 90, 220, 255), (8, 0, 12, 4))
    sources = [
        {"id": "base", "x": 0, "y": 0, "width": 4, "height": 4},
        {"id": "top", "x": 4, "y": 0, "width": 4, "height": 4},
        {"id": "other", "x": 8, "y": 0, "width": 4, "height": 4},
    ]
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(4, 4),
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {
                "top": "top",
                "right": "other",
                "bottom": "other",
                "left": "other",
            },
        },
        kind="blob_47",
    )

    top_only = next(role for role in result.tiles if role.mask == 124)
    rendered = result.image.crop(
        (
            top_only.column * 4,
            top_only.row * 4,
            (top_only.column + 1) * 4,
            (top_only.row + 1) * 4,
        )
    )
    assert rendered.getpixel((1, 0)) == (20, 30, 45, 255)
    assert rendered.getpixel((1, 2)) == (20, 30, 45, 255)
    assert rendered.getpixel((1, 3)) == (235, 145, 55, 255)


def test_tilesetter_blob_applies_cutoff_per_border_orientation() -> None:
    atlas = Image.new("RGBA", (12, 6), (0, 0, 0, 0))
    atlas.paste((40, 160, 70, 255), (0, 0, 6, 6))
    atlas.paste((240, 70, 70, 255), (6, 0, 12, 1))
    sources = [
        {"id": "base", "x": 0, "y": 0, "width": 6, "height": 6},
        {"id": "top", "x": 6, "y": 0, "width": 6, "height": 6},
    ]

    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(6, 6),
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {
                "top": "top",
                "right": "base",
                "bottom": "base",
                "left": "base",
            },
            "cutoff": 1,
            "edgeCutoffs": {"top": 3, "right": 1, "bottom": 1, "left": 1},
        },
        kind="blob_47",
    )

    top_only = next(role for role in result.tiles if role.mask == 124)
    origin = (top_only.column * 6, top_only.row * 6)
    assert result.image.getpixel((origin[0] + 2, origin[1])) == (
        240,
        70,
        70,
        255,
    )
    assert result.image.getpixel((origin[0] + 2, origin[1] + 1)) == (0, 0, 0, 0)
    assert result.image.getpixel((origin[0] + 2, origin[1] + 3)) == (
        40,
        160,
        70,
        255,
    )


def test_tilesetter_blob_clips_adjacent_complete_sources_at_a_merge_line() -> None:
    atlas = Image.new("RGBA", (12, 4), (0, 0, 0, 0))
    atlas.paste((40, 160, 70, 255), (0, 0, 4, 4))
    atlas.paste((230, 60, 60, 255), (4, 0, 8, 4))
    atlas.paste((60, 90, 230, 255), (8, 0, 12, 4))
    sources = [
        {"id": "base", "x": 0, "y": 0, "width": 4, "height": 4},
        {"id": "top", "x": 4, "y": 0, "width": 4, "height": 4},
        {"id": "left", "x": 8, "y": 0, "width": 4, "height": 4},
    ]
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(4, 4),
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {
                "top": "top",
                "right": "base",
                "bottom": "base",
                "left": "left",
            },
        },
        kind="blob_47",
    )

    top_left_exposed = next(role for role in result.tiles if role.mask == 28)
    origin = (top_left_exposed.column * 4, top_left_exposed.row * 4)
    assert result.image.getpixel((origin[0], origin[1] + 3)) == (
        60,
        90,
        230,
        255,
    )
    assert result.image.getpixel((origin[0] + 3, origin[1])) == (
        230,
        60,
        60,
        255,
    )


def test_tilesetter_blob_copies_one_source_per_pixel_without_alpha_blending() -> None:
    size = 4
    colors = {
        "base": (17, 37, 57, 83),
        "top": (237, 47, 67, 101),
        "right": (41, 211, 71, 137),
        "bottom": (31, 61, 227, 173),
        "left": (207, 43, 223, 209),
    }
    atlas = Image.new("RGBA", (size * len(colors), size))
    sources = []
    for index, (source_id, color) in enumerate(colors.items()):
        atlas.paste(color, (index * size, 0, (index + 1) * size, size))
        sources.append(
            {
                "id": source_id,
                "x": index * size,
                "y": 0,
                "width": size,
                "height": size,
            }
        )

    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(size, size),
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {
                direction: direction
                for direction in ("top", "right", "bottom", "left")
            },
            "cutoff": 1,
        },
        kind="blob_47",
    )

    rendered = _crop_pattern_role(result, 0)
    assert set(rendered.get_flattened_data()) <= set(colors.values())


def test_tilesetter_blob_uses_exact_edge_sources_required_by_each_role() -> None:
    size = 16
    colors = {
        "top": (250, 0, 0, 255),
        "right": (0, 250, 0, 255),
        "bottom": (0, 0, 250, 255),
        "left": (250, 0, 250, 255),
    }
    atlas = Image.new("RGBA", (size * 5, size), (100, 100, 100, 255))
    sources = [{"id": "base", "x": 0, "y": 0, "width": size, "height": size}]
    for index, (direction, color) in enumerate(colors.items(), start=1):
        atlas.paste(color, (index * size, 0, (index + 1) * size, size))
        sources.append(
            {
                "id": direction,
                "x": index * size,
                "y": 0,
                "width": size,
                "height": size,
            }
        )
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(size, size),
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {direction: direction for direction in colors},
            "cutoff": 2,
        },
        kind="blob_47",
    )
    corner_rules = (
        ("top_left", "top", "left"),
        ("top_right", "top", "right"),
        ("bottom_right", "bottom", "right"),
        ("bottom_left", "bottom", "left"),
    )

    for role in result.tiles:
        neighbors = set(role.neighbors)
        expected = {direction for direction in colors if direction not in neighbors}
        for diagonal, first, second in corner_rules:
            if first in neighbors and second in neighbors and diagonal not in neighbors:
                expected.update((first, second))
        rendered = result.image.crop(
            (
                role.column * size,
                role.row * size,
                (role.column + 1) * size,
                (role.row + 1) * size,
            )
        )
        pixels = set(rendered.get_flattened_data())
        actual = {
            direction for direction, color in colors.items() if color in pixels
        }
        assert actual == expected, f"mask {role.mask} used {actual}, expected {expected}"


def test_tilesetter_blob_custom_corners_replace_including_transparent_pixels() -> None:
    atlas = Image.new("RGBA", (12, 4), (0, 0, 0, 0))
    atlas.paste((40, 160, 70, 255), (0, 0, 4, 4))
    atlas.paste((40, 160, 70, 255), (4, 0, 8, 4))
    corner = Image.new("RGBA", (4, 4), (40, 160, 70, 255))
    corner.putpixel((0, 0), (250, 80, 120, 255))
    corner.putpixel((1, 1), (0, 0, 0, 0))
    corner.putpixel((3, 3), (70, 90, 250, 255))
    atlas.alpha_composite(corner, (8, 0))
    sources = [
        {"id": "base", "x": 0, "y": 0, "width": 4, "height": 4},
        {"id": "edge", "x": 4, "y": 0, "width": 4, "height": 4},
        {"id": "corner", "x": 8, "y": 0, "width": 4, "height": 4},
    ]

    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(4, 4),
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {
                "top": "edge",
                "right": "edge",
                "bottom": "edge",
                "left": "edge",
            },
            "corners": {
                "outer_top_left": "corner",
                "inner_top_left": "corner",
            },
            "customCorners": {
                "outer_top_left": True,
                "inner_top_left": True,
            },
        },
        kind="blob_47",
    )

    outer = next(role for role in result.tiles if role.mask == 0)
    inner = next(role for role in result.tiles if role.mask == 65)
    assert result.image.getpixel((outer.column * 4, outer.row * 4)) == (
        250,
        80,
        120,
        255,
    )
    assert result.image.getpixel((inner.column * 4, inner.row * 4)) == (
        250,
        80,
        120,
        255,
    )
    assert result.image.getpixel(
        (outer.column * 4 + 1, outer.row * 4 + 1)
    ) == (0, 0, 0, 0)
    assert result.image.getpixel(
        (outer.column * 4 + 3, outer.row * 4 + 3)
    ) == (40, 160, 70, 255)


def test_tilesetter_blob_automatically_splices_outer_and_inner_corners() -> None:
    atlas = Image.new("RGBA", (12, 4), (40, 160, 70, 255))
    top = Image.new("RGBA", (4, 4), (40, 160, 70, 255))
    for x in range(4):
        top.putpixel((x, 0), (240, 70, 70, 255))
    left = Image.new("RGBA", (4, 4), (40, 160, 70, 255))
    for y in range(4):
        left.putpixel((0, y), (70, 100, 240, 255))
    atlas.paste(top, (4, 0))
    atlas.paste(left, (8, 0))
    sources = [
        {"id": "base", "x": 0, "y": 0, "width": 4, "height": 4},
        {"id": "top", "x": 4, "y": 0, "width": 4, "height": 4},
        {"id": "left", "x": 8, "y": 0, "width": 4, "height": 4},
    ]

    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(4, 4),
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {
                "top": "top",
                "right": "base",
                "bottom": "base",
                "left": "left",
            },
        },
        kind="blob_47",
    )

    outer = next(role for role in result.tiles if role.mask == 0)
    outer_origin = (outer.column * 4, outer.row * 4)
    assert result.image.getpixel((outer_origin[0] + 1, outer_origin[1])) == (
        240,
        70,
        70,
        255,
    )
    assert result.image.getpixel((outer_origin[0], outer_origin[1] + 1)) == (
        70,
        100,
        240,
        255,
    )

    inner = next(role for role in result.tiles if role.mask == 65)
    inner_origin = (inner.column * 4, inner.row * 4)
    assert result.image.getpixel(inner_origin) in {
        (240, 70, 70, 255),
        (70, 100, 240, 255),
    }
    assert result.image.getpixel((inner_origin[0] + 1, inner_origin[1])) == (
        40,
        160,
        70,
        255,
    )
    assert result.image.getpixel((inner_origin[0], inner_origin[1] + 1)) == (
        40,
        160,
        70,
        255,
    )
    assert result.image.getpixel((inner_origin[0] + 2, inner_origin[1] + 2)) == (
        40,
        160,
        70,
        255,
    )


def test_tilesetter_wang_requires_two_centers_and_four_edges() -> None:
    atlas = Image.new("RGBA", (12, 4), (0, 0, 0, 0))
    atlas.paste((50, 170, 80, 255), (0, 0, 4, 4))
    atlas.paste((210, 170, 60, 255), (4, 0, 8, 4))
    edge = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    edge.paste((255, 255, 255, 255), (0, 1, 4, 2))
    atlas.alpha_composite(edge, (8, 0))
    sources = [
        {"id": "grass", "x": 0, "y": 0, "width": 4, "height": 4},
        {"id": "sand", "x": 4, "y": 0, "width": 4, "height": 4},
        {"id": "edge", "x": 8, "y": 0, "width": 4, "height": 4},
    ]
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(4, 4),
        sources=sources,
        set_config={
            "baseSource": "grass",
            "secondarySource": "sand",
            "edges": {
                "top": "edge",
                "right": "edge",
                "bottom": "edge",
                "left": "edge",
            },
        },
        kind="wang_16",
    )

    assert result.complete
    assert len(result.tiles) == 16


def _crop_pattern_role(result: object, mask: int) -> Image.Image:
    role = next(item for item in result.tiles if item.mask == mask)
    width = result.tile_width
    height = result.tile_height
    return result.image.crop(
        (
            role.column * width,
            role.row * height,
            (role.column + 1) * width,
            (role.row + 1) * height,
        )
    )


def _build_solid_wang(
    size: tuple[int, int],
    *,
    edge_order: tuple[str, ...] = ("top", "right", "bottom", "left"),
    edge_cutoffs: dict[str, int] | None = None,
    corners: dict[str, tuple[int, int, int, int]] | None = None,
) -> tuple[object, dict[str, tuple[int, int, int, int]]]:
    width, height = size
    colors = {
        "base": (11, 31, 51, 255),
        "secondary": (71, 91, 111, 83),
        "top": (241, 21, 31, 101),
        "right": (41, 221, 61, 137),
        "bottom": (31, 51, 231, 173),
        "left": (211, 41, 221, 209),
    }
    corner_colors = corners or {}
    source_colors = {**colors, **corner_colors}
    atlas = Image.new(
        "RGBA",
        (width * len(source_colors), height),
        (0, 0, 0, 0),
    )
    sources = []
    for index, (source_id, color) in enumerate(source_colors.items()):
        atlas.paste(
            color,
            (index * width, 0, (index + 1) * width, height),
        )
        sources.append(
            {
                "id": source_id,
                "x": index * width,
                "y": 0,
                "width": width,
                "height": height,
            }
        )
    configured_corners = {
        key: key for key in corner_colors
    }
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config={
            "baseSource": "base",
            "secondarySource": "secondary",
            "edges": {direction: direction for direction in edge_order},
            "cutoff": 0,
            "edgeCutoffs": edge_cutoffs or {},
            "corners": configured_corners,
            "customCorners": {key: True for key in configured_corners},
        },
        kind="wang_16",
    )
    return result, source_colors


def test_tilesetter_wang_splices_adjacent_complete_sources_without_blending() -> None:
    result, colors = _build_solid_wang((6, 4))

    rendered = _crop_pattern_role(result, 1)  # top + left, outer top-left

    assert set(_crop_pattern_role(result, 0).get_flattened_data()) == {
        colors["secondary"]
    }
    assert set(_crop_pattern_role(result, 15).get_flattened_data()) == {
        colors["base"]
    }
    assert rendered.getpixel((0, 0)) == colors["top"]
    assert rendered.getpixel((1, 0)) == colors["top"]
    assert rendered.getpixel((0, 1)) == colors["left"]
    assert set(rendered.get_flattened_data()) <= {
        colors["base"],
        colors["secondary"],
        colors["top"],
        colors["left"],
    }


def test_tilesetter_wang_opposite_edges_meet_at_exact_midpoint() -> None:
    result, colors = _build_solid_wang((5, 5))

    rendered = _crop_pattern_role(result, 3)  # left + right

    assert all(rendered.getpixel((0, y)) == colors["left"] for y in range(5))
    assert all(rendered.getpixel((4, y)) == colors["right"] for y in range(5))
    assert rendered.getpixel((2, 0)) == colors["right"]
    assert rendered.getpixel((2, 4)) == colors["left"]
    assert rendered.getpixel((2, 2)) in {colors["base"], colors["secondary"]}


def test_tilesetter_wang_four_way_crossing_has_deterministic_quadrants() -> None:
    result, colors = _build_solid_wang((5, 5))

    rendered = _crop_pattern_role(result, 5)

    assert rendered.getpixel((0, 0)) == colors["top"]
    assert rendered.getpixel((4, 0)) == colors["right"]
    assert rendered.getpixel((4, 4)) == colors["bottom"]
    assert rendered.getpixel((0, 4)) == colors["left"]
    assert rendered.getpixel((2, 2)) in {colors["base"], colors["secondary"]}
    assert set(rendered.get_flattened_data()) <= set(colors.values())


def test_tilesetter_wang_custom_outer_and_inner_corners_replace_composite() -> None:
    outer_color = (251, 121, 31, 67)
    inner_color = (21, 201, 231, 149)
    result, colors = _build_solid_wang(
        (5, 5),
        corners={
            "outer_top_left": outer_color,
            "inner_top_left": inner_color,
        },
    )

    outer = _crop_pattern_role(result, 1)
    inner = _crop_pattern_role(result, 14)

    assert outer.getpixel((0, 0)) == colors["outer_top_left"]
    assert outer.getpixel((1, 1)) == colors["outer_top_left"]
    assert inner.getpixel((0, 0)) == colors["inner_top_left"]
    assert inner.getpixel((1, 1)) == colors["inner_top_left"]
    # Odd-sized center axes belong to the automatic splice, not to any corner.
    assert outer.getpixel((2, 2)) != colors["outer_top_left"]
    assert inner.getpixel((2, 2)) != colors["inner_top_left"]


def test_tilesetter_wang_splice_is_independent_of_edge_mapping_order() -> None:
    forward, _ = _build_solid_wang((5, 5))
    reverse, _ = _build_solid_wang(
        (5, 5),
        edge_order=("left", "bottom", "right", "top"),
    )

    assert forward.image.tobytes() == reverse.image.tobytes()


def test_tilesetter_wang_diagonal_splice_rotates_with_corner_role() -> None:
    original, colors = _build_solid_wang((5, 5))
    # Rotate the Source assignments along with mask 1 (NW) to mask 2 (NE).
    width = height = 5
    source_order = ("base", "secondary", "top", "right", "bottom", "left")
    atlas = Image.new("RGBA", (width * len(source_order), height))
    sources = []
    for index, source_id in enumerate(source_order):
        atlas.paste(colors[source_id], (index * width, 0, (index + 1) * width, height))
        sources.append(
            {
                "id": source_id,
                "x": index * width,
                "y": 0,
                "width": width,
                "height": height,
            }
        )
    rotated = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(width, height),
        sources=sources,
        set_config={
            "baseSource": "base",
            "secondarySource": "secondary",
            "edges": {
                "top": "left",
                "right": "top",
                "bottom": "right",
                "left": "bottom",
            },
            "cutoff": 0,
        },
        kind="wang_16",
    )

    expected = _crop_pattern_role(original, 1).transpose(Image.Transpose.ROTATE_270)
    assert _crop_pattern_role(rotated, 2).tobytes() == expected.tobytes()


def test_tilesetter_wang_accepts_negative_directional_cutoff() -> None:
    neutral, colors = _build_solid_wang((5, 5))
    shifted, _ = _build_solid_wang(
        (5, 5),
        edge_cutoffs={"left": -1},
    )

    neutral_tile = _crop_pattern_role(neutral, 3)
    shifted_tile = _crop_pattern_role(shifted, 3)
    assert neutral_tile.getpixel((2, 2)) in {colors["base"], colors["secondary"]}
    assert shifted_tile.getpixel((2, 2)) == colors["left"]


def test_tilesetter_blob_opposite_sources_use_the_overlap_midpoint() -> None:
    size = 5
    colors = {
        "base": (40, 160, 70, 255),
        "top": (230, 60, 60, 255),
        "right": (50, 180, 80, 255),
        "bottom": (60, 90, 230, 255),
        "left": (70, 190, 90, 255),
    }
    atlas = Image.new("RGBA", (size * len(colors), size))
    sources = []
    for index, (source_id, color) in enumerate(colors.items()):
        atlas.paste(color, (index * size, 0, (index + 1) * size, size))
        sources.append({"id": source_id, "x": index * size, "y": 0, "width": size, "height": size})
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(size, size),
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {direction: direction for direction in ("top", "right", "bottom", "left")},
            "cutoff": 0,
        },
        kind="blob_47",
    )

    rendered = _crop_pattern_role(result, 68)  # top/bottom exposed, sides joined
    assert all(rendered.getpixel((x, 1)) == colors["top"] for x in range(size))
    assert all(rendered.getpixel((x, 2)) == colors["bottom"] for x in range(size))


def test_smart_blob_pattern_composites_base_edge_and_manual_override() -> None:
    atlas = Image.new("RGBA", (12, 4), (0, 0, 0, 0))
    atlas.paste((40, 160, 70, 255), (0, 0, 4, 4))
    edge = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    edge.paste((245, 210, 70, 255), (0, 0, 4, 1))
    atlas.alpha_composite(edge, (4, 0))
    atlas.paste((180, 40, 210, 255), (8, 0, 12, 4))

    result = build_smart_terrain_pattern(
        atlas,
        TilesetGrid(tile_width=4, tile_height=4),
        base_source=0,
        edge_source=1,
        kind="blob_47",
        cutoff=1,
        overrides={255: 2},
    )

    assert result.complete
    assert len(result.tiles) == 47
    assert result.tiles[0].generated
    assert result.tiles[-1].override_source_index == 2
    assert result.image.getpixel((0, 0)) == (245, 210, 70, 255)
    override_x = result.tiles[-1].column * 4
    override_y = result.tiles[-1].row * 4
    assert result.image.getpixel((override_x, override_y)) == (180, 40, 210, 255)


def test_smart_pattern_rejects_missing_sources() -> None:
    try:
        build_smart_terrain_pattern(
            Image.new("RGBA", (4, 4)),
            TilesetGrid(tile_width=4, tile_height=4),
            base_source=0,
            edge_source=3,
        )
    except ValueError as exc:
        assert "Missing source tile 3" in str(exc)
    else:
        raise AssertionError("Smart generation must validate every selected Source")


def test_smart_pattern_extracts_edge_detail_from_opaque_sample_tile() -> None:
    atlas = Image.new("RGBA", (8, 4), (30, 150, 60, 255))
    atlas.paste((240, 210, 50, 255), (4, 0, 8, 1))

    result = build_smart_terrain_pattern(
        atlas,
        TilesetGrid(tile_width=4, tile_height=4),
        base_source=0,
        edge_source=1,
        kind="sides_16",
    )

    assert result.image.getpixel((0, 0)) == (240, 210, 50, 255)
    assert result.image.getpixel((2, 2)) == (30, 150, 60, 255)
