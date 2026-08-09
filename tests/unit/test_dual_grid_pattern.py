import hashlib
import io
import json
import zipfile

import numpy as np
import pytest
from PIL import Image

from sprite_builder.tilesets import (
    TilesetGrid,
    build_fragment_terrain_pattern,
    build_manual_terrain_pattern,
    build_terrain_pattern_bundle,
    build_tilesetter_terrain_pattern,
    dual_grid_terrain_profiles,
    generate_terrain_pattern,
    render_godot_terrain_installer,
    terrain_pattern_layout,
    terrain_pattern_manifest,
    terrain_pattern_masks,
    terrain_pattern_set_layout,
)
from sprite_builder.tilesets.patterns import _render_dual_grid_pixels, _wang_bitmap_mask

_DUAL_GRID_LAYOUT = (
    (8, 6, 13, 12),
    (5, 14, 15, 11),
    (2, 3, 7, 9),
    (None, 4, 10, 1),
)
_DUAL_PEER_BITS = ("11", "15", "7", "3")  # TileMapDual: TL, TR, BL, BR.
_TILEMAP_DUAL_STANDARD_SEQUENCE = (
    (0, 3),
    (3, 3),
    (0, 2),
    (1, 2),
    (0, 0),
    (3, 2),
    (2, 3),
    (3, 1),
    (1, 3),
    (0, 1),
    (1, 0),
    (2, 2),
    (3, 0),
    (2, 0),
    (1, 1),
    (2, 1),
)
# TileMapDual counts TL, TR, BL, BR. The artistic mask counts NW, NE, SE, SW.
_TILEMAP_DUAL_INDEX_TO_ARTISTIC_MASK = (
    0,
    1,
    2,
    3,
    8,
    9,
    10,
    11,
    4,
    5,
    6,
    7,
    12,
    13,
    14,
    15,
)


def _crop_role(result: object, mask: int) -> Image.Image:
    tile = next(item for item in result.tiles if item.mask == mask)
    return result.image.crop(
        (
            tile.column * result.tile_width,
            tile.row * result.tile_height,
            (tile.column + 1) * result.tile_width,
            (tile.row + 1) * result.tile_height,
        )
    )


def _crop_atlas_cell(result: object, column: int, row: int) -> Image.Image:
    return result.image.crop(
        (
            column * result.tile_width,
            row * result.tile_height,
            (column + 1) * result.tile_width,
            (row + 1) * result.tile_height,
        )
    )


def _coordinate_texture(size: tuple[int, int], tag: int) -> Image.Image:
    """Encode source identity, source coordinate, and transparent pixels."""

    width, height = size
    image = Image.new("RGBA", size)
    for y in range(height):
        for x in range(width):
            alpha = (0, 29, 131, 255)[(tag + 3 * x + 5 * y) % 4]
            image.putpixel(
                (x, y),
                ((tag + 17 * x + 7 * y) % 256, x, y, alpha),
            )
    return image


def _dual_tilesetter_inputs(
    size: tuple[int, int],
) -> tuple[Image.Image, list[dict[str, object]], dict[str, object], dict[str, Image.Image]]:
    images = {
        "base": _coordinate_texture(size, 37),
        "secondary": _coordinate_texture(size, 173),
    }
    atlas = Image.new("RGBA", (size[0] * len(images), size[1]))
    sources: list[dict[str, object]] = []
    for index, (source_id, image) in enumerate(images.items()):
        atlas.paste(image, (index * size[0], 0))
        sources.append(
            {
                "id": source_id,
                "x": index * size[0],
                "y": 0,
                "width": size[0],
                "height": size[1],
            }
        )
    return atlas, sources, {"baseSource": "base", "secondarySource": "secondary"}, images


def _expected_two_source_role(
    base: Image.Image,
    secondary: Image.Image,
    mask: int,
) -> Image.Image:
    base_pixels = np.asarray(base, dtype=np.uint8)
    secondary_pixels = np.asarray(secondary, dtype=np.uint8)
    ownership = _wang_bitmap_mask(mask, base.width, base.height)
    return Image.fromarray(
        np.where(ownership[..., None], base_pixels, secondary_pixels).astype(np.uint8),
        mode="RGBA",
    )


