"""Adversarial tests for TileSetter-style full-Source composition.

These tests intentionally use coordinate-dependent RGBA samples.  Solid-color
fixtures can hide resampling, wrong transforms, and alpha blending at seams.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations

import numpy as np
import pytest
from PIL import Image

from sprite_builder.tilesets import build_tilesetter_terrain_pattern
from sprite_builder.tilesets.patterns import _wang_edge_owner_masks

DIRECTIONS = ("top", "right", "bottom", "left")
CORNERS = ("top_left", "top_right", "bottom_right", "bottom_left")
INCIDENT = {
    "top_left": ("top", "left"),
    "top_right": ("top", "right"),
    "bottom_right": ("bottom", "right"),
    "bottom_left": ("bottom", "left"),
}


def _pattern(size: tuple[int, int], seed: int, *, transparent: bool = False) -> Image.Image:
    """Make every source/coordinate identifiable, including its alpha."""

    width, height = size
    image = Image.new("RGBA", size)
    alpha_values = (37, 83, 149, 211)
    pixels = []
    for y in range(height):
        for x in range(width):
            alpha = alpha_values[(seed + 3 * x + 5 * y) % len(alpha_values)]
            if transparent and (2 * x + 3 * y + seed) % 5 == 0:
                alpha = 0
            pixels.append(
                (
                    1 + (43 * seed + 17 * x + 7 * y) % 251,
                    1 + (71 * seed + 11 * x + 19 * y) % 251,
                    1 + (97 * seed + 23 * x + 13 * y) % 251,
                    alpha,
                )
            )
    image.putdata(pixels)
    return image


def _opaque_pattern(size: tuple[int, int], seed: int) -> Image.Image:
    image = _pattern(size, seed)
    image.putalpha(255)
    return image


def _atlas(images: Mapping[str, Image.Image]) -> tuple[Image.Image, list[dict[str, object]]]:
    widths = [image.width for image in images.values()]
    height = max(image.height for image in images.values())
    atlas = Image.new("RGBA", (sum(widths), height), (0, 0, 0, 0))
    sources: list[dict[str, object]] = []
    x = 0
    for source_id, image in images.items():
        atlas.paste(image, (x, 0))
        sources.append(
            {
                "id": source_id,
                "x": x,
                "y": 0,
                "width": image.width,
                "height": image.height,
            }
        )
        x += image.width
    return atlas, sources


def _crop_role(result: object, mask: int) -> Image.Image:
    role = next(role for role in result.tiles if role.mask == mask)
    width, height = result.tile_width, result.tile_height
    return result.image.crop(
        (
            role.column * width,
            role.row * height,
            (role.column + 1) * width,
            (role.row + 1) * height,
        )
    )


def _transform(
    image: Image.Image,
    size: tuple[int, int],
    *,
    rotation: int = 0,
    flip_x: bool = False,
    flip_y: bool = False,
) -> Image.Image:
    """Independent public-Pillow description of a configured Source transform."""

    fitted = image.resize(size, Image.Resampling.NEAREST)
    if flip_x:
        fitted = fitted.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_y:
        fitted = fitted.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    turns = rotation % 4
    if turns == 1:
        fitted = fitted.transpose(Image.Transpose.ROTATE_270)
    elif turns == 2:
        fitted = fitted.transpose(Image.Transpose.ROTATE_180)
    elif turns == 3:
        fitted = fitted.transpose(Image.Transpose.ROTATE_90)
    return fitted.resize(size, Image.Resampling.NEAREST)


def _visible(pixel: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    # Alpha-compositing a fully transparent pixel onto the empty result atlas
    # canonicalizes its hidden RGB channels.
    return pixel if pixel[3] else (0, 0, 0, 0)


def _wang_transitions(mask: int) -> dict[str, bool]:
    nw, ne, se, sw = (bool(mask & (1 << bit)) for bit in range(4))
    return {
        "top": nw != ne,
        "right": ne != se,
        "bottom": sw != se,
        "left": nw != sw,
    }


def _wang_build(
    size: tuple[int, int],
    *,
    reverse_mapping: bool = False,
    transforms: Mapping[str, Mapping[str, object]] | None = None,
    edge_cutoffs: Mapping[str, int] | None = None,
    custom_corners: bool = False,
) -> tuple[object, dict[str, Image.Image]]:
    names = ["base", "secondary", *DIRECTIONS]
    if custom_corners:
        names += [f"{kind}_{corner}" for kind in ("outer", "inner") for corner in CORNERS]
    images = {
        name: _pattern(size, index + 1, transparent=custom_corners and "_" in name)
        for index, name in enumerate(names)
    }
    atlas, sources = _atlas(images)
    edge_items = list((direction, direction) for direction in DIRECTIONS)
    if reverse_mapping:
        edge_items.reverse()
        sources.reverse()
    corner_names = [name for name in names if name.startswith(("outer_", "inner_"))]
    config: dict[str, object] = {
        "baseSource": "base",
        "secondarySource": "secondary",
        "edges": dict(edge_items),
        "edgeTransforms": transforms or {},
        "edgeCutoffs": edge_cutoffs or {},
        "cutoff": 0,
    }
    if corner_names:
        config["corners"] = {name: name for name in corner_names}
        config["customCorners"] = {name: True for name in corner_names}
    return (
        build_tilesetter_terrain_pattern(
            atlas,
            tile_size=size,
            sources=sources,
            set_config=config,
            kind="wang_16",
        ),
        images,
    )


def test_wang_edge_profile_preserves_authored_border_pixels() -> None:
    size = (48, 48)
    base = Image.new("RGBA", size, (140, 110, 80, 255))
    secondary = Image.new("RGBA", size, (54, 110, 160, 255))
    edge = Image.new("RGBA", size, (0, 0, 0, 0))
    for y in range(6):
        for x in range(size[0]):
            edge.putpixel((x, y), (64, 129, 38, 255))
    atlas, sources = _atlas({"base": base, "secondary": secondary, "top": edge})
    common = {
        "baseSource": "base",
        "secondarySource": "secondary",
        "edges": {direction: "top" for direction in DIRECTIONS},
        "edgeTransforms": {
            "top": {"rotation": 0},
            "right": {"rotation": 1},
            "bottom": {"rotation": 2},
            "left": {"rotation": 3},
        },
        "cutoff": 0,
    }
    clean = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config={**common, "terrainProfile": "clean"},
        kind="wang_16",
    )
    styled = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config={
            **common,
            "terrainProfile": "dirt_over_water",
            "edgeVariation": 3,
            "edgeSeed": 451495,
        },
        kind="wang_16",
    )
    mask = 1
    clean_pixels = np.asarray(_crop_role(clean, mask), dtype=np.uint8)
    styled_pixels = np.asarray(_crop_role(styled, mask), dtype=np.uint8)
    transitions = _wang_transitions(mask)
    available = tuple(direction for direction in DIRECTIONS if transitions[direction])
    owners = _wang_edge_owner_masks(
        size,
        available,
        {direction: 0 for direction in DIRECTIONS},
    )
    transformed_edge = {
        "top": edge,
        "right": edge.transpose(Image.Transpose.ROTATE_270),
        "bottom": edge.transpose(Image.Transpose.ROTATE_180),
        "left": edge.transpose(Image.Transpose.ROTATE_90),
    }
    authored = np.zeros((size[1], size[0]), dtype=bool)
    for direction, owner in owners.items():
        authored |= owner & (
            np.asarray(transformed_edge[direction].getchannel("A"), dtype=np.uint8) != 0
        )

    assert authored.any()
    assert np.array_equal(styled_pixels[authored], clean_pixels[authored])
    assert np.any(styled_pixels[6:12] != clean_pixels[6:12])
    assert np.array_equal(styled_pixels[12:36, 12:36], clean_pixels[12:36, 12:36])


def test_wang_transparent_border_padding_keeps_the_two_materials_visible() -> None:
    size = (48, 48)
    base_color = (140, 110, 80, 255)
    secondary_color = (54, 110, 160, 255)
    base = Image.new("RGBA", size, base_color)
    secondary = Image.new("RGBA", size, secondary_color)
    edge = Image.new("RGBA", size, (0, 0, 0, 0))
    for y in range(6):
        for x in range(size[0]):
            edge.putpixel((x, y), (64, 129, 38, 255))
    atlas, sources = _atlas({"base": base, "secondary": secondary, "top": edge})
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config={
            "baseSource": "base",
            "secondarySource": "secondary",
            "edges": {direction: "top" for direction in DIRECTIONS},
            "edgeTransforms": {
                "top": {"rotation": 0},
                "right": {"rotation": 1},
                "bottom": {"rotation": 2},
                "left": {"rotation": 3},
            },
        },
        kind="wang_16",
    )
    rendered = np.asarray(_crop_role(result, 1), dtype=np.uint8)

    authored_colors = {base_color, secondary_color, (64, 129, 38, 255)}
    assert np.all(rendered[..., 3] == 255)
    assert set(map(tuple, rendered.reshape(-1, 4))) <= authored_colors


@pytest.mark.parametrize("size", [(4, 4), (5, 5), (7, 4), (4, 7)])
def test_wang_all_16_roles_have_single_source_pixel_provenance(
    size: tuple[int, int],
) -> None:
    transforms = {
        "top": {"rotation": 0, "flipX": True},
        "right": {"rotation": 1, "flipY": True},
        "bottom": {"rotation": 2, "flipX": True, "flipY": True},
        "left": {"rotation": 3},
    }
    result, images = _wang_build(size, transforms=transforms)
    transformed = {
        direction: _transform(
            images[direction],
            size,
            rotation=int(transforms[direction].get("rotation", 0)),
            flip_x=bool(transforms[direction].get("flipX", False)),
            flip_y=bool(transforms[direction].get("flipY", False)),
        )
        for direction in DIRECTIONS
    }

    for mask in range(16):
        rendered = _crop_role(result, mask)
        transitions = _wang_transitions(mask)
        allowed = [images["base"], images["secondary"]]
        allowed.extend(transformed[direction] for direction in DIRECTIONS if transitions[direction])
        for y in range(size[1]):
            for x in range(size[0]):
                candidates = {_visible(source.getpixel((x, y))) for source in allowed}
                assert rendered.getpixel((x, y)) in candidates, (
                    f"mask={mask}, size={size}, coordinate={(x, y)} produced a "
                    "pixel that is not present in any eligible full Source"
                )


@pytest.mark.parametrize("size", [(4, 4), (5, 5), (7, 4), (4, 7)])
def test_wang_owner_masks_are_pairwise_disjoint_for_every_edge_formation_and_cutoff(
    size: tuple[int, int],
) -> None:
    cutoff_cases = (
        {direction: 0 for direction in DIRECTIONS},
        {"top": -2, "right": 1, "bottom": 2, "left": -1},
        {"top": 2, "right": -2, "bottom": -1, "left": 1},
    )
    formations = [
        directions for count in range(1, 5) for directions in combinations(DIRECTIONS, count)
    ]
    for directions in formations:
        for cutoffs in cutoff_cases:
            owners = _wang_edge_owner_masks(size, directions, cutoffs)
            occupancy = np.zeros((size[1], size[0]), dtype=np.uint8)
            for owner in owners.values():
                occupancy += owner.astype(np.uint8)
            assert np.all(occupancy <= 1), (size, directions, cutoffs, occupancy)


def test_wang_mapping_order_and_repeated_build_are_byte_stable() -> None:
    first, _ = _wang_build((7, 5))
    reordered, _ = _wang_build((7, 5), reverse_mapping=True)
    repeated, _ = _wang_build((7, 5))

    assert first.image.tobytes() == reordered.image.tobytes()
    assert first.image.tobytes() == repeated.image.tobytes()


def _rotate_wang_mask_clockwise(mask: int) -> int:
    return sum((1 << ((bit + 1) % 4)) for bit in range(4) if mask & (1 << bit))


def test_wang_coordinate_artwork_is_rotationally_symmetric_for_all_roles() -> None:
    size = (7, 7)
    names = ("base", "secondary", *DIRECTIONS)
    original_images = {name: _pattern(size, index + 20) for index, name in enumerate(names)}
    original_atlas, original_sources = _atlas(original_images)
    original = build_tilesetter_terrain_pattern(
        original_atlas,
        tile_size=size,
        sources=original_sources,
        set_config={
            "baseSource": "base",
            "secondarySource": "secondary",
            "edges": {direction: direction for direction in DIRECTIONS},
            "cutoff": 0,
        },
        kind="wang_16",
    )

    rotated_images = {
        name: image.transpose(Image.Transpose.ROTATE_270) for name, image in original_images.items()
    }
    rotated_atlas, rotated_sources = _atlas(rotated_images)
    # A clockwise canvas rotation maps old L,T,R,B Sources to new T,R,B,L.
    rotated = build_tilesetter_terrain_pattern(
        rotated_atlas,
        tile_size=size,
        sources=rotated_sources,
        set_config={
            "baseSource": "base",
            "secondarySource": "secondary",
            "edges": {"top": "left", "right": "top", "bottom": "right", "left": "bottom"},
            "cutoff": 0,
        },
        kind="wang_16",
    )

    for mask in range(16):
        expected = _crop_role(original, mask).transpose(Image.Transpose.ROTATE_270)
        actual = _crop_role(rotated, _rotate_wang_mask_clockwise(mask))
        assert actual.tobytes() == expected.tobytes(), f"rotation failed for mask {mask}"


def test_wang_positive_and_negative_cutoffs_move_ownership_without_blending() -> None:
    neutral, images = _wang_build((7, 5), edge_cutoffs={"left": 0})
    expanded, _ = _wang_build((7, 5), edge_cutoffs={"left": -2})
    contracted, _ = _wang_build((7, 5), edge_cutoffs={"left": 2})

    def left_count(result: object) -> int:
        rendered = _crop_role(result, 3)  # opposite left/right transitions
        return sum(
            rendered.getpixel((x, y)) == images["left"].getpixel((x, y))
            for y in range(5)
            for x in range(7)
        )

    assert left_count(expanded) > left_count(neutral) > left_count(contracted)


def _quadrant(size: tuple[int, int], corner: str) -> tuple[int, int, int, int]:
    width, height = size
    split_x, split_y = width // 2, height // 2
    far_x, far_y = (width + 1) // 2, (height + 1) // 2
    return {
        "top_left": (0, 0, split_x, split_y),
        "top_right": (far_x, 0, width, split_y),
        "bottom_right": (far_x, far_y, width, height),
        "bottom_left": (0, far_y, split_x, height),
    }[corner]


def _matching_wang_mask(corner: str, corner_type: str) -> int:
    corner_bit = CORNERS.index(corner)
    first, second = INCIDENT[corner]
    for mask in range(16):
        transitions = _wang_transitions(mask)
        bit = bool(mask & (1 << corner_bit))
        if transitions[first] and transitions[second] and bit == (corner_type == "outer"):
            return mask
    raise AssertionError("no matching Wang role")


@pytest.mark.parametrize("size", [(6, 4), (5, 5)])
def test_wang_all_custom_corners_replace_quadrants_including_transparent_pixels(
    size: tuple[int, int],
) -> None:
    result, images = _wang_build(size, custom_corners=True)

    for corner_type in ("outer", "inner"):
        for corner in CORNERS:
            key = f"{corner_type}_{corner}"
            rendered = _crop_role(result, _matching_wang_mask(corner, corner_type))
            x0, y0, x1, y1 = _quadrant(size, corner)
            for y in range(y0, y1):
                for x in range(x0, x1):
                    assert rendered.getpixel((x, y)) == _visible(images[key].getpixel((x, y)))


def _blob_build_with_rgba_sources(
    size: tuple[int, int],
    *,
    custom_corners: bool = False,
    cutoff: int = 0,
) -> tuple[object, dict[str, Image.Image]]:
    names = ["base", *DIRECTIONS]
    if custom_corners:
        names += [f"{kind}_{corner}" for kind in ("outer", "inner") for corner in CORNERS]
    images = {
        name: _pattern(size, 50 + index, transparent=custom_corners and "_" in name)
        for index, name in enumerate(names)
    }
    atlas, sources = _atlas(images)
    config: dict[str, object] = {
        "baseSource": "base",
        "edges": {direction: direction for direction in DIRECTIONS},
        "cutoff": cutoff,
    }
    if custom_corners:
        corner_names = [name for name in names if name.startswith(("outer_", "inner_"))]
        config["corners"] = {name: name for name in corner_names}
        config["customCorners"] = {name: True for name in corner_names}
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config=config,
        kind="blob_47",
    )
    return result, images


@pytest.mark.parametrize("size", [(4, 4), (5, 5), (7, 4), (4, 7)])
def test_blob_47_full_sources_never_create_blended_rgba_pixels(
    size: tuple[int, int],
) -> None:
    result, images = _blob_build_with_rgba_sources(size, cutoff=1)

    for role in result.tiles:
        rendered = _crop_role(result, role.mask)
        for y in range(size[1]):
            for x in range(size[0]):
                candidates = {_visible(source.getpixel((x, y))) for source in images.values()}
                assert rendered.getpixel((x, y)) in candidates, (
                    f"blob mask={role.mask}, size={size}, coordinate={(x, y)} "
                    "contains an RGBA blend not present in any complete Source"
                )


@pytest.mark.parametrize("size", [(5, 5), (7, 4), (4, 7)])
def test_blob_transformed_coordinate_sources_do_not_interpolate(
    size: tuple[int, int],
) -> None:
    images = {
        name: _opaque_pattern(size, 80 + index) for index, name in enumerate(("base", *DIRECTIONS))
    }
    atlas, sources = _atlas(images)
    transforms = {
        "top": {"rotation": 0, "flipX": True},
        "right": {"rotation": 1, "flipY": True},
        "bottom": {"rotation": 2, "flipX": True, "flipY": True},
        "left": {"rotation": 3},
    }
    transformed = {
        direction: _transform(
            images[direction],
            size,
            rotation=int(transforms[direction].get("rotation", 0)),
            flip_x=bool(transforms[direction].get("flipX", False)),
            flip_y=bool(transforms[direction].get("flipY", False)),
        )
        for direction in DIRECTIONS
    }
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {direction: direction for direction in DIRECTIONS},
            "edgeTransforms": transforms,
            "cutoff": 1,
        },
        kind="blob_47",
    )

    for role in result.tiles:
        rendered = _crop_role(result, role.mask)
        for y in range(size[1]):
            for x in range(size[0]):
                candidates = {images["base"].getpixel((x, y))}
                candidates.update(image.getpixel((x, y)) for image in transformed.values())
                assert rendered.getpixel((x, y)) in candidates


def test_blob_mapping_order_rebuild_and_negative_cutoff_are_stable() -> None:
    size = (7, 5)
    images = {
        name: _opaque_pattern(size, 100 + index) for index, name in enumerate(("base", *DIRECTIONS))
    }
    atlas, sources = _atlas(images)

    def build(*, reverse: bool, cutoff: int) -> object:
        edge_items = [(direction, direction) for direction in DIRECTIONS]
        selected_sources = list(sources)
        if reverse:
            edge_items.reverse()
            selected_sources.reverse()
        return build_tilesetter_terrain_pattern(
            atlas,
            tile_size=size,
            sources=selected_sources,
            set_config={
                "baseSource": "base",
                "edges": dict(edge_items),
                "cutoff": cutoff,
            },
            kind="blob_47",
        )

    zero = build(reverse=False, cutoff=0)
    repeated = build(reverse=False, cutoff=0)
    reordered = build(reverse=True, cutoff=0)
    negative = build(reverse=False, cutoff=-3)
    positive = build(reverse=False, cutoff=2)
    positive_repeated = build(reverse=False, cutoff=2)

    assert zero.image.tobytes() == repeated.image.tobytes()
    assert zero.image.tobytes() == reordered.image.tobytes()
    assert zero.image.tobytes() == negative.image.tobytes()
    assert positive.image.tobytes() == positive_repeated.image.tobytes()


def _rotate_blob_mask_clockwise(mask: int) -> int:
    return sum((1 << ((bit + 2) % 8)) for bit in range(8) if mask & (1 << bit))


@pytest.mark.parametrize("size", [(6, 6), (5, 5)])
@pytest.mark.parametrize("cutoff", [0, 1])
def test_blob_auto_oriented_source_is_rotationally_covariant_for_all_47_roles(
    size: tuple[int, int],
    cutoff: int,
) -> None:
    base = Image.new("RGBA", size, (31, 61, 91, 137))
    edge = _pattern(size, 117, transparent=True)
    atlas, sources = _atlas({"base": base, "edge": edge})
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config={
            "baseSource": "base",
            "edges": {direction: "edge" for direction in DIRECTIONS},
            "autoOrientEdges": True,
            "cutoff": cutoff,
        },
        kind="blob_47",
    )

    available_masks = {role.mask for role in result.tiles}
    for mask in available_masks:
        rotated_mask = _rotate_blob_mask_clockwise(mask)
        assert rotated_mask in available_masks
        expected = _crop_role(result, mask).transpose(Image.Transpose.ROTATE_270)
        actual = _crop_role(result, rotated_mask)
        assert actual.tobytes() == expected.tobytes(), (
            f"Blob rotation covariance failed for mask={mask}, "
            f"rotated_mask={rotated_mask}, size={size}, cutoff={cutoff}"
        )


def _blob_corner_mask(corner: str, corner_type: str) -> int:
    direction_bits = {
        "top": 1,
        "right": 4,
        "bottom": 16,
        "left": 64,
    }
    if corner_type == "outer":
        return 0
    first, second = INCIDENT[corner]
    return direction_bits[first] | direction_bits[second]  # diagonal intentionally absent


@pytest.mark.parametrize("size", [(6, 4), (5, 5)])
def test_blob_all_custom_corners_replace_quadrants_including_transparent_pixels(
    size: tuple[int, int],
) -> None:
    result, images = _blob_build_with_rgba_sources(size, custom_corners=True, cutoff=0)

    for corner_type in ("outer", "inner"):
        for corner in CORNERS:
            key = f"{corner_type}_{corner}"
            rendered = _crop_role(result, _blob_corner_mask(corner, corner_type))
            x0, y0, x1, y1 = _quadrant(size, corner)
            for y in range(y0, y1):
                for x in range(x0, x1):
                    assert rendered.getpixel((x, y)) == _visible(images[key].getpixel((x, y))), (
                        key,
                        size,
                        (x, y),
                        rendered.getpixel((x, y)),
                        images[key].getpixel((x, y)),
                    )
