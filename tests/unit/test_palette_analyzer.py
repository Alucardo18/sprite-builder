"""Unit tests for the chromatic biome palette analyzer and multi-blob generator."""

import numpy as np
import pytest
from PIL import Image

from sprite_builder.tilesets.palette_analyzer import (
    BiomePalette,
    HarvestedTileSample,
    analyze_image_biome_palette,
    generate_biome_ecosystem_sets,
    harvest_image_terrain_tiles,
)
from sprite_builder.tilesets.patterns import build_tilesetter_terrain_pattern



def test_analyze_palette_grass_dominant():
    # Green image (grass)
    img = Image.new("RGBA", (32, 32), (68, 142, 78, 255))
    palette = analyze_image_biome_palette(img)
    assert isinstance(palette, BiomePalette)
    assert palette.grass.detected is True
    assert "grass" in palette.detected_terrains
    assert palette.dominant_terrain == "grass"
    assert palette.grass.hex_color.lower() == "#448e4e"


def test_analyze_palette_dirt_dominant():
    # Brown image (dirt) - RGB (139, 90, 43)
    img = Image.new("RGBA", (32, 32), (139, 90, 43, 255))
    palette = analyze_image_biome_palette(img)
    assert palette.dirt.detected is True
    assert "dirt" in palette.detected_terrains
    assert palette.dirt.hex_color.lower() == "#8b5a2b"


def test_analyze_palette_water_dominant():
    # Blue image (water) - RGB (40, 116, 166)
    img = Image.new("RGBA", (32, 32), (40, 116, 166, 255))
    palette = analyze_image_biome_palette(img)
    assert palette.water.detected is True
    assert "water" in palette.detected_terrains
    assert palette.water.hex_color.lower() == "#2874a6"


def test_analyze_palette_multi_biome_patches():
    # Multi-tile reference image with grass (top), dirt (middle), water (bottom)
    arr = np.zeros((48, 16, 4), dtype=np.uint8)
    arr[0:16, :, :] = (60, 150, 70, 255)   # grass
    arr[16:32, :, :] = (140, 95, 50, 255)  # dirt
    arr[32:48, :, :] = (35, 110, 175, 255) # water
    img = Image.fromarray(arr, mode="RGBA")

    palette = analyze_image_biome_palette(img)
    assert palette.grass.detected is True
    assert palette.dirt.detected is True
    assert palette.water.detected is True
    assert set(["grass", "dirt", "water"]).issubset(set(palette.detected_terrains))


def test_analyze_palette_monochrome_fallback():
    # Grayscale image (dungeon/moon) - should map tiers by luminance
    arr = np.zeros((30, 30, 4), dtype=np.uint8)
    arr[0:10, :, :] = (210, 210, 210, 255) # light
    arr[10:20, :, :] = (120, 120, 120, 255) # mid
    arr[20:30, :, :] = (40, 40, 40, 255)   # dark
    img = Image.fromarray(arr, mode="RGBA")

    palette = analyze_image_biome_palette(img)
    assert palette.grass.detected is True
    assert palette.dirt.detected is True
    assert palette.water.detected is True


def test_analyze_palette_empty_or_transparent():
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    palette = analyze_image_biome_palette(img)
    assert isinstance(palette, BiomePalette)
    assert palette.grass.hex_color is not None
    assert palette.dirt.hex_color is not None
    assert palette.water.hex_color is not None


def test_generate_biome_ecosystem_sets():
    palette = analyze_image_biome_palette(Image.new("RGBA", (16, 16), (70, 140, 80, 255)))
    sets = generate_biome_ecosystem_sets(
        palette,
        kind="blob_47",
        style_config={"cornerStyle": "chamfer", "dropShadow": 2, "shadowTint": "cool"},
        start_y=0,
        variant_count=5,
    )

    assert len(sets) == 3
    set1, set2, set3 = sets
    assert set1["terrainProfile"] == "grass_over_dirt"
    assert set2["terrainProfile"] == "dirt_over_water"
    assert set3["terrainProfile"] == "grass_over_water"

    # Verify originY does not overlap
    assert set1["originY"] == 0
    assert set2["originY"] == 7
    assert set3["originY"] == 14

    # Verify variantCount is 5
    assert set1["variantCount"] == 5
    assert set2["variantCount"] == 5
    assert set3["variantCount"] == 5

    # Verify building tilesetter pattern with procedural 5 variants
    atlas = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    pattern_result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=[],
        set_config=set1,
        kind="blob_47",
        columns=11,
    )
    # 47 tiles * 5 variants = 235 tiles
    assert len(pattern_result.tiles) == 235
    assert pattern_result.variant_count == 5


def test_palette_serialization_to_dict():
    img = Image.new("RGBA", (16, 16), (50, 150, 80, 255))
    palette = analyze_image_biome_palette(img)
    data = palette.to_dict()
    assert "grass" in data
    assert "dirt" in data
    assert "water" in data
    assert data["grass"]["hex_color"].startswith("#")
    assert isinstance(data["detected_terrains"], list)


def test_generate_biome_ecosystem_dual_grid():
    palette = analyze_image_biome_palette(Image.new("RGBA", (16, 16), (70, 140, 80, 255)))
    sets = generate_biome_ecosystem_sets(
        palette,
        kind="dual_grid_15",
        start_y=2,
    )
    assert len(sets) == 3
    assert sets[0]["kind"] == "dual_grid_15"
    assert sets[0]["columns"] == 4
    assert sets[0]["rows"] == 4
    assert sets[0]["originY"] == 2
    assert sets[1]["originY"] == 7
    assert sets[2]["originY"] == 12