def _rotate_mask_clockwise(mask: int) -> int:
    return sum(1 << ((bit + 1) % 4) for bit in range(4) if mask & (1 << bit))


def test_dual_grid_has_15_authored_masks_and_tilemapdual_standard_layout() -> None:
    assert terrain_pattern_masks("dual_grid_15") == tuple(range(1, 16))
    assert terrain_pattern_layout("dual_grid_15") == _DUAL_GRID_LAYOUT
    assert terrain_pattern_set_layout("dual_grid_15") == _DUAL_GRID_LAYOUT
    assert sum(mask is not None for row in _DUAL_GRID_LAYOUT for mask in row) == 15
    assert _DUAL_GRID_LAYOUT[3][0] is None  # physical mask 0 is synthesized.


@pytest.mark.parametrize("size", [(6, 4), (5, 7)])
def test_dual_grid_two_texture_generation_preserves_every_rgba_source_pixel(
    size: tuple[int, int],
) -> None:
    base = _coordinate_texture(size, 37)
    secondary = _coordinate_texture(size, 173)
    result = generate_terrain_pattern(base, secondary, kind="dual_grid_15")

    assert result.complete
    assert [role.mask for role in result.tiles] == list(range(1, 16))
    assert (result.columns, result.rows) == (4, 4)
    assert _crop_atlas_cell(result, 0, 3).tobytes() == secondary.tobytes()

    # Every output pixel is copied, never blended or shifted, from exactly one
    # of the two full texture sources. This includes RGB hidden by alpha 0.
    for mask in terrain_pattern_masks("dual_grid_15"):
        actual = _crop_role(result, mask)
        expected = _expected_two_source_role(base, secondary, mask)
        assert actual.tobytes() == expected.tobytes(), (size, mask)
        assert any(pixel[3] for pixel in actual.get_flattened_data())

    # Explicit semantic bit order: NW, NE, SE, SW maps to 1, 2, 4, 8.
    corners = {1: (0, 0), 2: (size[0] - 1, 0), 4: (size[0] - 1, size[1] - 1), 8: (0, size[1] - 1)}
    for mask, coordinate in corners.items():
        assert _crop_role(result, mask).getpixel(coordinate) == base.getpixel(coordinate)


def test_dual_grid_material_pair_profiles_are_stable_and_restrained() -> None:
    size = (16, 16)
    base = _coordinate_texture(size, 37)
    secondary = _coordinate_texture(size, 173)
    clean = generate_terrain_pattern(base, secondary, kind="dual_grid_15")
    profile_images: dict[str, bytes] = {}

    assert dual_grid_terrain_profiles() == (
        "clean",
        "grass_over_dirt",
        "dirt_over_water",
        "grass_over_water",
    )
    for profile in dual_grid_terrain_profiles()[1:]:
        result = generate_terrain_pattern(
            base,
            secondary,
            kind="dual_grid_15",
            terrain_profile=profile,
            edge_variation=2,
            edge_seed=17,
        )
        repeat = generate_terrain_pattern(
            base,
            secondary,
            kind="dual_grid_15",
            terrain_profile=profile,
            edge_variation=2,
            edge_seed=17,
        )

        assert result.image.tobytes() == repeat.image.tobytes()
        assert result.dual_grid_profile == profile
        assert result.dual_grid_edge_variation == 2
        assert result.dual_grid_edge_seed == 17
        assert _crop_role(result, 15).tobytes() == base.tobytes()
        assert _crop_atlas_cell(result, 0, 3).tobytes() == secondary.tobytes()

        changed_pixels = 0
        derived_pixels = 0
        for mask in range(1, 15):
            actual = np.asarray(_crop_role(result, mask), dtype=np.uint8)
            baseline = np.asarray(_crop_role(clean, mask), dtype=np.uint8)
            changed = np.any(actual != baseline, axis=2)
            changed_pixels += int(np.count_nonzero(changed))
            source_a = np.asarray(base, dtype=np.uint8)
            source_b = np.asarray(secondary, dtype=np.uint8)
            assert np.all(
                (actual[..., 3] == source_a[..., 3]) | (actual[..., 3] == source_b[..., 3])
            )
            derived = ~(np.all(actual == source_a, axis=2) | np.all(actual == source_b, axis=2))
            derived_pixels += int(np.count_nonzero(derived))
            assert int(np.count_nonzero(changed)) <= round(size[0] * size[1] * 0.70)

        assert changed_pixels > 0
        assert derived_pixels > 0
        profile_images[profile] = result.image.tobytes()

    assert len(set(profile_images.values())) == 3


