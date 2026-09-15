"""Regression coverage for seam-compatible organic Blob 47 variant banks."""

from __future__ import annotations

from collections import Counter

import numpy as np
import pytest
from PIL import Image

from sprite_builder.tilesets import (
    build_tilesetter_terrain_pattern,
    render_godot_terrain_installer,
    terrain_pattern_manifest,
)
from sprite_builder.tilesets.patterns import _organic_blob_coverage, _rounded_corner_coverage


def _blob_sources(size: int) -> tuple[Image.Image, list[dict[str, object]], dict[str, object]]:
    atlas = Image.new("RGBA", (size * 2, size), (72, 146, 65, 255))
    border = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    border.paste((112, 76, 48, 255), (0, 0, size, max(2, size // 4)))
    atlas.paste(border, (size, 0))
    sources: list[dict[str, object]] = [
        {"id": "base", "rect": [0, 0, size, size]},
        {"id": "border", "rect": [size, 0, size, size]},
    ]
    config: dict[str, object] = {
        "baseSource": "base",
        "autoOrientEdges": True,
        "edges": {direction: "border" for direction in ("top", "right", "bottom", "left")},
        "terrainProfile": "grass_over_dirt",
        "edgeVariation": 2,
        "edgeSeed": 314,
        "variantCount": 3,
    }
    return atlas, sources, config


def _tile_pixels(result: object, mask: int, variant: int) -> np.ndarray:
    role = next(
        role
        for role in result.tiles
        if role.mask == mask and role.variant == variant
    )
    left = role.column * result.tile_width
    top = role.row * result.tile_height
    return np.asarray(
        result.image.crop(
            (left, top, left + result.tile_width, top + result.tile_height)
        ),
        dtype=np.uint8,
    )


@pytest.mark.parametrize("profile", ["grass_over_dirt", "dirt_over_water", "grass_over_water"])
@pytest.mark.parametrize("size", [16, 32, 64, 128])
def test_procedural_blob_needs_no_sources_and_preserves_banks(profile: str, size: int) -> None:
    result = build_tilesetter_terrain_pattern(
        Image.new("RGBA", (1, 1)), tile_size=(size, size), sources=[],
        set_config={"blobMaterialMode": "procedural", "terrainProfile": profile,
                    "edgeVariation": 2, "variantCount": 3, "edgeSeed": 91},
        kind="blob_47",
    )
    assert result.complete and len(result.tiles) == 141
    for mask in {role.mask for role in result.tiles}:
        reference = _tile_pixels(result, mask, 0)
        for variant in (1, 2):
            pixels = _tile_pixels(result, mask, variant)
            for first, second in ((pixels[0], reference[0]), (pixels[-1], reference[-1]),
                                  (pixels[:, 0], reference[:, 0]),
                                  (pixels[:, -1], reference[:, -1])):
                assert np.array_equal(first, second), (size, profile, mask, variant)


def test_blob_builds_three_complete_canonical_variant_banks() -> None:
    atlas, sources, config = _blob_sources(16)
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )

    assert result.complete
    assert result.variant_count == 3
    assert len(result.tiles) == 141
    assert result.columns == 36
    assert result.rows == 4
    assert result.image.size == (576, 64)
    assert Counter(role.variant for role in result.tiles) == {0: 47, 1: 47, 2: 47}
    assert all(count == 3 for count in Counter(role.mask for role in result.tiles).values())
    assert all(role.probability == pytest.approx(1.0 / 3.0) for role in result.tiles)


def test_blob_variants_change_inside_but_keep_outer_ports_identical() -> None:
    atlas, sources, config = _blob_sources(16)
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )
    variants = [_tile_pixels(result, 28, variant) for variant in range(3)]

    assert any(not np.array_equal(variants[0], candidate) for candidate in variants[1:])
    for candidate in variants[1:]:
        assert np.array_equal(candidate[0, :], variants[0][0, :])
        assert np.array_equal(candidate[-1, :], variants[0][-1, :])
        assert np.array_equal(candidate[:, 0], variants[0][:, 0])
        assert np.array_equal(candidate[:, -1], variants[0][:, -1])


@pytest.mark.parametrize("size", [16, 32, 64, 128])
def test_organic_displacement_scales_and_locks_ports(size: int) -> None:
    yy, xx = np.indices((size, size))
    coverage = np.clip(0.5 + (xx - size / 2) / size, 0.0, 1.0).astype(np.float32)
    organic = _organic_blob_coverage(
        coverage,
        profile="dirt_over_water",
        variation=3,
        seed=91,
    )

    assert organic.shape == (size, size)
    assert np.array_equal(organic[0, :], coverage[0, :])
    assert np.array_equal(organic[-1, :], coverage[-1, :])
    assert np.array_equal(organic[:, 0], coverage[:, 0])
    assert np.array_equal(organic[:, -1], coverage[:, -1])
    assert not np.array_equal(organic[1:-1, 1:-1], coverage[1:-1, 1:-1])


def test_blob_exposed_side_gets_a_continuous_organic_contour() -> None:
    canonical = _rounded_corner_coverage(124, 16, 16, radius=4, kind="blob_47")
    organic = _organic_blob_coverage(
        canonical,
        profile="grass_over_water",
        variation=2,
        seed=314,
        exposed_directions=("top",),
    )

    first_owned_pixel = np.argmax(organic >= 0.5, axis=0)
    assert int(np.ptp(first_owned_pixel)) >= 1
    assert np.array_equal(organic[0, :], canonical[0, :])
    assert np.array_equal(organic[-1, :], canonical[-1, :])
    assert np.array_equal(organic[:, 0], canonical[:, 0])
    assert np.array_equal(organic[:, -1], canonical[:, -1])


def test_blob_native_outer_corner_is_curved_instead_of_a_source_rectangle() -> None:
    atlas, sources, config = _blob_sources(16)
    config.update({"terrainProfile": "organic_neutral", "edgeVariation": 3})
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )
    pixels = _tile_pixels(result, 28, 0)
    # Mask 28 exposes the top-left outer corner. The base sample is green and
    # the propagated outside sample is brown; the first base pixel therefore
    # traces the procedural arc across each row.
    base = (pixels[..., 1] > pixels[..., 0]) & (pixels[..., 1] > pixels[..., 2])
    corner = base[:8, :8]
    row_widths = np.count_nonzero(corner, axis=1)
    column_heights = np.count_nonzero(corner, axis=0)
    assert int(np.count_nonzero(np.diff(row_widths))) >= 2
    assert int(np.count_nonzero(np.diff(column_heights))) >= 2
    assert np.all(~base[0, :])
    assert np.all(~base[:, 0])


