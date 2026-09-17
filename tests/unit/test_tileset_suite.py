"""Unit tests for multi-format terrain autotile suite generation and Omnibundle export."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from PIL import Image

from sprite_builder.tilesets import (
    CURATED_BIOME_PALETTES,
    TerrainPalette,
    TerrainSuiteResult,
    build_omnibundle_zip,
    generate_terrain_suite,
    get_curated_palette,
    hex_to_rgb,
    normalize_hex_color,
    rgb_to_hex,
)


def test_color_utilities() -> None:
    assert hex_to_rgb("#48A832") == (72, 168, 50)
    assert hex_to_rgb("#FFF") == (255, 255, 255)
    assert rgb_to_hex((72, 168, 50)) == "#48A832"
    assert normalize_hex_color("48a832") == "#48A832"
    assert normalize_hex_color("invalid", fallback="#000000") == "#000000"


def test_curated_biome_palettes() -> None:
    assert len(CURATED_BIOME_PALETTES) >= 5
    pradera = get_curated_palette("pradera")
    assert pradera is not None
    assert pradera.inside_material == "grass"
    assert pradera.outside_material == "dirt"
    assert pradera.primary_color == "#48A832"


def test_generate_terrain_suite_full_triad() -> None:
    suite = generate_terrain_suite(
        name="Pradera Mágica",
        primary_color="#48A832",
        secondary_color="#8B5A2B",
        preset_id="zelda_topdown",
        kinds=("blob_47", "dual_grid_15", "wang_16"),
        tile_size=(16, 16),
        variant_count=3,
        start_y=0,
    )

    assert suite.name == "Pradera Mágica"
    assert suite.tile_size == (16, 16)
    assert suite.kinds == ("blob_47", "dual_grid_15", "wang_16")

    # Blob 47 verification
    assert suite.blob_result is not None
    assert suite.blob_result.complete
    assert suite.blob_result.kind == "blob_47"
    assert suite.blob_result.variant_count == 3
    assert len(suite.blob_result.tiles) == 141  # 47 masks * 3 variants

    # Dual Grid 15 verification
    assert suite.dual_grid_result is not None
    assert suite.dual_grid_result.complete
    assert suite.dual_grid_result.kind == "dual_grid_15"
    assert len(suite.dual_grid_result.tiles) == 15
    dual_set = next(s for s in suite.project_sets if s["kind"] == "dual_grid_15")
    assert dual_set["terrainProfile"] == "organic_neutral"

    # Wang 16 verification
    assert suite.wang_result is not None
    assert suite.wang_result.complete
    assert suite.wang_result.kind == "wang_16"
    assert len(suite.wang_result.tiles) == 16

    # Verify project sets and non-overlapping originY
    assert len(suite.project_sets) == 3
    y_coords = [s["originY"] for s in suite.project_sets]
    assert y_coords[0] < y_coords[1] < y_coords[2]

    # Verify transport sources and combined collage
    assert len(suite.sources) == 2
    assert suite.source_atlas is not None
    assert suite.source_atlas.size == (32, 16)
    assert suite.combined_image is not None


def test_generate_terrain_suite_single_kind() -> None:
    suite = generate_terrain_suite(
        name="Solo Dual Grid",
        primary_color="#60A5FA",
        secondary_color="#1E293B",
        preset_id="clean_pixel",
        kinds=("dual_grid_15",),
        tile_size=(16, 16),
    )

    assert suite.kinds == ("dual_grid_15",)
    assert suite.dual_grid_result is not None
    assert suite.blob_result is None
    assert suite.wang_result is None
    assert len(suite.project_sets) == 1


def test_build_omnibundle_zip() -> None:
    suite = generate_terrain_suite(
        name="Costa Tropical",
        primary_color="#E5B869",
        secondary_color="#2B65EC",
        preset_id="coastal_organic",
        kinds=("blob_47", "dual_grid_15", "wang_16"),
        tile_size=(16, 16),
        variant_count=1,
    )

    zip_bytes = build_omnibundle_zip(suite, bundle_name="costa_tropical")
    assert isinstance(zip_bytes, bytes)
    assert len(zip_bytes) > 50_000

    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    namelist = archive.namelist()

    # Core metadata
    assert "README.md" in namelist
    assert "palette.json" in namelist
    assert "all_terrains_overview.png" in namelist

    palette_meta = json.loads(archive.read("palette.json"))
    assert palette_meta["name"] == "Costa Tropical"
    assert palette_meta["primary_color"] == "#E5B869"

    # Per-format folders
    for kind in ("blob_47", "dual_grid_15", "wang_16"):
        assert f"{kind}/terrain_tiles.png" in namelist
        assert f"{kind}/terrain_bitmask_reference.png" in namelist
        assert f"{kind}/godot_installer.zip" in namelist
        assert f"{kind}/unity_ruletile.zip" in namelist
        assert f"{kind}/tiled_wangset.zip" in namelist


def test_procedural_blob_with_custom_palette() -> None:
    from sprite_builder.tilesets.patterns import build_tilesetter_terrain_pattern

    # Simulate set configured via Blob 47 palette bar (e.g. Grass over Water with Costa palette)
    set_config = {
        "id": "test_blob_custom_palette",
        "name": "Blob · Pasto sobre agua",
        "kind": "blob_47",
        "blobMaterialMode": "procedural",
        "primaryColor": "#E5B869",
        "secondaryColor": "#2B65EC",
        "insideMaterial": "sand",
        "outsideMaterial": "water",
        "terrainProfile": "grass_over_water",
        "edgeVariation": 2,
        "variantCount": 1,
    }

    dummy_image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    result = build_tilesetter_terrain_pattern(
        dummy_image,
        tile_size=(16, 16),
        sources=[],
        set_config=set_config,
        kind="blob_47",
    )

    assert result is not None
    assert result.complete
    assert len(result.tiles) == 47
    center_tile = next((t for t in result.tiles if t.mask == 255), None)
    assert center_tile is not None
    pix_c = result.image.getpixel((center_tile.column * 16 + 8, center_tile.row * 16 + 8))
    # Sand color #E5B869: R > 200, G > 150, B < 150
    assert pix_c[0] > 200 and pix_c[1] > 150 and pix_c[2] < 150
    empty_tile = next((t for t in result.tiles if t.mask == 0), None)
    assert empty_tile is not None


def test_procedural_surface_noise_and_finishing_studio() -> None:
    from sprite_builder.tilesets import apply_procedural_surface_noise
    from sprite_builder.tilesets.patterns import build_tilesetter_terrain_pattern

    # 1. Direct noise testing on a test patch
    base_img = Image.new("RGBA", (16, 16), (100, 150, 200, 255))
    # Unmodified with style "none"
    no_noise = apply_procedural_surface_noise(base_img, noise_style="none", intensity=0.5)
    assert no_noise.tobytes() == base_img.tobytes()

    # Dither noise
    dithered = apply_procedural_surface_noise(base_img, noise_style="dither", intensity=0.3, seed=12)
    assert dithered.tobytes() != base_img.tobytes()
    # Alpha channel must remain 255 everywhere
    dithered_arr = list(dithered.tobytes())
    assert all(dithered_arr[i] == 255 for i in range(3, len(dithered_arr), 4))

    # Simplex noise
    simplex = apply_procedural_surface_noise(base_img, noise_style="simplex", intensity=0.3, seed=12)
    assert simplex.tobytes() != base_img.tobytes()

    # Gravel noise
    gravel = apply_procedural_surface_noise(base_img, noise_style="gravel", intensity=0.4, seed=42)
    assert gravel.tobytes() != base_img.tobytes()

    # 2. Pattern building with noise config
    set_cfg = {
        "id": "dual_grid_noise_test",
        "name": "Dual Grid with Noise",
        "kind": "dual_grid_15",
        "primaryColor": "#48A832",
        "secondaryColor": "#8B5A2B",
        "terrainProfile": "organic_neutral",
        "edgeVariation": 2,
        "edgeSeed": 777,
        "noiseStyle": "simplex",
        "noiseIntensity": 0.20,
    }
    res = build_tilesetter_terrain_pattern(
        Image.new("RGBA", (16, 16), (0, 0, 0, 0)),
        tile_size=(16, 16),
        sources=[],
        set_config=set_cfg,
        kind="dual_grid_15",
    )
    assert res is not None
    assert res.complete
    assert res.noise_style == "simplex"
    assert abs(res.noise_intensity - 0.20) < 0.01
    assert res.edge_seed == 777
    assert res.edge_variation == 2
    assert res.terrain_profile == "organic_neutral"


def test_aesthetic_presets_noise_and_differentiation() -> None:
    from sprite_builder.tilesets.patterns import (
        get_aesthetic_preset,
        apply_procedural_surface_noise,
        build_tilesetter_terrain_pattern,
    )
    import numpy as np

    # 1. Preset noise attributes and apply_to_set transfer
    gb = get_aesthetic_preset("gameboy_dither")
    assert gb is not None
    assert gb.noise_style == "dither"
    assert gb.noise_intensity >= 0.40

    applied_gb = gb.apply_to_set({"id": "test_s"})
    assert applied_gb["noiseStyle"] == "dither"
    assert applied_gb["noiseIntensity"] == gb.noise_intensity

    coastal = get_aesthetic_preset("coastal_organic")
    assert coastal is not None
    assert coastal.noise_style == "gravel"
    applied_coastal = coastal.apply_to_set({"id": "test_s"})
    assert applied_coastal["noiseStyle"] == "gravel"

    clean = get_aesthetic_preset("clean_pixel")
    assert clean is not None
    assert clean.noise_style == "none"

    # 2. Distinct noise signatures on a test tile
    tile = Image.new("RGBA", (16, 16), (80, 140, 90, 255))
    dither_tile = apply_procedural_surface_noise(tile, noise_style="dither", intensity=0.35, seed=1)
    simplex_tile = apply_procedural_surface_noise(tile, noise_style="simplex", intensity=0.35, seed=1)
    gravel_tile = apply_procedural_surface_noise(tile, noise_style="gravel", intensity=0.35, seed=1)
    none_tile = apply_procedural_surface_noise(tile, noise_style="none", intensity=0.35, seed=1)

    arr_orig = np.asarray(tile)
    arr_dither = np.asarray(dither_tile)
    arr_simplex = np.asarray(simplex_tile)
    arr_gravel = np.asarray(gravel_tile)
    arr_none = np.asarray(none_tile)

    assert np.array_equal(arr_orig, arr_none)
    assert not np.array_equal(arr_orig, arr_dither)
    assert not np.array_equal(arr_orig, arr_simplex)
    assert not np.array_equal(arr_orig, arr_gravel)
    assert not np.array_equal(arr_dither, arr_simplex)
    assert not np.array_equal(arr_simplex, arr_gravel)