@pytest.mark.parametrize("size", [(8, 8), (16, 16), (32, 32)])
def test_dual_grid_subtle_profiles_do_not_quantize_to_the_same_bitmap(
    size: tuple[int, int],
) -> None:
    """Every selector option must cause a visible, still restrained pixel change."""

    base = _coordinate_texture(size, 37)
    secondary = _coordinate_texture(size, 173)
    clean = generate_terrain_pattern(base, secondary, kind="dual_grid_15")
    profile_pixels: dict[str, np.ndarray] = {}

    for profile in dual_grid_terrain_profiles()[1:]:
        result = generate_terrain_pattern(
            base,
            secondary,
            kind="dual_grid_15",
            terrain_profile=profile,
            edge_variation=1,
            edge_seed=0,
        )
        actual = np.asarray(result.image, dtype=np.uint8)
        baseline = np.asarray(clean.image, dtype=np.uint8)
        changed = np.any(actual != baseline, axis=2)

        # At least 14 concrete pixels across the transition atlas change,
        # without turning the subtle preset into broad noise.
        assert int(np.count_nonzero(changed)) >= 14
        assert int(np.count_nonzero(changed)) <= round(size[0] * size[1] * 14 * 0.40)
        profile_pixels[profile] = actual

    for first_index, first in enumerate(profile_pixels):
        for second in list(profile_pixels)[first_index + 1 :]:
            pairwise_difference = np.count_nonzero(
                np.any(profile_pixels[first] != profile_pixels[second], axis=2)
            )
            assert int(pairwise_difference) >= 8, (size, first, second)