@pytest.mark.parametrize(
    ("mask", "corner_slice", "corner"),
    [
        (28, (slice(0, 8), slice(0, 8)), (0, 0)),
        (112, (slice(0, 8), slice(8, 16)), (0, 15)),
        (193, (slice(8, 16), slice(8, 16)), (15, 15)),
        (7, (slice(8, 16), slice(0, 8)), (15, 0)),
    ],
)
def test_blob_rounds_all_four_outer_corner_quadrants(
    mask: int,
    corner_slice: tuple[slice, slice],
    corner: tuple[int, int],
) -> None:
    coverage = _rounded_corner_coverage(mask, 16, 16, radius=5, kind="blob_47")
    owned = coverage >= 0.5
    quadrant = owned[corner_slice]

    # The contour must leave the exposed vertex empty while reaching the
    # shared midpoint, with a partial arc rather than an 8x8 source block.
    assert not owned[corner]
    assert owned[8, 8]
    assert 0 < int(np.count_nonzero(quadrant)) < quadrant.size


def test_blob_four_inner_corner_warps_keep_the_center_connected() -> None:
    canonical = _rounded_corner_coverage(85, 16, 16, radius=5, kind="blob_47")
    organic = _organic_blob_coverage(
        canonical,
        profile="organic_neutral",
        variation=3,
        seed=314,
        exposed_directions=(),
        mask=85,
    )
    owned = organic >= 0.5
    pending = [(8, 8)]
    visited = np.zeros_like(owned, dtype=bool)
    while pending:
        x, y = pending.pop()
        if visited[y, x] or not owned[y, x]:
            continue
        visited[y, x] = True
        for next_x, next_y in (
            (x + 1, y),
            (x - 1, y),
            (x, y + 1),
            (x, y - 1),
        ):
            if 0 <= next_x < 16 and 0 <= next_y < 16:
                pending.append((next_x, next_y))

    assert np.array_equal(visited, owned)
    assert not np.array_equal(organic[1:-1, 1:-1], canonical[1:-1, 1:-1])


