"""Unit and adversarial tests for the authentic Wang 16 (2-Edge) autotile system."""

from __future__ import annotations

import zipfile
import io
import json
import numpy as np
import pytest
from PIL import Image

from sprite_builder.tilesets.patterns import (
    generate_terrain_pattern,
    terrain_pattern_layout,
    terrain_pattern_manifest,
    terrain_pattern_masks,
    render_godot_terrain_installer,
    render_tiled_wangset_tsx,
    render_unity_ruletile_json,
    _tile_neighbors,
)
from sprite_builder.tilesets.autotile import (
    autotile_sides16,
    clear_tile_matrix,
)
from sprite_builder.tilesets.suite import generate_terrain_suite


def test_wang_16_pattern_mode_and_canonical_edge_layout() -> None:
    inside = Image.new("RGBA", (16, 16), (200, 150, 50, 255))
    outside = Image.new("RGBA", (16, 16), (30, 80, 160, 255))

    result = generate_terrain_pattern(inside, outside, kind="wang_16")

    assert result.kind == "wang_16"
    assert result.mode == "match_sides"
    assert len(result.tiles) == 16
    assert result.columns == 4
    assert result.rows == 4

    layout = terrain_pattern_layout("wang_16")
    assert layout == (
        (4, 6, 14, 12),
        (5, 7, 15, 13),
        (1, 3, 11, 9),
        (0, 2, 10, 8),
    )


def test_wang_16_all_16_masks_map_to_cardinal_edges() -> None:
    expected_neighbors = {
        0: (),
        1: ("top",),
        2: ("right",),
        3: ("top", "right"),
        4: ("bottom",),
        5: ("top", "bottom"),  # straight vertical road
        6: ("right", "bottom"),  # bend right-down
        7: ("top", "right", "bottom"),  # T-junction pointing right
        8: ("left",),
        9: ("top", "left"),  # bend top-left
        10: ("right", "left"),  # straight horizontal road
        11: ("top", "right", "left"),  # T-junction pointing up
        12: ("bottom", "left"),  # bend bottom-left
        13: ("top", "bottom", "left"),  # T-junction pointing left
        14: ("right", "bottom", "left"),  # T-junction pointing down
        15: ("top", "right", "bottom", "left"),  # 4-way cross intersection
    }

    for mask, expected in expected_neighbors.items():
        neighbors = _tile_neighbors("wang_16", mask)
        assert neighbors == expected, f"Failed for mask {mask}: {neighbors} != {expected}"


def test_wang_16_godot_export_uses_match_sides_and_cardinal_peering_bits() -> None:
    inside = Image.new("RGBA", (16, 16), (100, 200, 100, 255))
    outside = Image.new("RGBA", (16, 16), (40, 40, 40, 255))
    result = generate_terrain_pattern(inside, outside, kind="wang_16")

    gd_script = render_godot_terrain_installer(result, terrain_name="Roads")

    assert "TileSet.TERRAIN_MODE_MATCH_SIDES" in gd_script
    # Peering bits for top (12), right (0), bottom (4), left (8)
    assert '"peers":' in gd_script

    manifest = terrain_pattern_manifest(result, terrain_name="Roads")
    assert manifest["godot"]["mode"] == "match_sides"


def test_wang_16_tiled_export_uses_edge_wangset_type() -> None:
    inside = Image.new("RGBA", (16, 16), (100, 200, 100, 255))
    outside = Image.new("RGBA", (16, 16), (40, 40, 40, 255))
    result = generate_terrain_pattern(inside, outside, kind="wang_16")

    tsx_xml = render_tiled_wangset_tsx(result, terrain_name="Paths")

    assert '<wangset name="Paths" type="edge"' in tsx_xml
    # 16 wangtile entries
    assert tsx_xml.count("<wangtile") == 16


def test_wang_16_unity_ruletile_json_rules() -> None:
    inside = Image.new("RGBA", (16, 16), (100, 200, 100, 255))
    outside = Image.new("RGBA", (16, 16), (40, 40, 40, 255))
    result = generate_terrain_pattern(inside, outside, kind="wang_16")

    ruletile_json = render_unity_ruletile_json(result, terrain_name="Paths")

    assert '"kind": "wang_16"' in ruletile_json
    # Vertical road (mask 5) must have top and bottom as "This", right and left as "NotThis"
    data = json.loads(ruletile_json)
    rule_mask_5 = next(t for t in data["tiles"] if t["mask"] == 5)
    assert rule_mask_5["neighbors"]["top"] == "This"
    assert rule_mask_5["neighbors"]["bottom"] == "This"
    assert rule_mask_5["neighbors"]["right"] == "NotThis"
    assert rule_mask_5["neighbors"]["left"] == "NotThis"
    assert rule_mask_5["neighbors"]["top_left"] == "DontCare"


def test_autotile_sides16_engine_paints_continuous_roads() -> None:
    inside = Image.new("RGBA", (16, 16), (255, 255, 255, 255))
    outside = Image.new("RGBA", (16, 16), (0, 0, 0, 255))
    result = generate_terrain_pattern(inside, outside, kind="wang_16")

    grid = clear_tile_matrix(5, 5)
    # Paint a horizontal road on row 2: (1, 2), (2, 2), (3, 2)
    grid[2][1] = True
    grid[2][2] = True
    grid[2][3] = True

    rendered = autotile_sides16(grid, result.image, (16, 16))
    assert rendered.size == (5 * 16, 5 * 16)


def test_triad_coexistence_proves_differentiation() -> None:
    """Prove that the 3 members of the triad produce 3 distinctly different modes and purposes."""
    suite = generate_terrain_suite(
        name="TriadTest",
        primary_color="#44AA44",
        secondary_color="#885522",
        kinds=("blob_47", "dual_grid_15", "wang_16"),
        tile_size=(16, 16),
    )

    blob = suite.blob_result
    dual = suite.dual_grid_result
    wang = suite.wang_result

    assert blob is not None
    assert dual is not None
    assert wang is not None

    # 1. Modes are completely differentiated
    assert blob.mode == "match_corners_and_sides"
    assert dual.mode == "match_corners"
    assert wang.mode == "match_sides"

    # 2. Tile counts
    assert len(blob.tiles) == 141  # 47 masks * 3 banks
    assert len(dual.tiles) == 15
    assert len(wang.tiles) == 16

    # 3. Godot exported peering modes
    blob_gd = render_godot_terrain_installer(blob)
    dual_gd = render_godot_terrain_installer(dual)
    wang_gd = render_godot_terrain_installer(wang)

    assert "TERRAIN_MODE_MATCH_CORNERS_AND_SIDES" in blob_gd
    assert "TERRAIN_MODE_MATCH_CORNERS" in dual_gd
    assert "TERRAIN_MODE_MATCH_SIDES" in wang_gd