def test_dirt_over_water_builds_the_reference_ordered_pixel_bands() -> None:
    size = (32, 32)
    dirt = Image.new("RGBA", size, (112, 79, 68, 255))
    water = Image.new("RGBA", size, (72, 151, 160, 255))
    result = generate_terrain_pattern(
        dirt,
        water,
        kind="dual_grid_15",
        terrain_profile="dirt_over_water",
        edge_variation=3,
        edge_seed=451495,
    )
    tile = np.asarray(_crop_role(result, 3), dtype=np.uint8)
    column = tile[:, size[0] // 2, :3]

    assert tuple(column[0]) == (112, 79, 68)  # untouched dirt
    assert float(np.mean(column[10])) < float(np.mean(column[0]))  # dark bank
    assert float(np.mean(column[13])) > float(np.mean(column[0]))  # light bank
    assert float(np.mean(column[15])) > 190.0  # pale one-pixel rim
    assert float(np.mean(column[16])) < float(np.mean(column[-1]))  # water shadow
    assert tuple(column[-1]) == (72, 151, 160)  # untouched water
    assert len({tuple(pixel) for pixel in tile.reshape(-1, 4)}) >= 7
    assert np.all(tile[..., 3] == 255)


@pytest.mark.parametrize(
    "profile",
    ["grass_over_dirt", "dirt_over_water", "grass_over_water"],
)
@pytest.mark.parametrize("size", [4, 8, 16, 32])
def test_styled_dual_grid_roles_keep_compatible_edges_pixel_identical(
    profile: str,
    size: int,
) -> None:
    inside = np.full((size, size, 4), (90, 140, 70, 255), dtype=np.uint8)
    outside = np.full((size, size, 4), (70, 130, 160, 255), dtype=np.uint8)
    tiles = {
        mask: _render_dual_grid_pixels(
            inside,
            outside,
            mask,
            profile=profile,
            variation=3,
            seed=451495,
        )
        for mask in range(16)
    }

    for first_mask, first in tiles.items():
        for second_mask, second in tiles.items():
            horizontal_match = bool(first_mask & 2) == bool(second_mask & 1) and bool(
                first_mask & 4
            ) == bool(second_mask & 8)
            if horizontal_match:
                assert np.array_equal(first[:, -1], second[:, 0]), (
                    profile,
                    size,
                    first_mask,
                    second_mask,
                    "horizontal",
                )

            vertical_match = bool(first_mask & 8) == bool(second_mask & 1) and bool(
                first_mask & 4
            ) == bool(second_mask & 2)
            if vertical_match:
                assert np.array_equal(first[-1, :], second[0, :]), (
                    profile,
                    size,
                    first_mask,
                    second_mask,
                    "vertical",
                )


@pytest.mark.parametrize(
    "profile",
    ["grass_over_dirt", "dirt_over_water", "grass_over_water"],
)
def test_dual_grid_profile_zero_variation_preserves_the_clean_legacy_atlas(
    profile: str,
) -> None:
    base = _coordinate_texture((9, 7), 37)
    secondary = _coordinate_texture((9, 7), 173)
    clean = generate_terrain_pattern(base, secondary, kind="dual_grid_15")
    styled = generate_terrain_pattern(
        base,
        secondary,
        kind="dual_grid_15",
        terrain_profile=profile,
        edge_variation=0,
        edge_seed=875,
    )

    assert styled.image.tobytes() == clean.image.tobytes()


def test_dual_grid_profile_seed_changes_detail_and_keeps_quarter_turn_covariance() -> None:
    size = (16, 16)
    base = _coordinate_texture(size, 37)
    secondary = _coordinate_texture(size, 173)
    original = generate_terrain_pattern(
        base,
        secondary,
        kind="dual_grid_15",
        terrain_profile="grass_over_dirt",
        edge_variation=3,
        edge_seed=17,
    )
    different_seed = generate_terrain_pattern(
        base,
        secondary,
        kind="dual_grid_15",
        terrain_profile="grass_over_dirt",
        edge_variation=3,
        edge_seed=18,
    )
    rotated = generate_terrain_pattern(
        base.transpose(Image.Transpose.ROTATE_270),
        secondary.transpose(Image.Transpose.ROTATE_270),
        kind="dual_grid_15",
        terrain_profile="grass_over_dirt",
        edge_variation=3,
        edge_seed=17,
    )

    assert different_seed.image.tobytes() != original.image.tobytes()
    for mask in terrain_pattern_masks("dual_grid_15"):
        assert (
            _crop_role(rotated, _rotate_mask_clockwise(mask)).tobytes()
            == _crop_role(original, mask).transpose(Image.Transpose.ROTATE_270).tobytes()
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"terrain_profile": "lava_over_clouds"}, "Unsupported Dual Grid terrain profile"),
        ({"edge_variation": 4}, "variation must be an integer from 0 to 3"),
        ({"edge_seed": -1}, "seed must be an integer from 0 to 999999"),
    ],
)
def test_dual_grid_rejects_invalid_edge_profile_configuration(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        generate_terrain_pattern(
            Image.new("RGBA", (8, 8)),
            Image.new("RGBA", (8, 8)),
            kind="dual_grid_15",
            **kwargs,
        )


@pytest.mark.parametrize("size", [(6, 4), (5, 7)])
def test_dual_grid_two_texture_tilesetter_needs_no_edge_sources_or_placeholders(
    size: tuple[int, int],
) -> None:
    atlas, sources, config, images = _dual_tilesetter_inputs(size)
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config=config,
        kind="dual_grid_15",
    )

    assert result.complete
    assert len(result.tiles) == 15
    assert _crop_atlas_cell(result, 0, 3).tobytes() == images["secondary"].tobytes()
    for mask in terrain_pattern_masks("dual_grid_15"):
        assert (
            _crop_role(result, mask).tobytes()
            == _expected_two_source_role(images["base"], images["secondary"], mask).tobytes()
        )


