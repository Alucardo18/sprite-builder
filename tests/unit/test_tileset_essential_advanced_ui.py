"""Unit tests for Tileset Builder Essential vs Advanced finishing mode UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import io
import json
import zipfile

from streamlit.testing.v1 import AppTest

from sprite_builder.tilesets.suite import generate_terrain_suite
from sprite_builder.ui import app
from sprite_builder.ui.app import _build_multi_set_omnibundle_zip


def _setup_tileset_session(test_app: AppTest) -> str:
    """Helper to initialize a project with an active starter set."""
    prefix = "tileset_builder:patterns"
    project_key = f"{prefix}:set_view_project"
    set_id = "test_set_123"

    project: dict[str, Any] = {
        "version": 3,
        "sources": [
            {"id": "src_1", "name": "Base", "x": 0, "y": 0, "width": 16, "height": 16, "rect": [0, 0, 16, 16]},
            {"id": "src_2", "name": "Fondo", "x": 16, "y": 0, "width": 16, "height": 16, "rect": [16, 0, 16, 16]},
        ],
        "tiles": [
            {"id": "t_1", "sourceId": "src_1", "x": 0, "y": 0},
            {"id": "t_2", "sourceId": "src_2", "x": 1, "y": 0},
        ],
        "sets": [
            {
                "id": set_id,
                "name": "Pradera Test",
                "kind": "blob_47",
                "baseSource": "src_1",
                "secondarySource": "src_2",
                "primaryColor": "#48A832",
                "secondaryColor": "#8B5A2B",
                "blobMaterialMode": "procedural",
                "terrainProfile": "organic_neutral",
                "dropShadow": 2,
                "rimLight": False,
                "noiseStyle": "dither",
                "noiseIntensity": 0.25,
                "variantCount": 1,
                "cornerRadius": 2,
                "cornerStyle": "arc",
                "edgeVariation": 1,
            }
        ],
        "activeSetId": set_id,
        "palette": {
            "biome": "pradera",
            "primary": "#48A832",
            "secondary": "#8B5A2B",
            "water": "#2B65EC",
        },
    }

    test_app.session_state[project_key] = project
    test_app.session_state["tileset_builder:tile_size"] = 16
    return set_id


def _setup_multi_set_tileset_session(test_app: AppTest) -> list[str]:
    """Helper to initialize a project with a full 3-set suite (Blob 47, Dual Grid 15, Wang 16)."""
    prefix = "tileset_builder:patterns"
    project_key = f"{prefix}:set_view_project"
    suite = generate_terrain_suite(
        name="Pradera Completa",
        primary_color="#48A832",
        secondary_color="#8B5A2B",
        kinds=("blob_47", "dual_grid_15", "wang_16"),
        tile_size=(16, 16),
        variant_count=1,
    )
    project: dict[str, Any] = {
        "version": 3,
        "sources": [dict(s) for s in suite.sources],
        "tiles": [
            {"id": "t_1", "sourceId": suite.sources[0]["id"], "x": 0, "y": 0},
            {"id": "t_2", "sourceId": suite.sources[1]["id"], "x": 1, "y": 0},
        ],
        "sets": [dict(s) for s in suite.project_sets],
        "activeSetId": suite.project_sets[0]["id"],
        "palette": {
            "biome": "pradera",
            "primary": "#48A832",
            "secondary": "#8B5A2B",
        },
    }
    test_app.session_state[project_key] = project
    test_app.session_state["tileset_builder:tile_size"] = 16
    return [str(s["id"]) for s in suite.project_sets]


def test_default_mode_is_essential() -> None:
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_id = _setup_tileset_session(test_app)
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"
    mode_radio = next(
        (r for r in test_app.radio if f"{prefix}:finish_ctrl_mode:{set_id}" in r.key),
        None,
    )
    assert mode_radio is not None
    assert mode_radio.value == "⚡ Esencial (Guiado)"

    # In Essential mode, essential controls must be present
    ess_shadow = next((s for s in test_app.slider if f"{prefix}:finish_ess_drop_shadow:{set_id}" in s.key), None)
    assert ess_shadow is not None
    assert ess_shadow.value == 2

    ess_rim = next((c for c in test_app.checkbox if f"{prefix}:finish_ess_rim_light:{set_id}" in c.key), None)
    assert ess_rim is not None
    assert ess_rim.value is False

    ess_noise = next((sb for sb in test_app.selectbox if f"{prefix}:finish_ess_noise_style:{set_id}" in sb.key), None)
    assert ess_noise is not None
    assert ess_noise.value == "dither"

    # Granular advanced controls must NOT be present in Essential mode
    adv_corner_r = next((s for s in test_app.slider if f"{prefix}:finish_corner_radius:{set_id}" in s.key), None)
    assert adv_corner_r is None

    adv_edge_var = next((s for s in test_app.slider if f"{prefix}:finish_edge_var:{set_id}" in s.key), None)
    assert adv_edge_var is None

    adv_profile = next((sb for sb in test_app.selectbox if f"{prefix}:finish_terrain_profile:{set_id}" in sb.key), None)
    assert adv_profile is None

    adv_shadow_dir = next((sb for sb in test_app.selectbox if f"{prefix}:finish_shadow_dir:{set_id}" in sb.key), None)
    assert adv_shadow_dir is None


def test_switching_to_advanced_mode_exposes_granular_controls() -> None:
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_id = _setup_tileset_session(test_app)
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"
    mode_radio = next(
        (r for r in test_app.radio if f"{prefix}:finish_ctrl_mode:{set_id}" in r.key),
        None,
    )
    assert mode_radio is not None

    # Switch to Advanced Mode
    mode_radio.set_value("🎛️ Avanzado (Control Total)").run(timeout=30)
    assert not test_app.exception

    # Granular controls must now be present
    adv_corner_r = next((s for s in test_app.slider if f"{prefix}:finish_corner_radius:{set_id}" in s.key), None)
    assert adv_corner_r is not None
    assert adv_corner_r.value == 2

    adv_corner_style = next((sb for sb in test_app.selectbox if f"{prefix}:finish_corner_style:{set_id}" in sb.key), None)
    assert adv_corner_style is not None

    adv_profile = next((sb for sb in test_app.selectbox if f"{prefix}:finish_terrain_profile:{set_id}" in sb.key), None)
    assert adv_profile is not None
    assert adv_profile.value == "organic_neutral"

    adv_shadow_dir = next((sb for sb in test_app.selectbox if f"{prefix}:finish_shadow_dir:{set_id}" in sb.key), None)
    assert adv_shadow_dir is not None

    adv_shadow_tint = next((sb for sb in test_app.selectbox if f"{prefix}:finish_shadow_tint:{set_id}" in sb.key), None)
    assert adv_shadow_tint is not None


def test_essential_mode_parameter_changes_persist_to_project() -> None:
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_id = _setup_tileset_session(test_app)
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"

    # Modify shadow in essential mode
    ess_shadow = next((s for s in test_app.slider if f"{prefix}:finish_ess_drop_shadow:{set_id}" in s.key), None)
    assert ess_shadow is not None
    ess_shadow.set_value(5).run(timeout=30)
    assert not test_app.exception

    # Modify rim light in essential mode
    ess_rim = next((c for c in test_app.checkbox if f"{prefix}:finish_ess_rim_light:{set_id}" in c.key), None)
    assert ess_rim is not None
    ess_rim.check().run(timeout=30)
    assert not test_app.exception

    # Check project state
    project = test_app.session_state[f"{prefix}:set_view_project"]
    saved_set = project["sets"][0]
    assert saved_set["dropShadow"] == 5
    assert saved_set["rimLight"] is True

    # Switch to Advanced Mode and verify the advanced sliders display the updated values
    mode_radio = next(
        (r for r in test_app.radio if f"{prefix}:finish_ctrl_mode:{set_id}" in r.key),
        None,
    )
    assert mode_radio is not None
    mode_radio.set_value("🎛️ Avanzado (Control Total)").run(timeout=30)
    assert not test_app.exception

    adv_shadow = next((s for s in test_app.slider if f"{prefix}:finish_drop_shadow:{set_id}" in s.key), None)
    assert adv_shadow is not None
    assert adv_shadow.value == 5

    adv_rim = next((c for c in test_app.checkbox if f"{prefix}:finish_rim_light:{set_id}" in c.key), None)
    assert adv_rim is not None
    assert adv_rim.value is True


def test_preset_application_synchronizes_essential_and_advanced() -> None:
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_id = _setup_tileset_session(test_app)
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"

    # Select Retro 16-bit preset
    preset_sel = next(
        (sb for sb in test_app.selectbox if f"{prefix}:finish_preset_picker:{set_id}" in sb.key),
        None,
    )
    assert preset_sel is not None
    preset_sel.set_value("retro_16bit").run(timeout=30)
    assert not test_app.exception

    # Click Apply
    apply_btn = next((b for b in test_app.button if f"{prefix}:finish_apply_preset:{set_id}" in b.key), None)
    assert apply_btn is not None
    apply_btn.click().run(timeout=30)
    assert not test_app.exception

    # Project should have retro_16bit traits
    project = test_app.session_state[f"{prefix}:set_view_project"]
    applied_set = project["sets"][0]
    assert applied_set["aestheticPreset"] == "retro_16bit"
    assert applied_set["dropShadow"] == 3
    assert applied_set["retroOutline"] is True

    # In Essential mode, the shadow slider should reflect 3px
    ess_shadow = next((s for s in test_app.slider if f"{prefix}:finish_ess_drop_shadow:{set_id}" in s.key), None)
    assert ess_shadow is not None
    assert ess_shadow.value == 3


def test_repeated_mode_switching_stability() -> None:
    """Adversarial test: Repeatedly switch between Essential and Advanced 6 times."""
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_id = _setup_tileset_session(test_app)
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"
    modes = [
        "🎛️ Avanzado (Control Total)",
        "⚡ Esencial (Guiado)",
        "🎛️ Avanzado (Control Total)",
        "⚡ Esencial (Guiado)",
        "🎛️ Avanzado (Control Total)",
        "⚡ Esencial (Guiado)",
    ]

    for target_mode in modes:
        mode_radio = next(
            (r for r in test_app.radio if f"{prefix}:finish_ctrl_mode:{set_id}" in r.key),
            None,
        )
        assert mode_radio is not None
        mode_radio.set_value(target_mode).run(timeout=30)
        assert not test_app.exception

        if "Esencial" in target_mode:
            assert any(f"{prefix}:finish_ess_drop_shadow:{set_id}" in s.key for s in test_app.slider)
            assert not any(f"{prefix}:finish_corner_radius:{set_id}" in s.key for s in test_app.slider)
        else:
            assert any(f"{prefix}:finish_drop_shadow:{set_id}" in s.key for s in test_app.slider)
            assert any(f"{prefix}:finish_corner_radius:{set_id}" in s.key for s in test_app.slider)
            assert not any(f"{prefix}:finish_ess_drop_shadow:{set_id}" in s.key for s in test_app.slider)


def test_adversarial_bidirectional_macro_sync() -> None:
    """Adversarial test: Modify values in Essential, verify in Advanced, then modify in Advanced, verify in Essential."""
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_id = _setup_tileset_session(test_app)
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"

    # Step 1: In Essential mode, modify shadow, rim light, noise style, noise intensity, and variant count
    ess_shadow = next((s for s in test_app.slider if f"{prefix}:finish_ess_drop_shadow:{set_id}" in s.key), None)
    assert ess_shadow is not None
    ess_shadow.set_value(6).run(timeout=30)
    assert not test_app.exception

    ess_rim = next((c for c in test_app.checkbox if f"{prefix}:finish_ess_rim_light:{set_id}" in c.key), None)
    assert ess_rim is not None
    ess_rim.check().run(timeout=30)
    assert not test_app.exception

    ess_noise = next((sb for sb in test_app.selectbox if f"{prefix}:finish_ess_noise_style:{set_id}" in sb.key), None)
    assert ess_noise is not None
    ess_noise.set_value("simplex").run(timeout=30)
    assert not test_app.exception

    ess_intensity = next((s for s in test_app.slider if f"{prefix}:finish_ess_noise_intensity:{set_id}" in s.key), None)
    assert ess_intensity is not None
    ess_intensity.set_value(70).run(timeout=30)
    assert not test_app.exception

    ess_variants = next((s for s in test_app.select_slider if f"{prefix}:finish_ess_variants:{set_id}" in s.key), None)
    assert ess_variants is not None
    ess_variants.set_value(4).run(timeout=30)
    assert not test_app.exception

    # Step 2: Switch to Advanced mode and verify that all changed values are reflected
    mode_radio = next((r for r in test_app.radio if f"{prefix}:finish_ctrl_mode:{set_id}" in r.key), None)
    assert mode_radio is not None
    mode_radio.set_value("🎛️ Avanzado (Control Total)").run(timeout=30)
    assert not test_app.exception

    adv_shadow = next((s for s in test_app.slider if f"{prefix}:finish_drop_shadow:{set_id}" in s.key), None)
    assert adv_shadow is not None
    assert adv_shadow.value == 6

    adv_rim = next((c for c in test_app.checkbox if f"{prefix}:finish_rim_light:{set_id}" in c.key), None)
    assert adv_rim is not None
    assert adv_rim.value is True

    adv_noise = next((sb for sb in test_app.selectbox if f"{prefix}:finish_noise_style:{set_id}" in sb.key), None)
    assert adv_noise is not None
    assert adv_noise.value == "simplex"

    adv_intensity = next((s for s in test_app.slider if f"{prefix}:finish_noise_intensity:{set_id}" in s.key), None)
    assert adv_intensity is not None
    assert adv_intensity.value == 70

    adv_variants = next((s for s in test_app.select_slider if f"{prefix}:finish_variant_count:{set_id}" in s.key), None)
    assert adv_variants is not None
    assert adv_variants.value == 4

    # Step 3: Now in Advanced mode, modify them to new values
    adv_shadow.set_value(1).run(timeout=30)
    assert not test_app.exception

    adv_rim = next((c for c in test_app.checkbox if f"{prefix}:finish_rim_light:{set_id}" in c.key), None)
    assert adv_rim is not None
    adv_rim.uncheck().run(timeout=30)
    assert not test_app.exception

    adv_noise = next((sb for sb in test_app.selectbox if f"{prefix}:finish_noise_style:{set_id}" in sb.key), None)
    assert adv_noise is not None
    adv_noise.set_value("gravel").run(timeout=30)
    assert not test_app.exception

    adv_intensity = next((s for s in test_app.slider if f"{prefix}:finish_noise_intensity:{set_id}" in s.key), None)
    assert adv_intensity is not None
    adv_intensity.set_value(45).run(timeout=30)
    assert not test_app.exception

    adv_variants = next((s for s in test_app.select_slider if f"{prefix}:finish_variant_count:{set_id}" in s.key), None)
    assert adv_variants is not None
    adv_variants.set_value(2).run(timeout=30)
    assert not test_app.exception

    # Step 4: Switch back to Essential mode and verify all new values synced
    mode_radio = next((r for r in test_app.radio if f"{prefix}:finish_ctrl_mode:{set_id}" in r.key), None)
    assert mode_radio is not None
    mode_radio.set_value("⚡ Esencial (Guiado)").run(timeout=30)
    assert not test_app.exception

    ess_shadow_2 = next((s for s in test_app.slider if f"{prefix}:finish_ess_drop_shadow:{set_id}" in s.key), None)
    assert ess_shadow_2 is not None
    assert ess_shadow_2.value == 1

    ess_rim_2 = next((c for c in test_app.checkbox if f"{prefix}:finish_ess_rim_light:{set_id}" in c.key), None)
    assert ess_rim_2 is not None
    assert ess_rim_2.value is False

    ess_noise_2 = next((sb for sb in test_app.selectbox if f"{prefix}:finish_ess_noise_style:{set_id}" in sb.key), None)
    assert ess_noise_2 is not None
    assert ess_noise_2.value == "gravel"

    ess_intensity_2 = next((s for s in test_app.slider if f"{prefix}:finish_ess_noise_intensity:{set_id}" in s.key), None)
    assert ess_intensity_2 is not None
    assert ess_intensity_2.value == 45

    ess_variants_2 = next((s for s in test_app.select_slider if f"{prefix}:finish_ess_variants:{set_id}" in s.key), None)
    assert ess_variants_2 is not None
    assert ess_variants_2.value == 2


def test_adversarial_reroll_seed_synchronization() -> None:
    """Adversarial test: Re-rolling seed in Essential updates project and displays in Advanced."""
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_id = _setup_tileset_session(test_app)
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"
    reroll_btn = next((b for b in test_app.button if f"{prefix}:finish_ess_reroll:{set_id}" in b.key), None)
    assert reroll_btn is not None
    reroll_btn.click().run(timeout=30)
    assert not test_app.exception

    project = test_app.session_state[f"{prefix}:set_view_project"]
    new_seed = project["sets"][0].get("edgeSeed")
    assert isinstance(new_seed, int)
    assert new_seed > 0

    # Switch to Advanced
    mode_radio = next((r for r in test_app.radio if f"{prefix}:finish_ctrl_mode:{set_id}" in r.key), None)
    assert mode_radio is not None
    mode_radio.set_value("🎛️ Avanzado (Control Total)").run(timeout=30)
    assert not test_app.exception

    adv_seed = next((ni for ni in test_app.number_input if f"{prefix}:finish_edge_seed:{set_id}" in ni.key), None)
    assert adv_seed is not None
    assert adv_seed.value == new_seed


def test_adversarial_preset_application_in_both_modes() -> None:
    """Adversarial test: Applying presets in Essential, then Advanced, then switching back."""
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_id = _setup_tileset_session(test_app)
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"

    # Step 1: Apply zelda_topdown in Essential mode
    preset_sel = next((sb for sb in test_app.selectbox if f"{prefix}:finish_preset_picker:{set_id}" in sb.key), None)
    assert preset_sel is not None
    preset_sel.set_value("zelda_topdown").run(timeout=30)
    assert not test_app.exception

    apply_btn = next((b for b in test_app.button if f"{prefix}:finish_apply_preset:{set_id}" in b.key), None)
    assert apply_btn is not None
    apply_btn.click().run(timeout=30)
    assert not test_app.exception

    # Verify Essential controls
    ess_shadow = next((s for s in test_app.slider if f"{prefix}:finish_ess_drop_shadow:{set_id}" in s.key), None)
    assert ess_shadow is not None
    assert ess_shadow.value == 2

    ess_rim = next((c for c in test_app.checkbox if f"{prefix}:finish_ess_rim_light:{set_id}" in c.key), None)
    assert ess_rim is not None
    assert ess_rim.value is True

    # Step 2: Switch to Advanced mode
    mode_radio = next((r for r in test_app.radio if f"{prefix}:finish_ctrl_mode:{set_id}" in r.key), None)
    assert mode_radio is not None
    mode_radio.set_value("🎛️ Avanzado (Control Total)").run(timeout=30)
    assert not test_app.exception

    adv_shadow = next((s for s in test_app.slider if f"{prefix}:finish_drop_shadow:{set_id}" in s.key), None)
    assert adv_shadow is not None
    assert adv_shadow.value == 2

    # Step 3: In Advanced mode, apply retro_16bit preset
    preset_sel_adv = next((sb for sb in test_app.selectbox if f"{prefix}:finish_preset_picker:{set_id}" in sb.key), None)
    assert preset_sel_adv is not None
    preset_sel_adv.set_value("retro_16bit").run(timeout=30)
    assert not test_app.exception

    apply_btn_adv = next((b for b in test_app.button if f"{prefix}:finish_apply_preset:{set_id}" in b.key), None)
    assert apply_btn_adv is not None
    apply_btn_adv.click().run(timeout=30)
    assert not test_app.exception

    # In Advanced, retro_16bit sets dropShadow=3, retroOutline=True
    adv_shadow_2 = next((s for s in test_app.slider if f"{prefix}:finish_drop_shadow:{set_id}" in s.key), None)
    assert adv_shadow_2 is not None
    assert adv_shadow_2.value == 3

    adv_outline = next((c for c in test_app.checkbox if f"{prefix}:finish_retro_outline:{set_id}" in c.key), None)
    assert adv_outline is not None
    assert adv_outline.value is True

    # Step 4: Switch back to Essential mode and verify immediate consistency
    mode_radio = next((r for r in test_app.radio if f"{prefix}:finish_ctrl_mode:{set_id}" in r.key), None)
    assert mode_radio is not None
    mode_radio.set_value("⚡ Esencial (Guiado)").run(timeout=30)
    assert not test_app.exception

    ess_shadow_3 = next((s for s in test_app.slider if f"{prefix}:finish_ess_drop_shadow:{set_id}" in s.key), None)
    assert ess_shadow_3 is not None
    assert ess_shadow_3.value == 3


def test_adversarial_multi_set_suite_isolation_and_color_sync() -> None:
    """Adversarial test: Multi-set suite (Blob 47, Dual Grid 15, Wang 16) with color synchronization."""
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_ids = _setup_multi_set_tileset_session(test_app)
    assert len(set_ids) == 3
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"
    active_set_id = set_ids[0]

    # Verify set selector dropdown contains all 3 sets
    set_sel = next((sb for sb in test_app.selectbox if f"{prefix}:finishing_set_select" in sb.key), None)
    assert set_sel is not None
    assert len(set_sel.options) == 3

    # Check color synchronization checkbox
    sync_cb = next((c for c in test_app.checkbox if f"{prefix}:finish_sync_colors:{active_set_id}" in c.key), None)
    assert sync_cb is not None
    assert sync_cb.value is True

    # Modify primary color on set 1 via hex input
    hex_input = next((ti for ti in test_app.text_input if f"{prefix}:finish_primary:{active_set_id}:hex" in ti.key), None)
    assert hex_input is not None
    hex_input.set_value("#1E88E5").run(timeout=30)
    assert not test_app.exception

    # Verify in session_state project that all 3 sets received #1E88E5
    project = test_app.session_state[f"{prefix}:set_view_project"]
    for s in project["sets"]:
        assert s["primaryColor"] == "#1E88E5"

    # Switch active set to set 2 (Dual Grid 15)
    set_sel = next((sb for sb in test_app.selectbox if f"{prefix}:finishing_set_select" in sb.key), None)
    assert set_sel is not None
    set_sel.set_value(set_ids[1]).run(timeout=30)
    assert not test_app.exception

    project = test_app.session_state[f"{prefix}:set_view_project"]
    assert project["activeSetId"] == set_ids[1]

    # In set 2, uncheck sync colors
    sync_cb_2 = next((c for c in test_app.checkbox if f"{prefix}:finish_sync_colors:{set_ids[1]}" in c.key), None)
    assert sync_cb_2 is not None
    sync_cb_2.uncheck().run(timeout=30)
    assert not test_app.exception

    # Change set 2 primary color to #FF5722
    hex_input_2 = next((ti for ti in test_app.text_input if f"{prefix}:finish_primary:{set_ids[1]}:hex" in ti.key), None)
    assert hex_input_2 is not None
    hex_input_2.set_value("#FF5722").run(timeout=30)
    assert not test_app.exception

    project = test_app.session_state[f"{prefix}:set_view_project"]
    # Only set 2 should have #FF5722; set 1 and set 3 must stay #1E88E5
    set_dict = {s["id"]: s for s in project["sets"]}
    assert set_dict[set_ids[1]]["primaryColor"] == "#FF5722"
    assert set_dict[set_ids[0]]["primaryColor"] == "#1E88E5"
    assert set_dict[set_ids[2]]["primaryColor"] == "#1E88E5"


def test_adversarial_multi_set_apply_to_all_presets() -> None:
    """Adversarial test: '🔄 A Todos' applies preset to all sets in suite and clears all cached states."""
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_ids = _setup_multi_set_tileset_session(test_app)
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"
    active_set_id = set_ids[0]

    # Select preset retro_16bit
    preset_sel = next((sb for sb in test_app.selectbox if f"{prefix}:finish_preset_picker:{active_set_id}" in sb.key), None)
    assert preset_sel is not None
    preset_sel.set_value("retro_16bit").run(timeout=30)
    assert not test_app.exception

    # Click '🔄 A Todos'
    apply_all_btn = next((b for b in test_app.button if f"{prefix}:finish_apply_all_preset:{active_set_id}" in b.key), None)
    assert apply_all_btn is not None
    apply_all_btn.click().run(timeout=30)
    assert not test_app.exception

    # Verify all 3 sets received retro_16bit
    project = test_app.session_state[f"{prefix}:set_view_project"]
    for s in project["sets"]:
        assert s["aestheticPreset"] == "retro_16bit"
        assert s["dropShadow"] == 3
        assert s["retroOutline"] is True

    # Switch to set 3 and verify its Essential shadow slider is 3
    set_sel = next((sb for sb in test_app.selectbox if f"{prefix}:finishing_set_select" in sb.key), None)
    assert set_sel is not None
    set_sel.set_value(set_ids[2]).run(timeout=30)
    assert not test_app.exception

    ess_shadow_3 = next((s for s in test_app.slider if f"{prefix}:finish_ess_drop_shadow:{set_ids[2]}" in s.key), None)
    assert ess_shadow_3 is not None
    assert ess_shadow_3.value == 3


def test_adversarial_export_bundles_and_omnibundle_integrity() -> None:
    """Adversarial test: Verify single-set engine bundles and multi-set Omnibundle ZIP integrity."""
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    set_ids = _setup_multi_set_tileset_session(test_app)
    test_app.run(timeout=30)
    assert not test_app.exception

    prefix = "tileset_builder:patterns"

    # Verify export buttons are present in UI
    assert any(f"{prefix}:finish_download_godot" in b.key for b in test_app.download_button)
    assert any(f"{prefix}:finish_download_unity" in b.key for b in test_app.download_button)
    assert any(f"{prefix}:finish_download_tiled" in b.key for b in test_app.download_button)
    assert any(f"{prefix}:finish_download_png" in b.key for b in test_app.download_button)
    assert any(f"{prefix}:finish_download_bitmask" in b.key for b in test_app.download_button)
    assert any(f"{prefix}:finish_download_project" in b.key for b in test_app.download_button)
    assert any(f"{prefix}:finish_download_omnibundle" in b.key for b in test_app.download_button)

    # Test Omnibundle package generation directly with generated suite
    from sprite_builder.tilesets.suite import generate_terrain_suite
    suite = generate_terrain_suite(
        name="Bosque Encantado",
        primary_color="#2E7D32",
        secondary_color="#4E342E",
        kinds=("blob_47", "dual_grid_15", "wang_16"),
        tile_size=(16, 16),
    )

    suite_set_results = {str(s["id"]): suite.results_by_kind[s["kind"]] for s in suite.project_sets}
    zip_bytes = _build_multi_set_omnibundle_zip(
        project_name="Bosque Encantado",
        sets=suite.project_sets,
        set_results=suite_set_results,
        tile_size=(16, 16),
    )
    assert len(zip_bytes) > 1000

    # Unpack Omnibundle and assert full structure and integrity
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        namelist = zf.namelist()
        assert "README.md" in namelist
        readme_text = zf.read("README.md").decode("utf-8")
        assert "Bosque Encantado" in readme_text
        assert "Total de Sets Incluidos: 3" in readme_text

        # Check subfolders for all 3 sets
        for idx, kind in enumerate(["blob_47", "dual_grid_15", "wang_16"]):
            prefix_folder = f"{idx+1:02d}_{kind}_"
            matched_folder = next((name.split("/")[0] for name in namelist if name.startswith(prefix_folder)), None)
            assert matched_folder is not None, f"Expected folder starting with {prefix_folder}"

            assert f"{matched_folder}/terrain_tiles.png" in namelist
            assert f"{matched_folder}/terrain_bitmask_reference.png" in namelist
            assert f"{matched_folder}/godot_installer.zip" in namelist
            assert f"{matched_folder}/unity_ruletile.zip" in namelist
            assert f"{matched_folder}/tiled_wangset.zip" in namelist

            # Verify nested Godot zip
            godot_data = zf.read(f"{matched_folder}/godot_installer.zip")
            with zipfile.ZipFile(io.BytesIO(godot_data), "r") as inner_gz:
                inner_names = inner_gz.namelist()
                assert any("install_terrain_tileset.gd" in n for n in inner_names)
                assert any("terrain_pattern.json" in n for n in inner_names)

            # Verify nested Unity zip
            unity_data = zf.read(f"{matched_folder}/unity_ruletile.zip")
            with zipfile.ZipFile(io.BytesIO(unity_data), "r") as inner_uz:
                inner_names = inner_uz.namelist()
                assert any(n.endswith("RuleTile.cs") for n in inner_names)
                assert any("RuleTileConfig.json" in n for n in inner_names)

            # Verify nested Tiled zip
            tiled_data = zf.read(f"{matched_folder}/tiled_wangset.zip")
            with zipfile.ZipFile(io.BytesIO(tiled_data), "r") as inner_tz:
                inner_names = inner_tz.namelist()
                assert any(n.endswith(".tsx") for n in inner_names)


def test_adversarial_starter_biome_creation_when_empty() -> None:
    """Adversarial test: When project has no sets, starter biome button initializes 3 sets cleanly."""
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    prefix = "tileset_builder:patterns"
    project_key = f"{prefix}:set_view_project"

    # Start with empty sets
    test_app.session_state[project_key] = {"version": 3, "sets": [], "sources": []}
    test_app.session_state["tileset_builder:tile_size"] = 16
    test_app.run(timeout=30)
    assert not test_app.exception

    # Button to create starter biome should be visible
    start_btn = next((b for b in test_app.button if f"{prefix}:finish_create_starter_biome" in b.key), None)
    assert start_btn is not None

    # Click starter biome button
    start_btn.click().run(timeout=30)
    assert not test_app.exception

    # Verify project now has sets and sources
    project = test_app.session_state[project_key]
    assert len(project["sets"]) == 3
    assert len(project["sources"]) == 2
    assert project["activeSetId"] == project["sets"][0]["id"]

    # Verify finishing studio controls are now rendered
    mode_radio = next((r for r in test_app.radio if f"{prefix}:finish_ctrl_mode" in r.key), None)
    assert mode_radio is not None
    assert mode_radio.value == "⚡ Esencial (Guiado)"