def test_harvest_image_terrain_tiles():
    # 48x32 image: 3 columns x 2 rows of 16x16 tiles
    # Row 0: pure grass (tile 0,0), noisy grass (tile 1,0), pure dirt (tile 2,0)
    # Row 1: pure water (tile 0,1), mixed grass/dirt (tile 1,1), transparent (tile 2,1)
    arr = np.zeros((32, 48, 4), dtype=np.uint8)

    # Tile (0, 0): Grass with slight variation
    rng = np.random.default_rng(42)
    grass_base = np.array([60, 140, 70, 255], dtype=np.uint8)
    noise = rng.integers(-10, 10, size=(16, 16, 3))
    arr[0:16, 0:16, :3] = np.clip(grass_base[:3] + noise, 0, 255)
    arr[0:16, 0:16, 3] = 255

    # Tile (1, 0): Another grass tile with more texture variance
    noise2 = rng.integers(-25, 25, size=(16, 16, 3))
    arr[0:16, 16:32, :3] = np.clip(grass_base[:3] + noise2, 0, 255)
    arr[0:16, 16:32, 3] = 255

    # Tile (2, 0): Pure dirt tile
    dirt_base = np.array([139, 90, 43, 255], dtype=np.uint8)
    dirt_noise = rng.integers(-15, 15, size=(16, 16, 3))
    arr[0:16, 32:48, :3] = np.clip(dirt_base[:3] + dirt_noise, 0, 255)
    arr[0:16, 32:48, 3] = 255

    # Tile (0, 1): Water tile
    water_base = np.array([40, 116, 166, 255], dtype=np.uint8)
    water_noise = rng.integers(-5, 5, size=(16, 16, 3))
    arr[16:32, 0:16, :3] = np.clip(water_base[:3] + water_noise, 0, 255)
    arr[16:32, 0:16, 3] = 255

    # Tile (1, 1): Half grass half dirt (mixed, purity < 0.7)
    arr[16:32, 16:24, :3] = grass_base[:3]
    arr[16:32, 16:24, 3] = 255
    arr[16:32, 24:32, :3] = dirt_base[:3]
    arr[16:32, 24:32, 3] = 255

    # Tile (2, 1) remains transparent (0, 0, 0, 0)

    img = Image.fromarray(arr, mode="RGBA")
    harvested = harvest_image_terrain_tiles(img, tile_size=(16, 16), max_samples_per_biome=3, min_purity=0.7)

    assert "grass" in harvested
    assert "dirt" in harvested
    assert "water" in harvested

    # Grass should have harvested 2 tiles (tile 0,0 and tile 1,0)
    assert len(harvested["grass"]) == 2
    # The one with higher texture variance should be first
    assert harvested["grass"][0].texture_variance >= harvested["grass"][1].texture_variance
    assert harvested["grass"][0].purity >= 0.7

    # Dirt should have 1 tile
    assert len(harvested["dirt"]) == 1
    assert harvested["dirt"][0].bounds == (32, 0, 16, 16)

    # Water should have 1 tile
    assert len(harvested["water"]) == 1
    assert harvested["water"][0].bounds == (0, 16, 16, 16)


def test_generate_biome_ecosystem_sets_with_harvested_sources():
    palette = analyze_image_biome_palette(Image.new("RGBA", (16, 16), (70, 140, 80, 255)))
    harvested = {
        "grass": [HarvestedTileSample("grass", (0, 0, 16, 16), Image.new("RGBA", (16, 16), (60, 140, 70, 255)), 0.95, 12.0)],
        "dirt": [HarvestedTileSample("dirt", (16, 0, 16, 16), Image.new("RGBA", (16, 16), (139, 90, 43, 255)), 0.92, 10.0)],
        "water": [HarvestedTileSample("water", (32, 0, 16, 16), Image.new("RGBA", (16, 16), (40, 116, 166, 255)), 0.98, 5.0)],
    }
    source_map = {
        "grass": "harvest_grass_0",
        "dirt": "harvest_dirt_0",
        "water": "harvest_water_0",
    }

    sets = generate_biome_ecosystem_sets(
        palette,
        kind="blob_47",
        harvested_tiles=harvested,
        source_id_map=source_map,
        start_y=0,
    )

    assert len(sets) == 3
    grass_dirt = sets[0]
    assert grass_dirt["terrainProfile"] == "grass_over_dirt"
    assert grass_dirt["baseSource"] == "harvest_grass_0"
    assert grass_dirt["secondarySource"] == "harvest_dirt_0"
    assert grass_dirt["blobMaterialMode"] == "synthesis"
    assert grass_dirt["edgeProfile"] == "rounded_grass_tufts"

    dirt_water = sets[1]
    assert dirt_water["baseSource"] == "harvest_dirt_0"
    assert dirt_water["secondarySource"] == "harvest_water_0"
    assert dirt_water["blobMaterialMode"] == "synthesis"

    # Now verify building the tilesetter pattern using these sources
    sources = [
        {"id": "harvest_grass_0", "name": "Grass", "bounds": [0, 0, 16, 16]},
        {"id": "harvest_dirt_0", "name": "Dirt", "bounds": [16, 0, 16, 16]},
    ]
    atlas = Image.new("RGBA", (64, 16), (0, 0, 0, 0))
    atlas.paste(harvested["grass"][0].image, (0, 0))
    atlas.paste(harvested["dirt"][0].image, (16, 0))

    pattern_result = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=(16, 16),
        sources=sources,
        set_config=grass_dirt,
        kind="blob_47",
        columns=11,
    )
    assert len(pattern_result.tiles) == 47 * grass_dirt.get("variantCount", 1)
    assert pattern_result.columns == 11 * grass_dirt.get("variantCount", 1)