@pytest.mark.parametrize("missing_source", ["base", "secondary"])
def test_dual_grid_overrides_cannot_make_missing_terrain_sources_exportable(
    missing_source: str,
) -> None:
    size = (4, 4)
    images = {
        "base": _coordinate_texture(size, 37),
        "secondary": _coordinate_texture(size, 173),
        "override": Image.new("RGBA", size, (241, 89, 31, 255)),
    }
    available = {
        source_id: image for source_id, image in images.items() if source_id != missing_source
    }
    atlas = Image.new("RGBA", (size[0] * len(available), size[1]))
    sources: list[dict[str, object]] = []
    for index, (source_id, image) in enumerate(available.items()):
        atlas.paste(image, (index * size[0], 0))
        sources.append(
            {
                "id": source_id,
                "x": index * size[0],
                "y": 0,
                "width": size[0],
                "height": size[1],
            }
        )
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config={
            "baseSource": "base",
            "secondarySource": "secondary",
            "overrides": {str(mask): "override" for mask in terrain_pattern_masks("dual_grid_15")},
        },
        kind="dual_grid_15",
    )

    assert not result.complete
    assert result.unassigned_masks == tuple(range(1, 16))
    assert all(role.source_index is None for role in result.tiles)
    # Overrides remain a useful preview, but cannot assert that the required
    # background/foreground runtime pair is ready.
    assert _crop_role(result, 7).tobytes() == images["override"].tobytes()
    if missing_source == "secondary":
        assert _crop_atlas_cell(result, 0, 3).getbbox() is None
    else:
        assert _crop_atlas_cell(result, 0, 3).tobytes() == images["secondary"].tobytes()
    with pytest.raises(ValueError, match="15 unassigned roles"):
        build_terrain_pattern_bundle(result)


def test_dual_grid_overrides_remain_exportable_after_both_terrain_sources_exist() -> None:
    size = (4, 4)
    atlas, sources, config, images = _dual_tilesetter_inputs(size)
    override = Image.new("RGBA", size, (241, 89, 31, 255))
    expanded = Image.new("RGBA", (atlas.width + size[0], atlas.height))
    expanded.paste(atlas, (0, 0))
    expanded.paste(override, (atlas.width, 0))
    sources.append(
        {
            "id": "override",
            "x": atlas.width,
            "y": 0,
            "width": size[0],
            "height": size[1],
        }
    )
    config["overrides"] = {"7": "override"}

    result = build_tilesetter_terrain_pattern(
        expanded,
        tile_size=size,
        sources=sources,
        set_config=config,
        kind="dual_grid_15",
    )

    assert result.complete
    assert all(role.source_index is not None for role in result.tiles)
    assert _crop_role(result, 7).tobytes() == override.tobytes()
    assert _crop_atlas_cell(result, 0, 3).tobytes() == images["secondary"].tobytes()
    assert build_terrain_pattern_bundle(result)


