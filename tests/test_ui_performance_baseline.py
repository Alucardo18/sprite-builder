"""Focused contracts for the Phase 0 UI performance baseline."""

from __future__ import annotations

from sprite_builder.ui import components
from sprite_builder.ui.performance_baseline import run_baseline


def test_baseline_covers_representative_flows_and_bridge_metrics() -> None:
    baseline = run_baseline(rerun_count=2)

    assert baseline["schema_version"] == "phase0.ui-baseline.v1"
    assert baseline["scope"]["flows"] == ["sheet-studio", "tileset-builder", "pixel-editor"]

    for case in baseline["cases"]:
        cold = case["cold"]
        rerun = case["rerun"]
        assert cold["elapsed_ms"] > 0
        assert cold["component_calls"] >= 1
        assert cold["image_uri_calls"] >= cold["component_calls"]
        assert cold["props_bytes"] > 0
        assert cold["props_bytes_by_component"]
        assert rerun["count"] == 2
        assert len(rerun["samples_ms"]) == 2
        assert all(sample > 0 for sample in rerun["samples_ms"])
        assert rerun["component_calls"] == [cold["component_calls"]] * 2
        assert all(count == cold["image_uri_calls"] for count in rerun["image_uri_calls"])
        assert rerun["props_bytes"] == [cold["props_bytes"]] * 2


def test_baseline_restores_component_declarations() -> None:
    originals = (
        components._PIXEL_EDITOR,
        components._TILESET_EDITOR,
        components._TERRAIN_PATTERN_STUDIO,
    )

    run_baseline(rerun_count=0)

    assert originals == (
        components._PIXEL_EDITOR,
        components._TILESET_EDITOR,
        components._TERRAIN_PATTERN_STUDIO,
    )


def test_optional_soak_is_observational_and_json_safe() -> None:
    baseline = run_baseline(rerun_count=0, soak_runs=2)

    for case in baseline["cases"]:
        soak = case["soak"]
        assert soak is not None
        assert soak["runs"] == 2
        assert soak["peak_bytes"] >= soak["end_current_bytes"]
        assert soak["component_calls"] >= 1
