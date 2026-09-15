"""Unit tests for 1-tile and 2-tile Blob 47 smart synthesis with shadows and lighting."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from sprite_builder.tilesets import (
    build_tilesetter_terrain_pattern,
    render_godot_terrain_installer,
    terrain_pattern_manifest,
)


def _make_test_atlas(size: int = 16) -> tuple[Image.Image, list[dict[str, object]]]:
    # Tile A: Vibrant green grass (100, 200, 80)
    # Tile B: Warm brown dirt (160, 110, 60)
    atlas = Image.new("RGBA", (size * 2, size), (0, 0, 0, 0))
    tile_a = Image.new("RGBA", (size, size), (100, 200, 80, 255))
    tile_b = Image.new("RGBA", (size, size), (160, 110, 60, 255))
    atlas.paste(tile_a, (0, 0))
    atlas.paste(tile_b, (size, 0))
    sources: list[dict[str, object]] = [
        {"id": "tile_a", "name": "Grass", "rect": [0, 0, size, size]},
        {"id": "tile_b", "name": "Dirt", "rect": [size, 0, size, size]},
    ]
    return atlas, sources


def test_blob_synthesis_single_tile_transparent_background() -> None:
    size = 16
    atlas, sources = _make_test_atlas(size)
    set_config = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": None,
        "terrainProfile": "clean",
        "cornerRadius": 3,
        "dropShadow": 0,
        "rimLight": False,
    }
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(size, size),
        sources=sources,
        set_config=set_config,
        kind="blob_47",
    )

    assert result.complete
    assert len(result.tiles) == 47
    assert result.blob_mode == "synthesis"

    # Mask 255 (solid center) should be solid Tile A
    tile_255 = next(r for r in result.tiles if r.mask == 255)
    img_255 = result.image.crop(
        (tile_255.column * size, tile_255.row * size, (tile_255.column + 1) * size, (tile_255.row + 1) * size)
    )
    arr_255 = np.asarray(img_255)
    assert np.all(arr_255[..., 3] == 255)
    assert np.all(arr_255[..., 0] == 100)
    assert np.all(arr_255[..., 1] == 200)

    # Mask 0 (empty) should be transparent
    tile_0 = next(r for r in result.tiles if r.mask == 0)
    img_0 = result.image.crop(
        (tile_0.column * size, tile_0.row * size, (tile_0.column + 1) * size, (tile_0.row + 1) * size)
    )
    arr_0 = np.asarray(img_0)
    assert np.all(arr_0[..., 3] == 0)

    # Mask 1 (top connected, bottom open): top half is Tile A, bottom half is transparent
    tile_1 = next(r for r in result.tiles if r.mask == 1)
    img_1 = result.image.crop(
        (tile_1.column * size, tile_1.row * size, (tile_1.column + 1) * size, (tile_1.row + 1) * size)
    )
    arr_1 = np.asarray(img_1)
    # Top row (inside) is opaque
    assert arr_1[0, size // 2, 3] == 255
    # Bottom row (outside) is transparent
    assert arr_1[size - 1, size // 2, 3] == 0


def test_blob_synthesis_two_tiles_blends_a_and_b() -> None:
    size = 16
    atlas, sources = _make_test_atlas(size)
    set_config = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "terrainProfile": "clean",
        "cornerRadius": 2,
        "dropShadow": 0,
        "rimLight": False,
    }
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(size, size),
        sources=sources,
        set_config=set_config,
        kind="blob_47",
    )

    assert result.complete
    assert len(result.tiles) == 47

    # Mask 0 (empty/background) should be solid Tile B (Dirt)
    tile_0 = next(r for r in result.tiles if r.mask == 0)
    img_0 = result.image.crop(
        (tile_0.column * size, tile_0.row * size, (tile_0.column + 1) * size, (tile_0.row + 1) * size)
    )
    arr_0 = np.asarray(img_0)
    assert np.all(arr_0[..., 3] == 255)
    assert np.all(arr_0[..., 0] == 160)
    assert np.all(arr_0[..., 1] == 110)

    # Mask 1: Top is Grass (Tile A), Bottom is Dirt (Tile B)
    tile_1 = next(r for r in result.tiles if r.mask == 1)
    img_1 = result.image.crop(
        (tile_1.column * size, tile_1.row * size, (tile_1.column + 1) * size, (tile_1.row + 1) * size)
    )
    arr_1 = np.asarray(img_1)
    # Top center is Tile A
    assert tuple(arr_1[0, size // 2, :3]) == (100, 200, 80)
    # Bottom center is Tile B
    assert tuple(arr_1[size - 1, size // 2, :3]) == (160, 110, 60)


def test_blob_synthesis_drop_shadow_darkens_background() -> None:
    size = 16
    atlas, sources = _make_test_atlas(size)
    # Without shadow
    no_shadow_config = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "terrainProfile": "clean",
        "dropShadow": 0,
        "rimLight": False,
    }
    res_no_shadow = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=no_shadow_config, kind="blob_47"
    )

    # With south shadow of 2px
    shadow_config = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "terrainProfile": "clean",
        "dropShadow": 2,
        "shadowDirection": "south",
        "rimLight": False,
    }
    res_shadow = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=shadow_config, kind="blob_47"
    )

    # For mask 1 (top is A, bottom is B):
    # Shadow falls on row 12 directly below the transition onto B
    t1_no = next(r for r in res_no_shadow.tiles if r.mask == 1)
    t1_sh = next(r for r in res_shadow.tiles if r.mask == 1)

    crop_no = np.asarray(res_no_shadow.image.crop(
        (t1_no.column * size, t1_no.row * size, (t1_no.column + 1) * size, (t1_no.row + 1) * size)
    ))
    crop_sh = np.asarray(res_shadow.image.crop(
        (t1_sh.column * size, t1_sh.row * size, (t1_sh.column + 1) * size, (t1_sh.row + 1) * size)
    ))

    unshaded_color = crop_no[12, size // 2, :3]
    shaded_color = crop_sh[12, size // 2, :3]

    assert shaded_color[0] < unshaded_color[0]
    assert shaded_color[1] < unshaded_color[1]


def test_blob_synthesis_rim_light_brightens_top_edge() -> None:
    size = 16
    atlas, sources = _make_test_atlas(size)
    no_rim_config = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "terrainProfile": "clean",
        "dropShadow": 0,
        "rimLight": False,
    }
    res_no_rim = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=no_rim_config, kind="blob_47"
    )

    rim_config = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "terrainProfile": "clean",
        "dropShadow": 0,
        "rimLight": True,
    }
    res_rim = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=rim_config, kind="blob_47"
    )

    # For mask 16 (bottom is A, top is B):
    # The top crest of Terreno A is at row 4
    t16_no = next(r for r in res_no_rim.tiles if r.mask == 16)
    t16_rim = next(r for r in res_rim.tiles if r.mask == 16)

    crop_no = np.asarray(res_no_rim.image.crop(
        (t16_no.column * size, t16_no.row * size, (t16_no.column + 1) * size, (t16_no.row + 1) * size)
    ))
    crop_rim = np.asarray(res_rim.image.crop(
        (t16_rim.column * size, t16_rim.row * size, (t16_rim.column + 1) * size, (t16_rim.row + 1) * size)
    ))

    unlit_color = crop_no[4, size // 2, :3]
    lit_color = crop_rim[4, size // 2, :3]

    assert lit_color[0] > unlit_color[0]
    assert lit_color[1] > unlit_color[1]


def test_blob_synthesis_with_three_variant_banks() -> None:
    size = 16
    atlas, sources = _make_test_atlas(size)
    set_config = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "terrainProfile": "grass_over_dirt",
        "edgeVariation": 2,
        "variantCount": 3,
    }
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(size, size),
        sources=sources,
        set_config=set_config,
        kind="blob_47",
    )

    assert result.complete
    assert result.variant_count == 3
    assert len(result.tiles) == 47 * 3  # 141 tiles


def test_blob_synthesis_godot_export() -> None:
    size = 16
    atlas, sources = _make_test_atlas(size)
    set_config = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "dropShadow": 2,
        "rimLight": True,
    }
    result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(size, size),
        sources=sources,
        set_config=set_config,
        kind="blob_47",
    )

    installer = render_godot_terrain_installer(result, terrain_name="Meadow")
    manifest = terrain_pattern_manifest(result)

    assert "TileSet.TERRAIN_MODE_MATCH_CORNERS_AND_SIDES" in installer
    assert manifest["pattern"] == "blob_47"
    assert result.complete is True
    assert len(manifest["tiles"]) == 47


def test_blob_synthesis_studio_component_and_bridge_integration(monkeypatch) -> None:
    from pathlib import Path
    from sprite_builder.ui import components

    studio_html = Path(components.__file__).parent / "terrain_pattern_studio_component" / "index.html"
    source = studio_html.read_text(encoding="utf-8")

    # Studio controls exist
    assert 'id="blobSynthesisSection"' in source
    assert 'id="blobSynthesisMode"' in source
    assert 'id="blobDropShadow"' in source
    assert 'id="blobShadowDirection"' in source
    assert 'id="blobRimLight"' in source
    assert 'id="buildBlobTwoTiles"' in source
    assert "isBlobSynthesis" in source

    # Component bridge roundtrip
    captured: dict[str, Any] = {}

    def fake_component(**kwargs: Any) -> None:
        captured.update(kwargs)
        return None

    project = {
        "version": 3,
        "sources": [
            {"id": "source-grass", "x": 0, "y": 0, "width": 16, "height": 16},
            {"id": "source-dirt", "x": 16, "y": 0, "width": 16, "height": 16},
        ],
        "tiles": [
            {"id": "tile-1", "sourceId": "source-grass", "x": 0, "y": 0},
            {"id": "tile-2", "sourceId": "source-dirt", "x": 1, "y": 0},
        ],
        "sets": [
            {
                "id": "blob-synth",
                "kind": "blob_47",
                "blobMode": "synthesis",
                "baseSource": "source-grass",
                "secondarySource": "source-dirt",
                "dropShadow": 3,
                "shadowDirection": "south_east",
                "rimLight": True,
                "variantCount": 3,
            }
        ],
        "activeSetId": "blob-synth",
    }
    monkeypatch.setattr(components, "_TERRAIN_PATTERN_STUDIO", fake_component)

    components.terrain_pattern_studio(
        Image.new("RGBA", (32, 16)),
        pattern_image=Image.new("RGBA", (176, 80)),
        image_token="synth-test",
        tile_size=(16, 16),
        kind="blob_47",
        roles=[],
        project=project,
        key="test-synth-key",
    )

    set_cfg = captured["project"]["sets"][0]
    assert set_cfg["blobMode"] == "synthesis"
    assert set_cfg["dropShadow"] == 3
    assert set_cfg["shadowDirection"] == "south_east"
    assert set_cfg["rimLight"] is True
    assert set_cfg["secondarySource"] == "source-dirt"


def test_blob_synthesis_shadow_tint_and_intensity() -> None:
    size = 16
    atlas, sources = _make_test_atlas(size)

    # Base configuration with identical base & secondary
    def make_config(tint: str, intensity: float) -> dict[str, Any]:
        return {
            "blobMode": "synthesis",
            "baseSource": "tile_a",
            "secondarySource": "tile_b",
            "terrainProfile": "clean",
            "dropShadow": 2,
            "shadowDirection": "south",
            "shadowTint": tint,
            "shadowIntensity": intensity,
            "rimLight": False,
        }

    res_cool = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=make_config("cool", 0.70), kind="blob_47"
    )
    res_warm = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=make_config("warm", 0.70), kind="blob_47"
    )
    res_low = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=make_config("cool", 0.25), kind="blob_47"
    )
    res_high = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=make_config("cool", 0.95), kind="blob_47"
    )

    assert res_cool.shadow_tint == "cool"
    assert res_warm.shadow_tint == "warm"
    assert res_cool.shadow_intensity == 0.70

    # Inspect shadow pixel on row 12 for mask 1 (south drop shadow)
    t1_cool = next(r for r in res_cool.tiles if r.mask == 1)
    t1_warm = next(r for r in res_warm.tiles if r.mask == 1)
    t1_low = next(r for r in res_low.tiles if r.mask == 1)
    t1_high = next(r for r in res_high.tiles if r.mask == 1)

    crop_cool = np.asarray(res_cool.image.crop(
        (t1_cool.column * size, t1_cool.row * size, (t1_cool.column + 1) * size, (t1_cool.row + 1) * size)
    ))
    crop_warm = np.asarray(res_warm.image.crop(
        (t1_warm.column * size, t1_warm.row * size, (t1_warm.column + 1) * size, (t1_warm.row + 1) * size)
    ))
    crop_low = np.asarray(res_low.image.crop(
        (t1_low.column * size, t1_low.row * size, (t1_low.column + 1) * size, (t1_low.row + 1) * size)
    ))
    crop_high = np.asarray(res_high.image.crop(
        (t1_high.column * size, t1_high.row * size, (t1_high.column + 1) * size, (t1_high.row + 1) * size)
    ))

    # In warm shadow, red channel is boosted and blue is suppressed compared to cool
    pixel_cool = crop_cool[12, size // 2, :3].astype(float)
    pixel_warm = crop_warm[12, size // 2, :3].astype(float)
    assert pixel_warm[0] > pixel_cool[0]  # Warm Red > Cool Red
    assert pixel_cool[2] > pixel_warm[2]  # Cool Blue > Warm Blue

    # In high intensity shadow, pixels are darker than low intensity
    pixel_low = crop_low[12, size // 2, :3].astype(float)
    pixel_high = crop_high[12, size // 2, :3].astype(float)
    assert np.mean(pixel_high) < np.mean(pixel_low)


def test_blob_synthesis_chamfer_corner_style() -> None:
    size = 16
    atlas, sources = _make_test_atlas(size)

    config_chamfer = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "terrainProfile": "rounded_chamfer",
        "cornerStyle": "chamfer",
        "cornerRadius": 4,
        "edgeVariation": 0,
        "dropShadow": 0,
        "rimLight": False,
    }
    result_chamfer = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=config_chamfer, kind="blob_47"
    )

    config_arc = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "terrainProfile": "rounded_clean",
        "cornerStyle": "arc",
        "cornerRadius": 4,
        "edgeVariation": 0,
        "dropShadow": 0,
        "rimLight": False,
    }
    result_arc = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=config_arc, kind="blob_47"
    )

    assert result_chamfer.corner_style == "chamfer"
    assert result_chamfer.terrain_profile == "rounded_chamfer"
    assert result_arc.corner_style == "arc"

    # Verify chamfer produces distinct diagonal planar cut compared to radial arc
    # Check across canonical blob tiles with corners
    diff_found = False
    for t_ch, t_ar in zip(result_chamfer.tiles, result_arc.tiles):
        if t_ch.mask in (0, 0xFF):
            continue
        c_ch = np.asarray(result_chamfer.image.crop(
            (t_ch.column * size, t_ch.row * size, (t_ch.column + 1) * size, (t_ch.row + 1) * size)
        ))
        c_ar = np.asarray(result_arc.image.crop(
            (t_ar.column * size, t_ar.row * size, (t_ar.column + 1) * size, (t_ar.row + 1) * size)
        ))
        if not np.array_equal(c_ch, c_ar):
            diff_found = True
            break
    assert diff_found


