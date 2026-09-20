"""Tests for automatic Blob 47 inverted variant generation (A sobre B <-> B sobre A)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from sprite_builder.tilesets.patterns import (
    TerrainPatternResult,
    TerrainPatternTile,
    build_tilesetter_terrain_pattern,
)
from sprite_builder.ui import components

STUDIO_HTML = Path(components.__file__).parent / "terrain_pattern_studio_component" / "index.html"
UI_APP = Path(components.__file__).parent / "app.py"


def test_blob_inverted_variant_html_contract() -> None:
    content = STUDIO_HTML.read_text(encoding="utf-8")

    # 1. buildProceduralBlob generates both primary and inverted sets
    assert "buildProceduralBlob" in content
    assert "Tierra sobre pasto" in content
    assert "Agua sobre tierra" in content
    assert "Agua sobre pasto" in content
    assert "invertedProfile" in content
    assert "invertedLabel" in content
    assert (
        "state.project.sets.push(set1, set2);" in content
        or "state.project.sets.push(set);" in content
    )

    # 2. buildBlobFromTwoTiles creates both A sobre B and B sobre A
    assert "Blob Set (A sobre B)" in content
    assert "Blob Set (B sobre A) · Invertido" in content
    assert "tiles[0].sourceId" in content
    assert "tiles[1].sourceId" in content

    # 3. Dedicated invertActiveBlobSet function exists
    assert "function invertActiveBlobSet()" in content
    assert 'id="invertBlobSet"' in content
    assert "invertActiveBlobSet" in content

    # 4. buildSet routes 2-tile selections to buildBlobFromTwoTiles
    assert (
        'if(kind==="blob_47"&&selectedTiles().length===2)'
        "{buildBlobFromTwoTiles();return}" in content
    )


def test_blob_inverted_variant_ui_app_contract() -> None:
    content = UI_APP.read_text(encoding="utf-8")
    assert "🔄 Generar Variante Invertida (B sobre A)" in content
    assert 'inverted["baseSource"] = active_set.get("secondarySource")' in content
    assert 'inverted["secondarySource"] = active_set.get("baseSource")' in content


def test_blob_inverted_synthesis_and_mask_inversion() -> None:
    # 16x16 sample tiles
    size = (16, 16)
    # Primary: Green grass (48, 168, 50)
    grass = Image.new("RGBA", size, (48, 168, 50, 255))
    # Secondary: Brown dirt (139, 90, 43)
    dirt = Image.new("RGBA", size, (139, 90, 43, 255))

    atlas = Image.new("RGBA", (32, 16), (0, 0, 0, 0))
    atlas.paste(grass, (0, 0))
    atlas.paste(dirt, (16, 0))

    sources = [
        {"id": "src_grass", "x": 0, "y": 0, "width": 16, "height": 16},
        {"id": "src_dirt", "x": 16, "y": 0, "width": 16, "height": 16},
    ]

    # Set 1: Grass over Dirt (Pasto sobre Tierra)
    set_grass_dirt = {
        "id": "set_primary",
        "name": "Blob · Pasto sobre tierra",
        "kind": "blob_47",
        "baseSource": "src_grass",
        "secondarySource": "src_dirt",
        "blobMode": "synthesis",
        "terrainProfile": "grass_over_dirt",
        "originX": 0,
        "originY": 0,
        "columns": 11,
        "rows": 5,
    }

    res_primary = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config=set_grass_dirt,
        kind="blob_47",
    )
    assert res_primary is not None
    assert len(res_primary.tiles) == 47

    # Set 2: Inverted Dirt over Grass (Tierra sobre Pasto)
    set_dirt_grass = {
        "id": "set_inverted",
        "name": "Blob · Tierra sobre pasto (Invertido)",
        "kind": "blob_47",
        "baseSource": "src_dirt",
        "secondarySource": "src_grass",
        "blobMode": "synthesis",
        "terrainProfile": "rounded_grass_tufts",
        "originX": 0,
        "originY": 7,
        "columns": 11,
        "rows": 5,
    }

    res_inverted = build_tilesetter_terrain_pattern(
        atlas,
        tile_size=size,
        sources=sources,
        set_config=set_dirt_grass,
        kind="blob_47",
    )
    assert res_inverted is not None
    assert len(res_inverted.tiles) == 47

    def get_tile_image(res: TerrainPatternResult, tile: TerrainPatternTile) -> Image.Image:
        x0 = tile.column * res.tile_width
        y0 = tile.row * res.tile_height
        return res.image.crop((x0, y0, x0 + res.tile_width, y0 + res.tile_height))

    # In Set 1 (Grass over Dirt):
    # Mask 0 is full exterior (Dirt)
    tile_primary_0 = next(t for t in res_primary.tiles if t.mask == 0)
    arr_p0 = np.asarray(get_tile_image(res_primary, tile_primary_0))
    # Average color of tile 0 in primary is brown dirt
    assert arr_p0[..., 0].mean() > 100  # R of dirt
    assert arr_p0[..., 1].mean() < 120  # G of dirt

    # Mask 255 is full interior (Grass)
    tile_primary_255 = next(t for t in res_primary.tiles if t.mask == 255)
    arr_p255 = np.asarray(get_tile_image(res_primary, tile_primary_255))
    assert arr_p255[..., 1].mean() > 140  # G of grass
    assert arr_p255[..., 0].mean() < 80   # R of grass

    # In Set 2 (Dirt over Grass - Inverted):
    # Mask 0 is full exterior (Grass)
    tile_inv_0 = next(t for t in res_inverted.tiles if t.mask == 0)
    arr_i0 = np.asarray(get_tile_image(res_inverted, tile_inv_0))
    assert arr_i0[..., 1].mean() > 140  # G of grass (now exterior!)
    assert arr_i0[..., 0].mean() < 80

    # Mask 255 is full interior (Dirt)
    tile_inv_255 = next(t for t in res_inverted.tiles if t.mask == 255)
    arr_i255 = np.asarray(get_tile_image(res_inverted, tile_inv_255))
    assert arr_i255[..., 0].mean() > 100  # R of dirt (now interior!)
    assert arr_i255[..., 1].mean() < 120
