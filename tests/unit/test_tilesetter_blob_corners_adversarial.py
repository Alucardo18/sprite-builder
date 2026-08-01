"""Independent adversarial checks for TileSetter-style Blob composition.

The fixtures deliberately encode the source id and pixel coordinate in every
pixel.  Solid-color samples can show that both borders appear, but cannot show
that a compositor mirrored, shifted, or stretched one of them at a seam.
"""

from __future__ import annotations

from collections.abc import Mapping

from PIL import Image

from sprite_builder.tilesets.patterns import (
    _tilesetter_blob_neighbor_matrix,
    build_tilesetter_terrain_pattern,
    terrain_pattern_masks,
)

_DIRECTIONS = (
    "top",
    "top_right",
    "right",
    "bottom_right",
    "bottom",
    "bottom_left",
    "left",
    "top_left",
)
_BITS = {direction: 1 << index for index, direction in enumerate(_DIRECTIONS)}
_CARDINALS = ("top", "right", "bottom", "left")
_SOURCE_TAG = {"base": 17, "top": 41, "right": 73, "bottom": 109, "left": 149}


def _coordinate_sample(
    size: int,
    tag: int,
    *,
    alpha: int = 255,
    alpha_band: int | None = None,
) -> Image.Image:
    sample = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rows = size if alpha_band is None else alpha_band
    for y in range(rows):
        for x in range(size):
            sample.putpixel((x, y), (tag, x, y, alpha))
    return sample


def _build_blob(
    size: int = 7,
    *,
    canonical_edge: bool = False,
    edge_transforms: Mapping[str, Mapping[str, object]] | None = None,
    custom: Image.Image | None = None,
    custom_key: str = "outer_top_left",
    symmetric_base: bool = False,
    edge_alpha: int = 255,
):
    images: dict[str, Image.Image] = {
        "base": (
            Image.new("RGBA", (size, size), (_SOURCE_TAG["base"],) * 3 + (255,))
            if symmetric_base
            else _coordinate_sample(size, _SOURCE_TAG["base"])
        ),
    }
    if canonical_edge:
        images["edge"] = _coordinate_sample(size, _SOURCE_TAG["top"], alpha=edge_alpha)
        edges = dict.fromkeys(_CARDINALS, "edge")
    else:
        images.update(
            {
                direction: _coordinate_sample(
                    size,
                    _SOURCE_TAG[direction],
                    alpha=edge_alpha,
                )
                for direction in _CARDINALS
            }
        )
        edges = {direction: direction for direction in _CARDINALS}
    if custom is not None:
        images["custom"] = custom

    atlas = Image.new("RGBA", (size * len(images), size), (0, 0, 0, 0))
    sources: list[dict[str, object]] = []
    for index, (source_id, image) in enumerate(images.items()):
        atlas.paste(image, (index * size, 0))
        sources.append(
            {
                "id": source_id,
                "x": index * size,
                "y": 0,
                "width": size,
                "height": size,
            }
        )

    config: dict[str, object] = {
        "baseSource": "base",
        "autoOrientEdges": canonical_edge,
        "edges": edges,
        "edgeTransforms": dict(edge_transforms or {}),
        "cutoff": 0,
    }
    if custom is not None:
        config["corners"] = {custom_key: "custom"}
        config["customCorners"] = {custom_key: True}
    return build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(size, size),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )


def _role_image(result, mask: int) -> Image.Image:
    role = next(role for role in result.tiles if role.mask == mask)
    x = role.column * result.tile_width
    y = role.row * result.tile_height
    return result.image.crop((x, y, x + result.tile_width, y + result.tile_height))


def _rotate_mask_clockwise(mask: int) -> int:
    return sum(1 << ((index + 2) % 8) for index in range(8) if mask & (1 << index))


def _diagonal_state(
    mask: int,
    cardinals: Mapping[str, bool],
    name: str,
    first: str,
    second: str,
) -> bool | None:
    if not cardinals[first] or not cardinals[second]:
        return None
    return bool(mask & _BITS[name])


def test_all_47_blob_masks_have_an_independent_three_state_diagonal_matrix() -> None:
    masks = terrain_pattern_masks("blob_47")

    assert len(masks) == 47
    for mask in masks:
        actual = _tilesetter_blob_neighbor_matrix(mask)
        cardinals = {direction: bool(mask & _BITS[direction]) for direction in _CARDINALS}

        expected = (
            _diagonal_state(mask, cardinals, "top_left", "top", "left"),
            cardinals["top"],
            _diagonal_state(mask, cardinals, "top_right", "top", "right"),
            cardinals["right"],
            _diagonal_state(mask, cardinals, "bottom_right", "bottom", "right"),
            cardinals["bottom"],
            _diagonal_state(mask, cardinals, "bottom_left", "bottom", "left"),
            cardinals["left"],
        )

        assert actual == expected, f"mask {mask} lost its null diagonal state"


def test_all_47_roles_copy_unshifted_pixels_only_from_semantically_needed_sources() -> None:
    result = _build_blob(7)
    corner_rules = (
        ("top_left", "top", "left"),
        ("top_right", "top", "right"),
        ("bottom_right", "bottom", "right"),
        ("bottom_left", "bottom", "left"),
    )

    assert result.complete
    for role in result.tiles:
        neighbors = set(role.neighbors)
        needed = {direction for direction in _CARDINALS if direction not in neighbors}
        for diagonal, first, second in corner_rules:
            if first in neighbors and second in neighbors and diagonal not in neighbors:
                needed.update((first, second))
        allowed_tags = {_SOURCE_TAG["base"], *(_SOURCE_TAG[item] for item in needed)}
        rendered = _role_image(result, role.mask)
        used_tags: set[int] = set()
        for y in range(rendered.height):
            for x in range(rendered.width):
                pixel = rendered.getpixel((x, y))
                assert pixel[3] == 255, f"mask {role.mask} left a hole at {(x, y)}"
                assert pixel[0] in allowed_tags, f"mask {role.mask} used an unrelated Source"
                assert pixel[1:3] == (x, y), f"mask {role.mask} shifted a Source at {(x, y)}"
                used_tags.add(pixel[0])
        assert {_SOURCE_TAG[item] for item in needed} <= used_tags