def test_dual_grid_ignores_stale_edge_and_corner_sources_from_migrated_config() -> None:
    size = (5, 7)
    base = _coordinate_texture(size, 37)
    secondary = _coordinate_texture(size, 173)
    stale_green = Image.new("RGBA", size, (11, 251, 17, 255))
    atlas = Image.new("RGBA", (size[0] * 3, size[1]))
    sources: list[dict[str, object]] = []
    for index, (source_id, image) in enumerate(
        (("base", base), ("secondary", secondary), ("stale-green", stale_green))
    ):
        atlas.paste(image, (index * size[0], 0))
        sources.append(
            {
                "id": source_id,
                "x": index * size[0],
                "y": 0,
                "width": size[0],
                "height": size[1],
            }
        )
    clean_config = {"baseSource": "base", "secondarySource": "secondary"}
    stale_config = {
        **clean_config,
        "autoOrientEdges": True,
        "edges": {direction: "stale-green" for direction in ("top", "right", "bottom", "left")},
        "edgeTransforms": {
            direction: {"rotation": 1, "flipX": True}
            for direction in ("top", "right", "bottom", "left")
        },
        "corners": {
            f"{corner_type}_{diagonal}": "stale-green"
            for corner_type in ("outer", "inner")
            for diagonal in ("top_left", "top_right", "bottom_right", "bottom_left")
        },
        "customCorners": {
            f"{corner_type}_{diagonal}": True
            for corner_type in ("outer", "inner")
            for diagonal in ("top_left", "top_right", "bottom_right", "bottom_left")
        },
        "cornerTransforms": {
            f"{corner_type}_{diagonal}": {"rotation": 3, "flipY": True}
            for corner_type in ("outer", "inner")
            for diagonal in ("top_left", "top_right", "bottom_right", "bottom_left")
        },
    }

    clean = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config=clean_config,
        kind="dual_grid_15",
    )
    migrated = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config=stale_config,
        kind="dual_grid_15",
    )

    assert clean.complete and migrated.complete
    assert migrated.image.tobytes() == clean.image.tobytes()
    assert (11, 251, 17, 255) not in migrated.image.get_flattened_data()
    for mask in terrain_pattern_masks("dual_grid_15"):
        assert (
            _crop_role(migrated, mask).tobytes()
            == _expected_two_source_role(base, secondary, mask).tobytes()
        )


@pytest.mark.parametrize("size", [(6, 4), (5, 7)])
def test_dual_grid_corner_roles_rotate_with_their_source_ownership(
    size: tuple[int, int],
) -> None:
    base = _coordinate_texture(size, 37)
    secondary = _coordinate_texture(size, 173)
    original = generate_terrain_pattern(base, secondary, kind="dual_grid_15")
    rotated = generate_terrain_pattern(
        base.transpose(Image.Transpose.ROTATE_270),
        secondary.transpose(Image.Transpose.ROTATE_270),
        kind="dual_grid_15",
    )

    for mask in terrain_pattern_masks("dual_grid_15"):
        assert (
            _crop_role(rotated, _rotate_mask_clockwise(mask)).tobytes()
            == _crop_role(original, mask).transpose(Image.Transpose.ROTATE_270).tobytes()
        )


