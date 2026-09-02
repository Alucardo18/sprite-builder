"""Unit tests for AI material prompt templates and reference generation."""

from __future__ import annotations

import pytest
from PIL import Image

from sprite_builder.tilesets import (
    format_tile_prompt,
    generate_procedural_reference_tile,
    get_material_template,
    list_material_templates,
    prepare_tile_source_record,
)


def test_list_material_templates_contains_curated_biomes() -> None:
    templates = list_material_templates()
    template_ids = {t.id for t in templates}

    expected = {
        "grass_meadow",
        "dirt_earth",
        "stone_cobblestone",
        "water_ocean",
        "sand_desert",
        "snow_ice",
        "dungeon_slate",
        "wood_planks",
        "lava_magma",
        "scifi_metal",
    }
    assert expected.issubset(template_ids)


def test_get_material_template_found_and_not_found() -> None:
    grass = get_material_template("grass_meadow")
    assert grass is not None
    assert grass.name == "Césped / Pradera"
    assert grass.default_role == "base"

    missing = get_material_template("non_existent_biome")
    assert missing is None


def test_format_tile_prompt_includes_size_and_constraints() -> None:
    prompt_32 = format_tile_prompt("grass_meadow", tile_size=(32, 32))
    assert "32x32" in prompt_32
    assert "seamless repeatable texture swatch" in prompt_32
    assert "lush vibrant green" in prompt_32

    custom_prompt = format_tile_prompt(
        "stone_cobblestone",
        custom_instruction="covered in glowing blue moss runes",
        tile_size=(48, 48),
    )
    assert "48x48" in custom_prompt
    assert "covered in glowing blue moss runes" in custom_prompt
    assert "weathered gray cobblestone" in custom_prompt


def test_generate_procedural_reference_tile_deterministic() -> None:
    tile1 = generate_procedural_reference_tile("grass_meadow", (32, 32), seed=123)
    tile2 = generate_procedural_reference_tile("grass_meadow", (32, 32), seed=123)
    tile3 = generate_procedural_reference_tile("grass_meadow", (32, 32), seed=999)

    assert tile1.size == (32, 32)
    assert tile1.mode == "RGBA"
    assert list(tile1.get_flattened_data()) == list(tile2.get_flattened_data())
    assert list(tile1.get_flattened_data()) != list(tile3.get_flattened_data())


def test_generate_procedural_reference_tile_all_templates() -> None:
    for template in list_material_templates():
        img = generate_procedural_reference_tile(template.id, (24, 24), seed=42)
        assert img.size == (24, 24)
        assert img.mode == "RGBA"


def test_prepare_tile_source_record() -> None:
    img = Image.new("RGBA", (32, 32), (50, 100, 50, 255))
    record = prepare_tile_source_record(
        img,
        tile_size=(32, 32),
        source_id="src_grass_1",
        name="Pasto Base",
    )
    assert record["id"] == "src_grass_1"
    assert record["name"] == "Pasto Base"
    assert record["rect"] == [0, 0, 32, 32]
