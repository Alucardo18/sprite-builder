"""Small, deterministic performance probes for the three UI component flows.

This module intentionally measures the Python-to-component bridge rather than the
browser.  It is useful for Phase 0 because it has no network dependency, does not
start Streamlit, and does not modify the application or accepted assets.  The
payloads are representative fixtures, not production data:

* ``sheet-studio`` renders the background/segmentation editor payload.
* ``tileset-builder`` renders the atlas editor and Pattern Studio payloads.
* ``pixel-editor`` renders a layered animation-editing payload.

Cold samples clear the image data-URI cache and create fresh PIL images.  Rerun
samples create fresh PIL images with the same pixels, which exercises the shared
cache as an app rerun would when a session reloads the source image.  The optional
soak reports ``tracemalloc`` numbers; it is deliberately observational and does
not enforce a machine-specific memory threshold.
"""

from __future__ import annotations

import gc
import json
import statistics
import time
import tracemalloc
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw

from sprite_builder.ui import components


@dataclass(frozen=True)
class _BridgeCase:
    name: str
    build: Callable[[], Callable[[], None]]


class _ComponentProbe:
    """Capture bridge invocations without mounting a browser component."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.image_uri_calls = 0
        self.cache_lookup_calls = 0
        self.cache_hits = 0
        self.cache_misses = 0

    def fake(self, component_name: str) -> Callable[..., None]:
        def invoke(**props: Any) -> None:
            self.calls.append({"component": component_name, "props": props})

        return invoke


@contextmanager
def _component_probe() -> Iterator[_ComponentProbe]:
    probe = _ComponentProbe()
    originals = {
        "_PIXEL_EDITOR": components._PIXEL_EDITOR,
        "_TILESET_EDITOR": components._TILESET_EDITOR,
        "_TERRAIN_PATTERN_STUDIO": components._TERRAIN_PATTERN_STUDIO,
        "image_data_uri": components.image_data_uri,
    }
    image_cache = getattr(components, "_IMAGE_DATA_URI_CACHE", None)
    original_cache_get = getattr(image_cache, "get", None)
    try:
        def counted_image_data_uri(image: Image.Image) -> str:
            probe.image_uri_calls += 1
            return originals["image_data_uri"](image)

        def counted_cache_get(key: object) -> str | None:
            value = original_cache_get(key)
            probe.cache_lookup_calls += 1
            if value is None:
                probe.cache_misses += 1
            else:
                probe.cache_hits += 1
            return value

        components._PIXEL_EDITOR = probe.fake("pixel-editor")
        components._TILESET_EDITOR = probe.fake("tileset-editor")
        components._TERRAIN_PATTERN_STUDIO = probe.fake("terrain-pattern-studio")
        components.image_data_uri = counted_image_data_uri
        if callable(original_cache_get):
            image_cache.get = counted_cache_get
        yield probe
    finally:
        components._PIXEL_EDITOR = originals["_PIXEL_EDITOR"]
        components._TILESET_EDITOR = originals["_TILESET_EDITOR"]
        components._TERRAIN_PATTERN_STUDIO = originals["_TERRAIN_PATTERN_STUDIO"]
        components.image_data_uri = originals["image_data_uri"]
        if callable(original_cache_get):
            image_cache.get = original_cache_get


def _image(size: tuple[int, int], seed: int) -> Image.Image:
    """Create a stable, small RGBA fixture with enough variation to encode."""

    width, height = size
    base = ((seed * 37) % 180 + 24, (seed * 53) % 180 + 24, (seed * 71) % 180 + 24, 255)
    image = Image.new("RGBA", size, base)
    draw = ImageDraw.Draw(image)
    step = max(2, min(width, height) // 8)
    for index, x in enumerate(range(0, width, step)):
        color = (
            (base[0] + index * 17) % 240,
            (base[1] + index * 13) % 240,
            (base[2] + index * 11) % 240,
            255,
        )
        draw.rectangle(
            (x, (index * step) % height, min(width - 1, x + step - 1), height - 1),
            fill=color,
        )
    draw.line((0, 0, width - 1, height - 1), fill=(250, 220, 120, 255), width=1)
    return image


def _blob_roles() -> list[dict[str, Any]]:
    return [
        {
            "index": mask,
            "mask": mask,
            "neighbors": [],
            "sourceIndex": 0 if mask == 0 else 1,
            "previewColumn": mask % 11,
            "previewRow": mask // 11,
            "setColumn": mask % 11,
            "setRow": mask // 11,
        }
        for mask in range(47)
    ]


def _pattern_project() -> dict[str, Any]:
    return {
        "version": 3,
        "kind": "tilesetter_set_project",
        "sources": [
            {"id": "terrain-a", "name": "Base", "x": 0, "y": 0, "width": 16, "height": 16},
            {"id": "terrain-b", "name": "Fondo", "x": 16, "y": 0, "width": 16, "height": 16},
        ],
        "tiles": [
            {"id": "tile-a", "sourceId": "terrain-a", "x": 0, "y": 0},
            {"id": "tile-b", "sourceId": "terrain-b", "x": 1, "y": 0},
        ],
        "sets": [
            {
                "id": "blob-baseline",
                "name": "Baseline Blob",
                "kind": "blob_47",
                "baseSource": "terrain-a",
                "secondarySource": "terrain-b",
                "primaryColor": "#48A832",
                "secondaryColor": "#2B65EC",
                "terrainProfile": "organic_neutral",
                "edgeVariation": 1,
            }
        ],
        "activeSetId": "blob-baseline",
    }


def _build_sheet_studio() -> Callable[[], None]:
    image = _image((128, 128), 11)
    overlay = _image((128, 128), 12)

    def render() -> None:
        components.pixel_editor(
            image,
            overlay=overlay,
            sample=(24, 32, 40, 255),
            paint_color=(0, 0, 0, 0),
            tool="wand",
            mode="background",
            brush_radius=3,
            wand_tolerance=18,
            wand_contiguous=True,
            zoom=6.0,
            show_guides=True,
            show_frame_guide=True,
            show_column_guides=True,
            show_row_guides=True,
            grid_columns=4,
            grid_rows=4,
            fit_on_load=True,
            fit_token="sheet-baseline-v1",
            frame_token="sheet-baseline:128x128:16",
            cut_positions=(0, 32, 64, 96, 128),
            allow_cut_drag=True,
            frame_count=16,
            frame_locks=[False] * 16,
            selected_frames=[0],
            can_undo=True,
            undo_label="Pincel",
            palette_colors=["#18212B", "#48A832", "#E6B35A"],
            key="phase0:sheet-studio",
        )

    return render


def _build_tileset_builder() -> Callable[[], None]:
    atlas = _image((192, 128), 21)
    pattern = _image((176, 80), 22)
    preview = _image((176, 80), 23)
    roles = _blob_roles()
    project = _pattern_project()

    def render() -> None:
        components.tileset_editor(
            atlas,
            image_token="phase0-atlas-v1",
            tile_size=16,
            offset_x=0,
            offset_y=0,
            spacing_x=0,
            spacing_y=0,
            key="phase0:tileset-atlas",
        )
        components.terrain_pattern_studio(
            atlas,
            pattern_image=pattern,
            image_token="phase0-atlas-v1",
            tile_size=(16, 16),
            offset=(0, 0),
            spacing=(0, 0),
            kind="blob_47",
            roles=roles,
            project=project,
            set_previews=[
                {"id": "blob-baseline", "kind": "blob_47", "image": preview, "roles": roles}
            ],
            key="phase0:tileset-patterns",
        )

    return render


def _build_pixel_editor() -> Callable[[], None]:
    image = _image((64, 64), 31)
    overlay = _image((64, 64), 32)
    move_base = _image((64, 64), 33)
    animation_frames = tuple(_image((64, 64), 34 + index) for index in range(4))

    def render() -> None:
        components.pixel_editor(
            image,
            overlay=overlay,
            move_base=move_base,
            sample=(40, 60, 80, 255),
            paint_color=(220, 160, 90, 255),
            tool="pencil",
            mode="layer",
            brush_radius=2,
            zoom=10.0,
            offset_x=2,
            offset_y=-1,
            home_offset_x=0,
            home_offset_y=0,
            show_guides=True,
            show_pixel_grid=True,
            pixel_grid_size=16,
            show_cell_center=True,
            show_frame_guide=True,
            show_column_guides=True,
            show_row_guides=True,
            grid_columns=2,
            grid_rows=2,
            current_anchor_x=31.0,
            current_anchor_y=54.0,
            target_anchor_x=32.0,
            target_anchor_y=54.0,
            show_anchor_delta=True,
            allow_drag=True,
            show_autocenter=True,
            show_autocenter_all=True,
            show_autocrop=True,
            fit_on_load=False,
            fit_token="pixel-baseline-v1",
            frame_token="pixel-baseline:64x64:4",
            studio_layers=[
                {"id": "base", "name": "Base", "visible": True, "opacity": 1.0},
                {"id": "ink", "name": "Ink", "visible": True, "opacity": 0.9},
            ],
            active_layer_id="ink",
            active_frame=1,
            frame_count=4,
            frame_locks=[False, True, False, False],
            selected_frames=[1, 2],
            floating_selection=overlay,
            floating_highlight=move_base,
            floating_selection_x=3,
            floating_selection_y=4,
            floating_selection_bounds=(3, 4, 20, 20),
            floating_operation_kind="move_mask",
            can_undo=True,
            can_redo=True,
            undo_label="Mover selección",
            redo_label="Pegar selección",
            animation_frames=animation_frames,
            animation_fps=8,
            animation_durations=[120, 120, 160, 120],
            palette_colors=["#18212B", "#E6B35A", "#48A832", "#F4E6C1"],
            key="phase0:pixel-editor",
        )

    return render


def _cases() -> tuple[_BridgeCase, ...]:
    return (
        _BridgeCase("sheet-studio", _build_sheet_studio),
        _BridgeCase("tileset-builder", _build_tileset_builder),
        _BridgeCase("pixel-editor", _build_pixel_editor),
    )


def _clear_image_cache() -> None:
    cache_clear = getattr(components._image_data_uri_cached, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()
    cache = getattr(components, "_IMAGE_DATA_URI_CACHE", None)
    clear = getattr(cache, "clear", None)
    if callable(clear):
        clear()


def _cache_info() -> dict[str, int]:
    info: dict[str, int] = {
        "hits": 0,
        "misses": 0,
        "maxsize": 0,
        "currsize": 0,
        "entries": 0,
        "bytes": 0,
        "max_bytes": 0,
    }
    cache_info = getattr(components._image_data_uri_cached, "cache_info", None)
    if callable(cache_info):
        cached = cache_info()
        info.update(
            {
                "hits": int(cached.hits),
                "misses": int(cached.misses),
                "maxsize": int(cached.maxsize or 0),
                "currsize": int(cached.currsize),
            }
        )
    budget_cache = getattr(components, "_IMAGE_DATA_URI_CACHE", None)
    budget_info = getattr(budget_cache, "info", None)
    if callable(budget_info):
        info.update({key: int(value) for key, value in budget_info().items()})
    return info


def _cache_delta(before: Mapping[str, int], after: Mapping[str, int]) -> dict[str, int]:
    return {
        "hits": int(after.get("hits", 0) - before.get("hits", 0)),
        "misses": int(after.get("misses", 0) - before.get("misses", 0)),
        "entries": int(
            after.get("entries", after.get("currsize", 0))
            - before.get("entries", before.get("currsize", 0))
        ),
        "bytes": int(after.get("bytes", 0) - before.get("bytes", 0)),
    }


def _props_bytes(calls: Iterable[Mapping[str, Any]]) -> tuple[int, dict[str, int]]:
    by_component: dict[str, int] = {}
    for call in calls:
        component = str(call["component"])
        props = call["props"]
        encoded = json.dumps(
            props,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        by_component[component] = by_component.get(component, 0) + len(encoded)
    return sum(by_component.values()), by_component


def _memory_soak(
    builder: Callable[[], Callable[[], None]],
    probe: _ComponentProbe,
    runs: int,
) -> dict[str, int] | None:
    if runs <= 0:
        return None
    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()
    gc.collect()
    start_current, start_peak = tracemalloc.get_traced_memory()
    try:
        for _ in range(runs):
            render = builder()
            probe.calls.clear()
            render()
            del render
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        return {
            "runs": int(runs),
            "start_current_bytes": int(start_current),
            "end_current_bytes": int(current),
            "peak_bytes": int(peak),
            "growth_bytes": int(current - start_current),
            "component_calls": int(len(probe.calls)),
        }
    finally:
        if not was_tracing:
            tracemalloc.stop()


def _timed_render(
    builder: Callable[[], Callable[[], None]], probe: _ComponentProbe
) -> dict[str, Any]:
    render = builder()
    probe.calls.clear()
    probe.image_uri_calls = 0
    probe.cache_lookup_calls = 0
    probe.cache_hits = 0
    probe.cache_misses = 0
    cache_before = _cache_info()
    started = time.perf_counter()
    render()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    cache_after = _cache_info()
    props_total, props_by_component = _props_bytes(probe.calls)
    return {
        "elapsed_ms": elapsed_ms,
        "component_calls": len(probe.calls),
        "image_uri_calls": probe.image_uri_calls,
        "cache_lookup_calls": probe.cache_lookup_calls,
        "cache_hits": probe.cache_hits,
        "cache_misses": probe.cache_misses,
        "props_bytes": props_total,
        "props_bytes_by_component": props_by_component,
        "cache_delta": _cache_delta(cache_before, cache_after),
    }


def run_baseline(*, rerun_count: int = 5, soak_runs: int = 0) -> dict[str, Any]:
    """Measure the bounded Phase 0 bridge baseline and return JSON-safe data."""

    rerun_count = max(0, int(rerun_count))
    soak_runs = max(0, int(soak_runs))
    case_results: list[dict[str, Any]] = []

    with _component_probe() as probe:
        for case in _cases():
            _clear_image_cache()
            cold = _timed_render(case.build, probe)
            reruns: list[dict[str, Any]] = []
            for _ in range(rerun_count):
                reruns.append(_timed_render(case.build, probe))
            rerun_times = [float(sample["elapsed_ms"]) for sample in reruns]
            soak = _memory_soak(case.build, probe, soak_runs)
            case_results.append(
                {
                    "name": case.name,
                    "cold": cold,
                    "rerun": {
                        "count": rerun_count,
                        "samples_ms": rerun_times,
                        "median_ms": statistics.median(rerun_times) if rerun_times else None,
                        "min_ms": min(rerun_times) if rerun_times else None,
                        "max_ms": max(rerun_times) if rerun_times else None,
                        "component_calls": [int(sample["component_calls"]) for sample in reruns],
                        "image_uri_calls": [int(sample["image_uri_calls"]) for sample in reruns],
                        "cache_lookup_calls": [
                            int(sample["cache_lookup_calls"]) for sample in reruns
                        ],
                        "cache_hits": [int(sample["cache_hits"]) for sample in reruns],
                        "cache_misses": [int(sample["cache_misses"]) for sample in reruns],
                        "props_bytes": [int(sample["props_bytes"]) for sample in reruns],
                        "cache_delta": [sample["cache_delta"] for sample in reruns],
                    },
                    "soak": soak,
                }
            )

    return {
        "schema_version": "phase0.ui-baseline.v1",
        "scope": {
            "measurement": "python component bridge",
            "flows": [case["name"] for case in case_results],
            "network": False,
            "browser": False,
            "image_generation": False,
            "rerun_count": rerun_count,
            "soak_runs": soak_runs,
        },
        "cases": case_results,
    }


__all__ = ["run_baseline"]