def test_dual_grid_manifest_and_installer_follow_tilemapdual_v5_contract() -> None:
    result = generate_terrain_pattern(
        _coordinate_texture((4, 4), 37),
        _coordinate_texture((4, 4), 173),
        kind="dual_grid_15",
    )
    manifest = terrain_pattern_manifest(result, terrain_name="Dual")

    assert manifest["godot"]["mode"] == "match_corners"
    assert manifest["godot"]["terrain"] == {
        "background": 0,
        "foreground": 1,
        "transitions": -1,
    }
    assert manifest["dual_grid"]["runtime"] == "TileMapDual"
    assert manifest["dual_grid"]["atlas_layout"] == "tilemapdual_standard_4x4"
    assert manifest["dual_grid"]["topology"] == "square"
    assert manifest["dual_grid"]["neighborhood"] == "square"
    assert manifest["dual_grid"]["terrain_profile"] == "clean"
    assert manifest["dual_grid"]["edge_variation"] == 0
    assert manifest["dual_grid"]["edge_seed"] == 0
    assert manifest["dual_grid"]["edge_generation"] == "deterministic_palette_bands"
    assert manifest["dual_grid"]["corner_order"] == [
        "top_left",
        "top_right",
        "bottom_right",
        "bottom_left",
    ]
    assert manifest["dual_grid"]["tilemap_dual_peering_order"] == [
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
    ]

    by_mask = {tile["mask"]: tile for tile in manifest["tiles"]}
    assert sorted(by_mask) == list(range(16))
    assert len(manifest["tiles"]) == 16
    assert by_mask[0]["column"] == 0 and by_mask[0]["row"] == 3
    assert by_mask[0]["role"] == "background" and by_mask[0]["terrain"] == 0
    assert by_mask[0]["peering_bits"] == {bit: 0 for bit in _DUAL_PEER_BITS}
    assert by_mask[15]["column"] == 2 and by_mask[15]["row"] == 1
    assert by_mask[15]["role"] == "foreground" and by_mask[15]["terrain"] == 1
    assert by_mask[15]["peering_bits"] == {bit: 1 for bit in _DUAL_PEER_BITS}
    assert by_mask[4]["peering_bits"] == {"11": 0, "15": 0, "7": 0, "3": 1}
    assert by_mask[8]["peering_bits"] == {"11": 0, "15": 0, "7": 1, "3": 0}
    assert [
        (by_mask[mask]["column"], by_mask[mask]["row"])
        for mask in _TILEMAP_DUAL_INDEX_TO_ARTISTIC_MASK
    ] == list(_TILEMAP_DUAL_STANDARD_SEQUENCE)
    for mask in range(1, 15):
        assert by_mask[mask]["role"] == "transition"
        assert by_mask[mask]["terrain"] == -1
    assert all(
        set(tile["peering_bits"].values()) <= {0, 1}
        and set(tile["peering_bits"]) == set(_DUAL_PEER_BITS)
        for tile in by_mask.values()
    )

    installer = render_godot_terrain_installer(result, terrain_name="Dual")
    assert "TERRAIN_MODE_MATCH_CORNERS" in installer
    assert "TERRAIN_MODE_MATCH_CORNERS_AND_SIDES" not in installer
    assert installer.count("tile_set.add_terrain(0)") == 2
    assert 'tile_data.terrain = entry["terrain"]' in installer
    assert installer.count('"coords": Vector2i(') == 16
    assert installer.count('"terrain": -1') == 14
    assert "var script_dir := get_script().resource_path.get_base_dir()" in installer
    assert 'load(script_dir.path_join("terrain_tiles.png"))' in installer
    assert 'ResourceSaver.save(tile_set, script_dir.path_join("terrain_tileset.tres"))' in installer
    assert "res://terrain_tiles" not in installer


def test_tilesetter_dual_grid_profile_round_trips_into_export_metadata() -> None:
    atlas, sources, config, _ = _dual_tilesetter_inputs((16, 16))
    config.update(
        {
            "terrainProfile": "dirt_over_water",
            "edgeVariation": 2,
            "edgeSeed": 314,
        }
    )

    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="dual_grid_15",
    )
    manifest = terrain_pattern_manifest(result)

    assert result.dual_grid_profile == "dirt_over_water"
    assert result.dual_grid_edge_variation == 2
    assert result.dual_grid_edge_seed == 314
    assert manifest["dual_grid"]["terrain_profile"] == "dirt_over_water"
    assert manifest["dual_grid"]["edge_variation"] == 2
    assert manifest["dual_grid"]["edge_seed"] == 314


def test_dual_grid_installer_preserves_explicit_res_paths() -> None:
    result = generate_terrain_pattern(
        _coordinate_texture((4, 4), 37),
        _coordinate_texture((4, 4), 173),
        kind="dual_grid_15",
    )

    installer = render_godot_terrain_installer(
        result,
        texture_resource_path="res://art/dual_tiles.png",
        tileset_resource_path="res://tilesets/dual/dual_tileset.tres",
    )

    assert 'load("res://art/dual_tiles.png")' in installer
    assert 'ResourceSaver.save(tile_set, "res://tilesets/dual/dual_tileset.tres")' in installer
    assert "var script_dir" not in installer
    assert ".import" not in installer