@pytest.mark.parametrize(
    "profile",
    ["grass_over_dirt", "dirt_over_water", "grass_over_water"],
)
def test_blob_material_profiles_add_authorized_procedural_shades(profile: str) -> None:
    atlas, sources, config = _blob_sources(16)
    config.update({"terrainProfile": profile, "edgeVariation": 3})
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )
    styled = _tile_pixels(result, 28, 0)
    organic_config = {**config, "terrainProfile": "organic_neutral"}
    organic = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=organic_config,
        kind="blob_47",
    )
    neutral = _tile_pixels(organic, 28, 0)
    assert not np.array_equal(styled, neutral)
    # User-authorized procedural shading adds discrete tonal levels.
    source_palette = {(72, 146, 65, 255), (112, 76, 48, 255)}
    changed = [
        tuple(pixel)
        for pixel in styled.reshape(-1, 4)
        if tuple(pixel) not in source_palette
    ]
    assert len(changed) >= 3
    assert np.all(styled[..., 3] == 255)


def test_blob_variant_manifest_and_godot_probabilities() -> None:
    atlas, sources, config = _blob_sources(16)
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )
    manifest = terrain_pattern_manifest(result)
    installer = render_godot_terrain_installer(result)

    assert manifest["schema_version"] == "1.1"
    assert manifest["edge_profile"]["variant_count"] == 3
    assert manifest["edge_profile"]["variants_are_seam_compatible"] is True
    assert {tile["variant"] for tile in manifest["tiles"]} == {0, 1, 2}
    assert 'tile_data.probability = entry["probability"]' in installer
    assert installer.count('"probability": 0.33333333') == 141


def test_blob_builds_five_complete_canonical_variant_banks() -> None:
    atlas, sources, config = _blob_sources(16)
    config["variantCount"] = 5
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=config,
        kind="blob_47",
    )

    assert result.complete
    assert result.variant_count == 5
    assert len(result.tiles) == 235
    assert result.columns == 60
    assert result.rows == 4
    assert result.image.size == (960, 64)
    assert Counter(role.variant for role in result.tiles) == {0: 47, 1: 47, 2: 47, 3: 47, 4: 47}
    assert all(count == 5 for count in Counter(role.mask for role in result.tiles).values())
    assert all(role.probability == pytest.approx(1.0 / 5.0) for role in result.tiles)


def test_blob_rejects_more_than_five_variants() -> None:
    atlas, sources, config = _blob_sources(16)
    config["variantCount"] = 6
    with pytest.raises(ValueError, match="Blob variant count"):
        build_tilesetter_terrain_pattern(
            atlas,
            tile_size=(16, 16),
            sources=sources,
            set_config=config,
            kind="blob_47",
        )



@pytest.mark.parametrize("size", [16, 32, 64, 128])
def test_all_native_banks_have_connected_terrain_and_no_pinholes(size: int) -> None:
    import cv2

    atlas, sources, config = _blob_sources(size)
    config.update(terrainProfile="organic_neutral", edgeVariation=3)
    for seed in (0, 91, 314):
        config["edgeSeed"] = seed
        result = build_tilesetter_terrain_pattern(
            atlas, tile_size=(size, size), sources=sources,
            set_config=config, kind="blob_47",
        )
        assert result.complete and len(result.tiles) == 141
        for role in result.tiles:
            pixels = _tile_pixels(result, role.mask, role.variant)
            owned = (pixels[..., 1] > pixels[..., 0]).astype(np.uint8)
            count, labels, stats, _ = cv2.connectedComponentsWithStats(owned, connectivity=4)
            assert count == (1 if role.mask == 0 else 2), (size, seed, role.mask)
            if role.mask:
                assert stats[1, cv2.CC_STAT_AREA] > 2
            count, labels, stats, _ = cv2.connectedComponentsWithStats(1-owned, connectivity=4)
            boundary = set(labels[0]) | set(labels[-1]) | set(labels[:, 0]) | set(labels[:, -1])
            for component in range(1, count):
                assert component in boundary, (size, seed, role.mask, "pinhole")
                assert stats[component, cv2.CC_STAT_AREA] > 2
            reference = _tile_pixels(result, role.mask, 0)
            for a, b in ((pixels[0], reference[0]), (pixels[-1], reference[-1]),
                         (pixels[:, 0], reference[:, 0]), (pixels[:, -1], reference[:, -1])):
                assert np.array_equal(a, b)


