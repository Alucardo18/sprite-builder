import io
import json
import zipfile
import pytest
from PIL import Image

from sprite_builder.tilesets.patterns import (
    build_tilesetter_terrain_pattern,
    render_unity_ruletile_json,
    render_unity_ruletile_script,
    build_unity_ruletile_bundle,
    render_tiled_wangset_tsx,
    build_tiled_bundle,
    _blob_procedural_material,
    _hex_to_rgb,
)


def _make_test_atlas(size: int = 16) -> tuple[Image.Image, list[dict]]:
    atlas = Image.new("RGBA", (size * 2, size), (0, 0, 0, 0))
    tile_a = Image.new("RGBA", (size, size), (50, 180, 80, 255))
    tile_b = Image.new("RGBA", (size, size), (120, 80, 40, 255))
    atlas.paste(tile_a, (0, 0))
    atlas.paste(tile_b, (size, 0))
    sources = [
        {"id": "tile_a", "x": 0, "y": 0, "width": size, "height": size},
        {"id": "tile_b", "x": size, "y": 0, "width": size, "height": size},
    ]
    return atlas, sources


def test_procedural_material_custom_colors_and_presets() -> None:
    size = (16, 16)
    rgb = _hex_to_rgb("#ff8800")
    assert rgb == (255, 136, 0)

    # Custom color override
    custom_tile = _blob_procedural_material(size, "lava", base_color="#ff5500", seed=42)
    assert custom_tile.size == size
    assert custom_tile.mode == "RGBA"

    # Default presets
    for mat in ("grass", "dirt", "water", "stone", "sand", "lava", "snow", "dungeon"):
        tile = _blob_procedural_material(size, mat)
        assert tile.size == size
        assert tile.getpixel((0, 0))[3] == 255


def test_unity_ruletile_export_blob_and_wang() -> None:
    size = 16
    atlas, sources = _make_test_atlas(size)
    config = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "terrainProfile": "clean",
        "dropShadow": 2,
    }
    result_blob = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=config, kind="blob_47"
    )

    ruletile_json = render_unity_ruletile_json(result_blob, terrain_name="ForestGrass")
    parsed = json.loads(ruletile_json)
    assert parsed["terrain_name"] == "ForestGrass"
    assert parsed["kind"] == "blob_47"
    assert len(parsed["tiles"]) == 47

    # Validate neighbor rule values
    for t in parsed["tiles"]:
        neighbors = t["neighbors"]
        for dir_name in ("top_left", "top", "top_right", "left", "right", "bottom_left", "bottom", "bottom_right"):
            assert neighbors[dir_name] in ("This", "NotThis", "DontCare")

    ruletile_cs = render_unity_ruletile_script(result_blob, terrain_name="ForestGrass")
    assert "public static class CreateForestGrassRuleTile" in ruletile_cs
    assert "RuleTile.TilingRuleOutput.Neighbor.This" in ruletile_cs
    assert "RuleTile.TilingRuleOutput.Neighbor.NotThis" in ruletile_cs

    bundle_bytes = build_unity_ruletile_bundle(result_blob, terrain_name="ForestGrass")
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as zf:
        namelist = zf.namelist()
        assert "terrain_tiles.png" in namelist
        assert "terrain_bitmask_reference.png" in namelist
        assert "RuleTileConfig.json" in namelist
        assert "CreateForestGrassRuleTile.cs" in namelist
        assert "README_UNITY.txt" in namelist


def test_tiled_wangset_export() -> None:
    size = 16
    atlas, sources = _make_test_atlas(size)
    config = {
        "blobMode": "synthesis",
        "baseSource": "tile_a",
        "secondarySource": "tile_b",
        "terrainProfile": "clean",
    }
    result = build_tilesetter_terrain_pattern(
        atlas, tile_size=(size, size), sources=sources, set_config=config, kind="blob_47"
    )

    tsx = render_tiled_wangset_tsx(result, terrain_name="Meadow")
    assert 'name="Meadow"' in tsx
    assert '<wangset name="Meadow" type="mixed"' in tsx
    assert '<wangcolor name="Meadow"' in tsx
    assert '<wangtile tileid="' in tsx
    assert 'wangid="' in tsx

    tiled_zip = build_tiled_bundle(result, terrain_name="Meadow")
    with zipfile.ZipFile(io.BytesIO(tiled_zip), "r") as zf:
        namelist = zf.namelist()
        assert "terrain_tiles.png" in namelist
        assert "meadow.tsx" in namelist
        assert "terrain_bitmask_reference.png" in namelist
        assert "README_TILED.txt" in namelist


def test_tileset_wizard_studio_markup_and_handlers() -> None:
    from pathlib import Path
    from sprite_builder.ui import components

    studio_html = Path(components.__file__).parent / "terrain_pattern_studio_component" / "index.html"
    source = studio_html.read_text(encoding="utf-8")

    # Wizard controls exist
    assert 'id="openWizardBtn"' in source
    assert 'id="tilesetWizardModal"' in source
    assert 'id="closeWizardBtn"' in source
    assert 'id="applyWizardBtn"' in source
    assert 'wizard-preset' in source
    assert 'wizard-kind-grid' in source
    assert 'id="wizardCornerStyle"' in source
    assert 'id="wizardShadowTint"' in source
    assert 'id="wizardDropShadow"' in source
    assert 'id="wizardShadowDirection"' in source
    assert 'function openWizard()' in source
    assert 'function applyWizard()' in source

