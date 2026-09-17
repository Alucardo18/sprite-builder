"""Unit tests for TilesetAestheticPreset recipes and helpers."""

from __future__ import annotations

from sprite_builder.tilesets import (
    TILESET_AESTHETIC_PRESETS,
    detect_matching_aesthetic_preset,
    get_aesthetic_preset,
    list_aesthetic_presets,
)


def test_list_and_lookup_aesthetic_presets() -> None:
    presets = list_aesthetic_presets()
    assert len(presets) == 6
    assert presets == TILESET_AESTHETIC_PRESETS

    zelda = get_aesthetic_preset("zelda_topdown")
    assert zelda is not None
    assert zelda.name == "Zelda Top-Down"
    assert zelda.terrain_profile == "rounded_grass_tufts"
    assert zelda.rim_light is True
    assert zelda.drop_shadow == 2

    assert get_aesthetic_preset("non_existent") is None


def test_apply_aesthetic_preset_to_set_config() -> None:
    retro = get_aesthetic_preset("retro_16bit")
    assert retro is not None

    base_set = {"id": "test-set", "kind": "blob_47"}
    applied = retro.apply_to_set(base_set)

    assert applied["id"] == "test-set"
    assert applied["cornerRadius"] == 3
    assert applied["cornerStyle"] == "chamfer"
    assert applied["retroOutline"] is True
    assert applied["terrainProfile"] == "rounded_chamfer"
    assert applied["dropShadow"] == 3
    assert applied["shadowDirection"] == "south_east"
    assert applied["aestheticPreset"] == "retro_16bit"

    detected = detect_matching_aesthetic_preset(applied)
    assert detected == "retro_16bit"


def test_detect_matching_aesthetic_preset_from_traits() -> None:
    clean = get_aesthetic_preset("clean_pixel")
    assert clean is not None

    traits_only = {
        "terrainProfile": "clean",
        "cornerRadius": 0,
        "cornerStyle": "arc",
        "retroOutline": False,
        "dropShadow": 0,
        "rimLight": False,
    }
    assert detect_matching_aesthetic_preset(traits_only) == "clean_pixel"