def test_dual_grid_bundle_contains_a_tilemapdual_ready_background_slot_and_checksum() -> None:
    base = _coordinate_texture((5, 7), 37)
    secondary = _coordinate_texture((5, 7), 173)
    result = generate_terrain_pattern(base, secondary, kind="dual_grid_15")

    with zipfile.ZipFile(io.BytesIO(build_terrain_pattern_bundle(result))) as archive:
        assert all(not name.endswith(".import") for name in archive.namelist())
        atlas_bytes = archive.read("terrain_tiles.png")
        manifest = json.loads(archive.read("terrain_pattern.json"))
        installer = archive.read("install_terrain_tileset.gd").decode("utf-8")
        readme = archive.read("README.txt").decode("utf-8")
        exported = Image.open(io.BytesIO(atlas_bytes)).convert("RGBA")
        reference = Image.open(io.BytesIO(archive.read("terrain_bitmask_reference.png"))).convert(
            "RGBA"
        )

    assert manifest["atlas"]["sha256"] == hashlib.sha256(atlas_bytes).hexdigest()
    assert exported.crop((0, 3 * 7, 5, 4 * 7)).tobytes() == secondary.tobytes()
    assert "TileMapDual node with Square topology" in readme
    assert "do not support isometric, hexagonal, or triangle" in readme
    assert "masks 1 through 14 are transitions" in readme
    assert "Do not paint the omitted mask 0" not in readme
    assert "may live in any project subfolder" in readme
    # For example, extraction at res://tilesets/dual makes script_dir that
    # subfolder; no bundle file is pinned to project root.
    assert "var script_dir := get_script().resource_path.get_base_dir()" in installer
    assert 'load(script_dir.path_join("terrain_tiles.png"))' in installer
    assert 'ResourceSaver.save(tile_set, script_dir.path_join("terrain_tileset.tres"))' in installer
    assert "res://terrain_tiles" not in installer
    # This guide represents 15 authored masks; the actual runtime atlas above
    # owns its physical mask-0 cell.
    assert reference.getpixel((24, 3 * 48 + 24)) == (255, 255, 255, 255)


def test_dual_grid_rejects_collapsed_and_nonstandard_atlas_geometry() -> None:
    with pytest.raises(ValueError, match="at least 2x2"):
        generate_terrain_pattern(
            Image.new("RGBA", (1, 2)),
            Image.new("RGBA", (1, 2)),
            kind="dual_grid_15",
        )
    with pytest.raises(ValueError, match="fixed 4x4 layout"):
        generate_terrain_pattern(
            Image.new("RGBA", (2, 2)),
            Image.new("RGBA", (2, 2)),
            kind="dual_grid_15",
            columns=4,
        )


def test_dual_grid_authoring_paths_cannot_silently_export_without_background() -> None:
    atlas = Image.new("RGBA", (4, 4), (30, 70, 190, 255))
    with pytest.raises(ValueError, match="require background_source"):
        build_manual_terrain_pattern(
            atlas,
            TilesetGrid(tile_width=4, tile_height=4),
            {},
            kind="dual_grid_15",
        )
    with pytest.raises(ValueError, match="requires two complete textures"):
        build_fragment_terrain_pattern(
            atlas,
            tile_size=(4, 4),
            fragments=[],
            master_layers=[],
            semantic_roles={},
            kind="dual_grid_15",
        )


def test_existing_terrain_patterns_keep_their_masks_layouts_and_modes() -> None:
    assert terrain_pattern_masks("wang_16") == tuple(range(16))
    assert terrain_pattern_masks("sides_16") == tuple(range(16))
    assert len(terrain_pattern_masks("blob_47")) == 47
    assert terrain_pattern_layout("wang_16")[3][0] == 0
    assert terrain_pattern_layout("sides_16")[3] == (0, 2, 10, 8)

    inside = Image.new("RGBA", (4, 4), (220, 50, 60, 255))
    outside = Image.new("RGBA", (4, 4), (30, 40, 150, 255))
    for kind, expected_mode, expected_count in (
        ("wang_16", "match_corners", 16),
        ("sides_16", "match_sides", 16),
        ("blob_47", "match_corners_and_sides", 47),
    ):
        result = generate_terrain_pattern(inside, outside, kind=kind)
        assert result.mode == expected_mode
        assert len(result.tiles) == expected_count