def test_all_47_roles_copy_semitransparent_rgba_without_blending_sources() -> None:
    size = 7
    edge_alpha = 93
    result = _build_blob(size, edge_alpha=edge_alpha)

    for role in result.tiles:
        rendered = _role_image(result, role.mask)
        for y in range(size):
            for x in range(size):
                pixel = rendered.getpixel((x, y))
                authored = {
                    (_SOURCE_TAG["base"], x, y, 255),
                    *((_SOURCE_TAG[direction], x, y, edge_alpha) for direction in _CARDINALS),
                }
                assert pixel in authored, f"mask {role.mask} synthesized RGBA {pixel} at {(x, y)}"


def test_adjacent_opposite_three_and_four_side_regions_meet_at_geometric_midpoints() -> None:
    size = 7
    result = _build_blob(size)
    cases = {
        28: ("top", "left"),
        68: ("top", "bottom"),
        16: ("top", "right", "left"),
        0: ("top", "right", "bottom", "left"),
    }
    distance = {
        "top": lambda x, y: y,
        "right": lambda x, y: size - 1 - x,
        "bottom": lambda x, y: size - 1 - y,
        "left": lambda x, y: x,
    }

    for mask, exposed in cases.items():
        rendered = _role_image(result, mask)
        for y in range(size):
            for x in range(size):
                scores = {direction: distance[direction](x, y) for direction in exposed}
                minimum = min(scores.values())
                winners = [direction for direction, value in scores.items() if value == minimum]
                if len(winners) == 1:
                    assert rendered.getpixel((x, y))[0] == _SOURCE_TAG[winners[0]], (
                        f"mask {mask} assigned {(x, y)} to the wrong overlap region"
                    )

    opposite = _role_image(result, 68)
    midpoint = size // 2
    assert all(opposite.getpixel((x, midpoint - 1))[0] == _SOURCE_TAG["top"] for x in range(size))
    assert all(opposite.getpixel((x, midpoint))[0] == _SOURCE_TAG["bottom"] for x in range(size))


def test_all_automatic_outer_and_inner_corners_are_spliced_from_two_incident_edges() -> None:
    size = 7
    result = _build_blob(size)
    near = size // 2
    far = (size + 1) // 2
    cases = (
        (0, (0, 0, near, near), ("top", "left")),
        (0, (far, 0, size, near), ("top", "right")),
        (0, (far, far, size, size), ("right", "bottom")),
        (0, (0, far, near, size), ("bottom", "left")),
        (65, (0, 0, near, near), ("top", "left")),
        (5, (far, 0, size, near), ("top", "right")),
        (20, (far, far, size, size), ("right", "bottom")),
        (80, (0, far, near, size), ("bottom", "left")),
    )

    for mask, bounds, incident in cases:
        tags = {pixel[0] for pixel in _role_image(result, mask).crop(bounds).get_flattened_data()}
        assert tags == {_SOURCE_TAG[item] for item in incident}, (mask, bounds, tags)


def test_auto_orientation_and_user_flip_transform_complete_odd_sized_sources_exactly() -> None:
    size = 5
    transforms = {direction: {"flipX": True} for direction in _CARDINALS}
    result = _build_blob(size, canonical_edge=True, edge_transforms=transforms)
    canonical = _coordinate_sample(size, _SOURCE_TAG["top"])
    flipped = canonical.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    single_exposed_masks = {"top": 124, "right": 241, "bottom": 199, "left": 31}

    for turns, direction in enumerate(_CARDINALS):
        expected = (
            flipped,
            flipped.transpose(Image.Transpose.ROTATE_270),
            flipped.transpose(Image.Transpose.ROTATE_180),
            flipped.transpose(Image.Transpose.ROTATE_90),
        )[turns]
        assert _role_image(result, single_exposed_masks[direction]).tobytes() == expected.tobytes()


def test_odd_sized_automatic_splices_rotate_exactly_for_all_47_roles() -> None:
    result = _build_blob(5, canonical_edge=True, symmetric_base=True)
    mismatches: list[tuple[int, int]] = []

    for mask in terrain_pattern_masks("blob_47"):
        rotated_mask = _rotate_mask_clockwise(mask)
        expected = _role_image(result, mask).transpose(Image.Transpose.ROTATE_270)
        if _role_image(result, rotated_mask).tobytes() != expected.tobytes():
            mismatches.append((mask, rotated_mask))

    assert not mismatches, f"90-degree rotation changed automatic seams: {mismatches}"


def test_blob_custom_corner_replaces_quadrant_including_transparent_pixels() -> None:
    size = 5
    custom = _coordinate_sample(size, 223)
    custom.putpixel((0, 0), (0, 0, 0, 0))
    result = _build_blob(size, custom=custom)
    rendered = _role_image(result, 0)
    quadrant = (0, 0, size // 2, size // 2)

    assert rendered.crop(quadrant).tobytes() == custom.crop(quadrant).tobytes()