def test_compatible_ports_match_across_masks_seeds_and_variants() -> None:
    from sprite_builder.tilesets.patterns import _blob_bitmap_coverage

    atlas, sources, config = _blob_sources(16)
    ports: dict[tuple[int, bytes], bytes] = {}
    for seed in (0, 91, 314):
        config.update(edgeSeed=seed, edgeVariation=3)
        result = build_tilesetter_terrain_pattern(
            atlas, tile_size=(16, 16), sources=sources,
            set_config=config, kind="blob_47",
        )
        for role in result.tiles:
            pixels = _tile_pixels(result, role.mask, role.variant)
            canonical = _blob_bitmap_coverage(role.mask, 16, 16) >= 0.5
            for axis, (edge, signature) in enumerate(zip(
                (pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]),
                (canonical[0], canonical[-1], canonical[:, 0], canonical[:, -1]), strict=True,
            )):
                key = (axis, signature.tobytes())
                assert ports.setdefault(key, edge.tobytes()) == edge.tobytes()


def test_material_contact_tracks_contour_and_clusters_are_whole() -> None:
    import cv2

    from sprite_builder.tilesets.patterns import _blob_material_layers, _pixel_distance_to_mask

    yy, xx = np.indices((32, 32))
    owned = (xx - 16) ** 2 + (yy - 16) ** 2 <= 100
    source = np.where(owned[..., None], [72, 146, 65, 255], [112, 76, 48, 255]).astype(
        np.uint8
    )
    result = _blob_material_layers(source, owned, profile="grass_over_dirt", seed=314)
    distance = _pixel_distance_to_mask(owned)
    contact = ~owned & (distance == 1)
    expected = np.rint(source[contact, :3].astype(float) * 0.70).astype(np.uint8)
    assert np.array_equal(result[contact, :3], expected)
    assert np.array_equal(result[..., 3], source[..., 3])
    marks = owned & np.any(result != source, axis=2)
    count, _, stats, _ = cv2.connectedComponentsWithStats(marks.astype(np.uint8), connectivity=4)
    assert count > 1
    assert all(stats[i, cv2.CC_STAT_AREA] >= 3 for i in range(1, count))
    for a, b in ((result[0], source[0]), (result[-1], source[-1]),
                 (result[:, 0], source[:, 0]), (result[:, -1], source[:, -1])):
        assert np.array_equal(a, b)


@pytest.mark.parametrize("profile", ["grass_over_dirt", "dirt_over_water", "grass_over_water"])
def test_material_profiles_keep_all_native_topologies(profile: str) -> None:
    import cv2

    atlas, sources, config = _blob_sources(16)
    config.update(terrainProfile=profile, edgeVariation=3)
    for seed in (0, 91, 314):
        config["edgeSeed"] = seed
        result = build_tilesetter_terrain_pattern(
            atlas, tile_size=(16, 16), sources=sources, set_config=config, kind="blob_47",
        )
        for role in result.tiles:
            pixels = _tile_pixels(result, role.mask, role.variant)
            owned = (pixels[..., 1] > pixels[..., 0]).astype(np.uint8)
            count, _, stats, _ = cv2.connectedComponentsWithStats(owned, connectivity=4)
            assert count == (1 if role.mask == 0 else 2), (profile, seed, role.mask)
            count, labels, stats, _ = cv2.connectedComponentsWithStats(1-owned, connectivity=4)
            border = set(labels[0]) | set(labels[-1]) | set(labels[:, 0]) | set(labels[:, -1])
            for component in range(1, count):
                assert component in border and stats[component, cv2.CC_STAT_AREA] > 2
