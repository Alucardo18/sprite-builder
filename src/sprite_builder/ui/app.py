"""Apple-glass, pixel-perfect local editor for existing sprite sheets."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import streamlit as st
from PIL import Image

from sprite_builder.domain.errors import ArtifactIntegrityError
from sprite_builder.sheets import (
    AutoCenterConfig,
    BackgroundRemovalConfig,
    CenteringResult,
    FrameAdjustment,
    ExportCropResult,
    SegmentationConfig,
    SheetSessionStore,
    apply_background_removal,
    apply_manual_background_edits,
    auto_center_frames,
    combine_selection_masks,
    encode_mask,
    render_contact_sheet,
    render_frame_overlay,
    render_selection_overlay,
    render_segmentation_guides,
    render_segmentation_preview,
    resolve_segmentation_config,
    sample_pixel,
    select_similar_pixels,
    segment_sheet,
    trim_transparent_frames,
)
from sprite_builder.sheets.models import ExportCropConfig
from sprite_builder.ui.components import pixel_editor, pixel_image_html, status_badge


def _workspace() -> Path:
    return Path(os.environ.get("SPRITE_BUILDER_WORKSPACE", ".")).expanduser().resolve()


def _load_css() -> None:
    css = (Path(__file__).parent / "assets" / "theme.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _set_editor_width_mode(enabled: bool) -> None:
    if not enabled:
        return
    st.markdown(
        """
        <style>
          [data-testid="stAppViewContainer"] > .main {
            padding-left: 1.5rem;
            padding-right: 1.5rem;
            max-width: 100%;
          }
          [data-testid="stSidebar"] {
            min-width: 20rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _rgb_to_hex(value: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in value)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _background_tool_label(tool: str) -> str:
    return {
        "wand": "Varita",
        "eraser": "Borrador",
        "eyedropper": "Cuentagotas",
    }.get(tool, "Varita")


def _normalize_background_tool(tool: Any) -> str:
    value = str(tool or "wand")
    return value if value in {"wand", "eraser", "eyedropper"} else "wand"


def _show_pixel(image: Image.Image, caption: str, *, max_height: int = 560) -> None:
    st.markdown(
        pixel_image_html(image, caption=caption, max_height=max_height),
        unsafe_allow_html=True,
    )


def _auto_cut_positions(
    source_size: tuple[int, int],
    config: SegmentationConfig,
) -> tuple[int, ...]:
    resolved, _ = resolve_segmentation_config(source_size, config)
    if resolved.frame_count < 2:
        return ()
    if resolved.orientation == "vertical":
        start = resolved.offset_y
        span = (
            int(resolved.cell_height or source_size[1]) * resolved.frame_count
            + max(0, resolved.frame_count - 1) * resolved.spacing_y
        )
    else:
        start = resolved.offset_x
        span = (
            int(resolved.cell_width or source_size[0]) * resolved.frame_count
            + max(0, resolved.frame_count - 1) * resolved.spacing_x
        )
    step = span / resolved.frame_count
    return tuple(
        int(round(start + step * index))
        for index in range(1, resolved.frame_count)
    )


def _normalized_segmentation_cut_positions(
    source_size: tuple[int, int],
    config: SegmentationConfig,
    positions: Sequence[int] | None,
) -> tuple[int, ...]:
    if config.orientation not in {"horizontal", "vertical"}:
        return ()
    desired = max(0, int(config.frame_count) - 1)
    if desired == 0:
        return ()
    raw = tuple(int(value) for value in (positions or ()))
    if len(raw) != desired:
        fallback_config = SegmentationConfig(
            frame_count=config.frame_count,
            orientation=config.orientation,
            rows=config.rows,
            columns=config.columns,
            cell_width=config.cell_width,
            cell_height=config.cell_height,
            offset_x=config.offset_x,
            offset_y=config.offset_y,
            spacing_x=config.spacing_x,
            spacing_y=config.spacing_y,
            manual_cut_positions=(),
        )
        return _auto_cut_positions(source_size, fallback_config)
    return raw


def _ensure_segmentation_cut_state(
    session: Any,
    source_size: tuple[int, int],
    config: SegmentationConfig,
) -> tuple[int, ...]:
    prefix = session.session_id
    cuts_key = f"{prefix}:segmentation_cut_positions"
    sync_key = f"{prefix}:segmentation_cut_positions_sig"
    signature = json.dumps(
        {
            "source_size": list(source_size),
            "frame_count": config.frame_count,
            "orientation": config.orientation,
            "rows": config.rows,
            "columns": config.columns,
            "cell_width": config.cell_width,
            "cell_height": config.cell_height,
            "offset_x": config.offset_x,
            "offset_y": config.offset_y,
            "spacing_x": config.spacing_x,
            "spacing_y": config.spacing_y,
            "manual_cut_positions": list(config.manual_cut_positions),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    saved = _normalized_segmentation_cut_positions(
        source_size,
        config,
        config.manual_cut_positions,
    )
    if (
        cuts_key not in st.session_state
        or st.session_state.get(sync_key) != signature
        or len(st.session_state[cuts_key]) != max(0, config.frame_count - 1)
    ):
        st.session_state[cuts_key] = list(saved)
        st.session_state[sync_key] = signature
    return tuple(int(value) for value in st.session_state[cuts_key])


def _ensure_segmentation_cut_controls_state(session: Any) -> None:
    prefix = session.session_id
    zoom_key = f"{prefix}:segmentation_cut_zoom"
    zoom_widget_key = f"{zoom_key}_widget"
    zoom_sync_key = f"{zoom_key}_widget_sync"
    free_key = f"{prefix}:segmentation_free_adjust"
    free_widget_key = f"{free_key}_widget"
    free_sync_key = f"{free_key}_widget_sync"
    if zoom_key not in st.session_state:
        st.session_state[zoom_key] = 8
    if zoom_sync_key in st.session_state:
        st.session_state[zoom_widget_key] = st.session_state.pop(zoom_sync_key)
    elif zoom_widget_key not in st.session_state:
        st.session_state[zoom_widget_key] = st.session_state[zoom_key]
    if free_key not in st.session_state:
        st.session_state[free_key] = False
    if free_sync_key in st.session_state:
        st.session_state[free_widget_key] = st.session_state.pop(free_sync_key)
    elif free_widget_key not in st.session_state:
        st.session_state[free_widget_key] = st.session_state[free_key]


def _set_auto_segmentation_cuts(
    session: Any,
    source_size: tuple[int, int],
    config: SegmentationConfig,
) -> tuple[int, ...]:
    prefix = session.session_id
    cuts = list(_auto_cut_positions(source_size, config))
    st.session_state[f"{prefix}:segmentation_cut_positions"] = cuts
    st.session_state[f"{prefix}:segmentation_cut_positions_sig"] = json.dumps(
        {
            "source_size": list(source_size),
            "frame_count": config.frame_count,
            "orientation": config.orientation,
            "rows": config.rows,
            "columns": config.columns,
            "cell_width": config.cell_width,
            "cell_height": config.cell_height,
            "offset_x": config.offset_x,
            "offset_y": config.offset_y,
            "spacing_x": config.spacing_x,
            "spacing_y": config.spacing_y,
            "manual_cut_positions": cuts,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return tuple(cuts)


def _load_stage_manifest(
    store: SheetSessionStore,
    session: Any,
    stage: str,
) -> dict[str, Any] | None:
    record = session.stages.get(stage, {})
    manifest = record.get("manifest")
    if not manifest:
        return None
    path = store.workspace / str(manifest)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _saved_manual_edit_ops(
    store: SheetSessionStore,
    session: Any,
) -> dict[int, list[dict[str, Any]]]:
    manifest = _load_stage_manifest(store, session, "background")
    if not manifest:
        return {}
    raw = manifest.get("metadata", {}).get("manual_edit_operations", {})
    if not isinstance(raw, dict):
        return {}
    output: dict[int, list[dict[str, Any]]] = {}
    for key, value in raw.items():
        if not isinstance(value, list):
            continue
        try:
            index = int(key)
        except ValueError:
            continue
        output[index] = [dict(item) for item in value if isinstance(item, dict)]
    return output


def _manual_ops_signature(
    operations_by_frame: dict[int, list[dict[str, Any]]],
) -> str:
    return json.dumps(operations_by_frame, sort_keys=True, separators=(",", ":"))


def _ensure_manual_background_state(
    store: SheetSessionStore,
    session: Any,
    count: int,
) -> None:
    prefix = session.session_id
    ops_key = f"{prefix}:background_manual_ops"
    sig_key = f"{prefix}:background_manual_ops_sig"
    saved = _saved_manual_edit_ops(store, session)
    normalized = {
        index: list(saved.get(index, []))
        for index in range(count)
        if saved.get(index)
    }
    signature = _manual_ops_signature(normalized)
    if ops_key not in st.session_state or st.session_state.get(sig_key) != signature:
        st.session_state[ops_key] = normalized
        st.session_state[sig_key] = signature


def _ensure_background_editor_state(session: Any, count: int) -> None:
    prefix = session.session_id
    tool_key = f"{prefix}:background_tool"
    tool_widget_key = f"{prefix}:background_tool_widget"
    tool_sync_key = f"{prefix}:background_tool_widget_sync"
    color_key = f"{prefix}:background_sampled_color"
    selection_key = f"{prefix}:background_selection_masks"
    zoom_key = f"{prefix}:background_zoom"
    brush_key = f"{prefix}:background_brush_radius"
    brush_widget_key = f"{prefix}:background_brush_radius_widget"
    brush_sync_key = f"{prefix}:background_brush_radius_widget_sync"
    event_key = f"{prefix}:background_last_event"
    if tool_key not in st.session_state:
        st.session_state[tool_key] = "wand"
    else:
        st.session_state[tool_key] = _normalize_background_tool(st.session_state[tool_key])
    if tool_widget_key not in st.session_state:
        st.session_state[tool_widget_key] = st.session_state[tool_key]
    if color_key not in st.session_state:
        st.session_state[color_key] = (0, 255, 0, 255)
    if selection_key not in st.session_state or len(st.session_state[selection_key]) != count:
        st.session_state[selection_key] = [None] * count
    if zoom_key not in st.session_state:
        st.session_state[zoom_key] = 8
    if brush_key not in st.session_state:
        st.session_state[brush_key] = 5
    if brush_widget_key not in st.session_state:
        st.session_state[brush_widget_key] = st.session_state[brush_key]
    if event_key not in st.session_state:
        st.session_state[event_key] = None


def _selection_mode_from_event(event: dict[str, Any]) -> str:
    if event.get("altKey"):
        return "subtract"
    if event.get("shiftKey"):
        return "add"
    if event.get("metaKey") or event.get("ctrlKey"):
        return "intersect"
    return "replace"


def _handle_background_editor_event(
    session: Any,
    frames: Sequence[Image.Image],
    selected_frame: int,
    event: dict[str, Any] | None,
    *,
    tolerance: float,
    contiguous: bool,
) -> bool:
    if not event:
        return False
    prefix = session.session_id
    event_id = event.get("eventId")
    last_event = st.session_state.get(f"{prefix}:background_last_event")
    if not event_id or event_id == last_event:
        return False
    st.session_state[f"{prefix}:background_last_event"] = event_id
    if event.get("type") == "key":
        key = str(event.get("key", "")).lower()
        if key == "i":
            st.session_state[f"{prefix}:background_tool"] = "eyedropper"
            st.session_state[f"{prefix}:background_tool_widget_sync"] = "eyedropper"
        elif key == "w":
            st.session_state[f"{prefix}:background_tool"] = "wand"
            st.session_state[f"{prefix}:background_tool_widget_sync"] = "wand"
        elif key == "e":
            st.session_state[f"{prefix}:background_tool"] = "eraser"
            st.session_state[f"{prefix}:background_tool_widget_sync"] = "eraser"
        elif key == "escape":
            selections = list(st.session_state[f"{prefix}:background_selection_masks"])
            selections[selected_frame] = None
            st.session_state[f"{prefix}:background_selection_masks"] = selections
        elif key in {"delete", "backspace"}:
            selections = list(st.session_state[f"{prefix}:background_selection_masks"])
            mask = selections[selected_frame]
            if isinstance(mask, np.ndarray) and mask.size and mask.any():
                operations = {
                    int(index): [dict(item) for item in items]
                    for index, items in st.session_state[f"{prefix}:background_manual_ops"].items()
                }
                operations.setdefault(selected_frame, []).append(
                    {
                        "kind": "erase_mask",
                        **encode_mask(mask),
                    }
                )
                selections[selected_frame] = None
                st.session_state[f"{prefix}:background_manual_ops"] = operations
                st.session_state[f"{prefix}:background_selection_masks"] = selections
        return True

    if event.get("type") == "toolbar":
        action = str(event.get("action", ""))
        if action == "tool":
            tool = _normalize_background_tool(event.get("tool", "wand"))
            st.session_state[f"{prefix}:background_tool"] = tool
            st.session_state[f"{prefix}:background_tool_widget_sync"] = tool
            return True
        if action == "brush-radius":
            brush_radius = int(
                event.get(
                    "brushRadius",
                    st.session_state.get(f"{prefix}:background_brush_radius", 5),
                )
            )
            radius = max(1, min(48, brush_radius))
            st.session_state[f"{prefix}:background_brush_radius"] = radius
            st.session_state[f"{prefix}:background_brush_radius_widget_sync"] = radius
            return True
        if action == "zoom":
            zoom = int(event.get("zoom", st.session_state.get(f"{prefix}:background_zoom", 8)))
            st.session_state[f"{prefix}:background_zoom"] = max(1, min(40, zoom))
            return True
        return False

    event_type = str(event.get("type", ""))
    if event_type not in {"pointer", "pointerdown", "pointermove"}:
        return False
    if event_type == "pointermove" and not event.get("dragging"):
        return False
    x = int(event.get("x", 0))
    y = int(event.get("y", 0))
    frame = frames[selected_frame]
    sampled = sample_pixel(frame, (x, y))
    st.session_state[f"{prefix}:background_sampled_color"] = sampled
    tool = _normalize_background_tool(event.get("tool", st.session_state[f"{prefix}:background_tool"]))
    st.session_state[f"{prefix}:background_tool"] = tool
    st.session_state[f"{prefix}:background_tool_widget_sync"] = tool
    if tool == "eyedropper":
        return True
    if tool == "eraser":
        stroke = event.get("path")
        path: tuple[tuple[int, int], ...] | None = None
        if isinstance(stroke, (list, tuple)) and stroke:
            points = [
                tuple(map(int, point))
                for point in stroke
                if isinstance(point, (list, tuple)) and len(point) == 2
            ]
            if points:
                path = tuple(points)
        operations = {
            int(index): [dict(item) for item in items]
            for index, items in st.session_state[f"{prefix}:background_manual_ops"].items()
        }
        operations.setdefault(selected_frame, []).append(
            {
                "kind": "erase_brush",
                "point": [x, y],
                "radius": int(st.session_state[f"{prefix}:background_brush_radius"]),
                **({"path": [list(point) for point in path]} if path else {}),
            }
        )
        selections = list(st.session_state[f"{prefix}:background_selection_masks"])
        selections[selected_frame] = None
        st.session_state[f"{prefix}:background_manual_ops"] = operations
        st.session_state[f"{prefix}:background_selection_masks"] = selections
        return True
    if tool != "wand":
        return False
    incoming = select_similar_pixels(
        frame,
        seed_point=(x, y),
        tolerance=tolerance,
        contiguous=contiguous,
    )
    selections = list(st.session_state[f"{prefix}:background_selection_masks"])
    current = selections[selected_frame]
    selections[selected_frame] = combine_selection_masks(
        current if isinstance(current, np.ndarray) else None,
        incoming,
        mode=_selection_mode_from_event(event),
    )
    st.session_state[f"{prefix}:background_selection_masks"] = selections
    return True


def _handle_center_editor_event(
    session: Any,
    count: int,
    selected_frame: int,
    event: dict[str, Any] | None,
    *,
    home_offset: tuple[int, int] = (0, 0),
) -> bool:
    if not event:
        return False
    prefix = session.session_id
    event_id = event.get("eventId")
    last_event = st.session_state.get(f"{prefix}:center_last_event")
    if not event_id or event_id == last_event:
        return False
    st.session_state[f"{prefix}:center_last_event"] = event_id
    if "zoom" in event:
        zoom = int(event["zoom"])
        st.session_state[f"{prefix}:center_zoom:{selected_frame}"] = max(
            1,
            min(40, zoom),
        )
    offsets = list(st.session_state.get(f"{prefix}:offsets", [(0, 0)] * count))
    if len(offsets) != count:
        offsets = [(0, 0)] * count
    if event.get("type") == "transform":
        offset_x = int(event.get("offsetX", offsets[selected_frame][0]))
        offset_y = int(event.get("offsetY", offsets[selected_frame][1]))
        offsets[selected_frame] = (offset_x - int(home_offset[0]), offset_y - int(home_offset[1]))
        st.session_state[f"{prefix}:offsets"] = offsets
        st.session_state[f"{prefix}:offset_x_widget:{selected_frame}"] = offsets[selected_frame][0]
        st.session_state[f"{prefix}:offset_y_widget:{selected_frame}"] = offsets[selected_frame][1]
        st.session_state[f"{prefix}:center_widget_sync"] = True
        return True
    if event.get("type") == "guide":
        guide = str(event.get("guide", ""))
        if guide == "ground-line":
            absolute_y = float(event.get("groundLineY", home_offset[1]))
            local_y = max(0, round(absolute_y - float(home_offset[1])))
            st.session_state[f"{prefix}:center_ground_line_y"] = local_y
            st.session_state[f"{prefix}:center_ground_line_y_widget"] = local_y
            return True
        return False
    if event.get("type") != "toolbar":
        return False
    action = str(event.get("action", ""))
    if action == "autocenter":
        offsets[selected_frame] = (0, 0)
        st.session_state[f"{prefix}:offsets"] = offsets
        st.session_state[f"{prefix}:offset_x_widget:{selected_frame}"] = 0
        st.session_state[f"{prefix}:offset_y_widget:{selected_frame}"] = 0
        st.session_state[f"{prefix}:center_widget_sync"] = True
        return True
    if action == "reset-transform":
        offsets[selected_frame] = (0, 0)
        st.session_state[f"{prefix}:offsets"] = offsets
        st.session_state[f"{prefix}:offset_x_widget:{selected_frame}"] = 0
        st.session_state[f"{prefix}:offset_y_widget:{selected_frame}"] = 0
        st.session_state[f"{prefix}:center_widget_sync"] = True
        return True
    if action == "zoom":
        zoom_key = f"{prefix}:center_zoom:{selected_frame}"
        zoom = int(event.get("zoom", st.session_state.get(zoom_key, 12)))
        st.session_state[zoom_key] = max(1, min(40, zoom))
        return True
    if action == "toggle-guides":
        key = f"{prefix}:center_guides"
        widget_key = f"{key}_widget"
        next_value = bool(
            event.get("showGuides", not bool(st.session_state.get(key, True)))
        )
        st.session_state[key] = next_value
        st.session_state[widget_key] = next_value
        return True
    if action == "guide-opacity":
        opacity = max(0.1, min(1.0, float(event.get("guideOpacity", 0.7))))
        st.session_state[f"{prefix}:center_guide_opacity"] = opacity
        st.session_state[f"{prefix}:center_guide_opacity_widget"] = opacity
        return True
    if action == "toggle-cell-center":
        value = bool(event.get("showCellCenter", True))
        st.session_state[f"{prefix}:center_show_cell_center"] = value
        st.session_state[f"{prefix}:center_show_cell_center_widget"] = value
        return True
    if action == "toggle-frame-guide":
        value = bool(event.get("showFrameGuide", True))
        st.session_state[f"{prefix}:center_show_frame_guide"] = value
        st.session_state[f"{prefix}:center_show_frame_guide_widget"] = value
        return True
    if action == "toggle-ground-line":
        value = bool(event.get("showGroundLine", False))
        st.session_state[f"{prefix}:center_show_ground_line"] = value
        st.session_state[f"{prefix}:center_show_ground_line_widget"] = value
        return True
    if action == "toggle-body-anchor":
        value = bool(event.get("showBodyAnchor", True))
        st.session_state[f"{prefix}:center_show_body_anchor"] = value
        st.session_state[f"{prefix}:center_show_body_anchor_widget"] = value
        return True
    if action == "toggle-target-anchor":
        value = bool(event.get("showTargetAnchor", True))
        st.session_state[f"{prefix}:center_show_target_anchor"] = value
        st.session_state[f"{prefix}:center_show_target_anchor_widget"] = value
        return True
    if action in {"ground-line", "ground-line-y", "move-ground-line"}:
        absolute_y = float(event.get("groundLineY", home_offset[1]))
        local_y = max(0, round(absolute_y - float(home_offset[1])))
        st.session_state[f"{prefix}:center_ground_line_y"] = local_y
        st.session_state[f"{prefix}:center_ground_line_y_widget"] = local_y
        return True
    if action == "toggle-anchor-delta":
        value = bool(event.get("showAnchorDelta", True))
        st.session_state[f"{prefix}:center_show_anchor_delta"] = value
        st.session_state[f"{prefix}:center_show_anchor_delta_widget"] = value
        return True
    if action == "autocrop":
        st.session_state[f"{prefix}:export_crop_enabled"] = True
        return True
    return False


def _handle_segmentation_cut_event(
    session: Any,
    count: int,
    event: dict[str, Any] | None,
) -> bool:
    if not event:
        return False
    prefix = session.session_id
    event_id = event.get("eventId")
    last_event = st.session_state.get(f"{prefix}:segmentation_cut_last_event")
    if not event_id or event_id == last_event:
        return False
    st.session_state[f"{prefix}:segmentation_cut_last_event"] = event_id
    if event.get("type") != "cut":
        if event.get("type") == "toolbar" and str(event.get("action", "")) == "zoom":
            zoom = int(event.get("zoom", st.session_state.get(f"{prefix}:segmentation_cut_zoom", 8)))
            st.session_state[f"{prefix}:segmentation_cut_zoom"] = max(1, min(40, zoom))
            return True
        return False
    cuts = event.get("cutPositions")
    if not isinstance(cuts, (list, tuple)):
        return False
    normalized = [int(value) for value in cuts]
    if len(normalized) != max(0, count - 1):
        return False
    st.session_state[f"{prefix}:segmentation_cut_positions"] = normalized
    return True


def _render_pick_preview(
    image: Image.Image,
    *,
    point: tuple[int, int] | None = None,
    radius: int | None = None,
) -> Image.Image:
    preview = render_frame_overlay(image, scale=1, show_bbox=False)
    if point is None:
        return preview
    x, y = point
    draw_point = (max(0, x), max(0, y))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(preview)
    draw.line((draw_point[0], 0, draw_point[0], preview.height - 1), fill=(91, 223, 255, 220))
    draw.line((0, draw_point[1], preview.width - 1, draw_point[1]), fill=(91, 223, 255, 220))
    if radius and radius > 0:
        draw.ellipse(
            (
                draw_point[0] - radius,
                draw_point[1] - radius,
                draw_point[0] + radius,
                draw_point[1] + radius,
            ),
            outline=(255, 196, 91, 255),
            width=1,
        )
    return preview


def _session_badge(session: Any) -> tuple[str, str]:
    if session.export_manifest:
        return "exported", "exported"
    if session.frame_adjustments and any(
        item.manual_offset_x or item.manual_offset_y for item in session.frame_adjustments
    ):
        return "adjusted", "adjusted"
    if "alignment" in session.stages or "background" in session.stages:
        return "processed", "processed"
    return "pending", "pending"


def _load_source(store: SheetSessionStore, session: Any) -> Image.Image:
    with Image.open(store.source_path(session)) as image:
        return image.convert("RGBA")


def _load_stage_frames(
    store: SheetSessionStore,
    session: Any,
    stage: str,
) -> tuple[Image.Image, ...]:
    return tuple(
        Image.open(path).convert("RGBA")
        for path in store.stage_paths(session, stage)
    )


def _ensure_adjustment_state(session: Any, count: int) -> None:
    prefix = session.session_id
    offsets_key = f"{prefix}:offsets"
    locks_key = f"{prefix}:locks"
    notes_key = f"{prefix}:notes"
    previous = {
        item.frame_index: item
        for item in session.frame_adjustments
        if item.frame_index < count
    }
    if offsets_key not in st.session_state or len(st.session_state[offsets_key]) != count:
        st.session_state[offsets_key] = [
            (
                previous[index].manual_offset_x if index in previous else 0,
                previous[index].manual_offset_y if index in previous else 0,
            )
            for index in range(count)
        ]
    if locks_key not in st.session_state or len(st.session_state[locks_key]) != count:
        st.session_state[locks_key] = [
            previous[index].locked if index in previous else False
            for index in range(count)
        ]
    if notes_key not in st.session_state or len(st.session_state[notes_key]) != count:
        st.session_state[notes_key] = [
            previous[index].notes if index in previous else ""
            for index in range(count)
        ]

    selected = min(
        int(st.session_state.get(f"{prefix}:selected_frame", 0)),
        max(0, count - 1),
    )
    lock_key = f"{prefix}:locked:{selected}"
    note_key = f"{prefix}:note:{selected}"
    offsets = list(st.session_state[offsets_key])
    locks = list(st.session_state[locks_key])
    notes = list(st.session_state[notes_key])
    if lock_key in st.session_state:
        locks[selected] = bool(st.session_state[lock_key])
    if note_key in st.session_state:
        notes[selected] = str(st.session_state[note_key])
    st.session_state[offsets_key] = offsets
    st.session_state[locks_key] = locks
    st.session_state[notes_key] = notes


def _ensure_center_guide_state(
    session: Any,
    *,
    default_ground_line_y: int,
    max_ground_line_y: int,
) -> None:
    prefix = session.session_id
    defaults: dict[str, Any] = {
        "center_guides": True,
        "center_guide_opacity": 0.7,
        "center_show_cell_center": True,
        "center_show_frame_guide": True,
        "center_show_ground_line": False,
        "center_ground_line_y": default_ground_line_y,
        "center_show_body_anchor": True,
        "center_show_target_anchor": True,
        "center_show_anchor_delta": True,
    }
    maximum = max(0, int(max_ground_line_y))
    for name, default in defaults.items():
        logical_key = f"{prefix}:{name}"
        widget_key = f"{logical_key}_widget"
        if logical_key not in st.session_state:
            st.session_state[logical_key] = default
        if name == "center_ground_line_y":
            st.session_state[logical_key] = max(
                0,
                min(maximum, int(st.session_state[logical_key])),
            )
        elif name == "center_guide_opacity":
            st.session_state[logical_key] = max(
                0.1,
                min(1.0, float(st.session_state[logical_key])),
            )
        else:
            st.session_state[logical_key] = bool(st.session_state[logical_key])
        if widget_key not in st.session_state:
            st.session_state[widget_key] = st.session_state[logical_key]
        elif name == "center_ground_line_y":
            st.session_state[widget_key] = max(
                0,
                min(maximum, int(st.session_state[widget_key])),
            )
            st.session_state[logical_key] = st.session_state[widget_key]
        elif name == "center_guide_opacity":
            st.session_state[logical_key] = max(
                0.1,
                min(1.0, float(st.session_state[widget_key])),
            )
        else:
            st.session_state[logical_key] = bool(st.session_state[widget_key])


def _clamp_manual_offsets_to_canvas(
    adjustments: Sequence[FrameAdjustment],
    manual_offsets: Sequence[tuple[int, int]],
    canvas_size: tuple[int, int],
) -> tuple[list[tuple[int, int]], list[int]]:
    width, height = canvas_size
    clamped: list[tuple[int, int]] = []
    changed: list[int] = []
    for index, (adjustment, offset) in enumerate(
        zip(adjustments, manual_offsets, strict=True)
    ):
        x0, y0, x1, y1 = adjustment.body_bbox
        base_dx = int(adjustment.applied_translation[0]) - int(adjustment.manual_offset_x)
        base_dy = int(adjustment.applied_translation[1]) - int(adjustment.manual_offset_y)
        min_x = -base_dx - int(x0)
        max_x = width - base_dx - int(x1)
        min_y = -base_dy - int(y0)
        max_y = height - base_dy - int(y1)
        next_x = max(min_x, min(max_x, int(offset[0])))
        next_y = max(min_y, min(max_y, int(offset[1])))
        if (next_x, next_y) != (int(offset[0]), int(offset[1])):
            changed.append(index)
        clamped.append((next_x, next_y))
    return clamped, changed


def _contact_sheet_cell_size(frames: Sequence[Image.Image]) -> tuple[int, int]:
    if not frames:
        raise ValueError("At least one frame is required")
    return max(frame.width for frame in frames), max(frame.height for frame in frames)


def _contact_sheet_frame_origin(
    frame_index: int,
    columns: int,
    cell_size: tuple[int, int],
) -> tuple[int, int]:
    cell_width, cell_height = cell_size
    return (frame_index % columns) * cell_width, (frame_index // columns) * cell_height


def _alignment_frame_position(
    frames: Sequence[Image.Image],
    frame_index: int,
    columns: int,
) -> tuple[int, int]:
    cell_size = _contact_sheet_cell_size(frames)
    origin_x, origin_y = _contact_sheet_frame_origin(frame_index, columns, cell_size)
    frame = frames[frame_index]
    return (
        origin_x + (cell_size[0] - frame.width) // 2,
        origin_y + (cell_size[1] - frame.height) // 2,
    )


def _alignment_workspace_preview(
    frames: Sequence[Image.Image],
    adjustments: Sequence[FrameAdjustment],
    selected_frame: int,
    columns: int,
    *,
    origin_offset: tuple[int, int] = (0, 0),
) -> Image.Image:
    sheet_frames = [frame.convert("RGBA") for frame in frames]
    sheet_frames[selected_frame] = Image.new("RGBA", sheet_frames[selected_frame].size, (0, 0, 0, 0))
    return render_contact_sheet(
        sheet_frames,
        adjustments=adjustments,
        columns=columns,
        scale=1,
        origin_offset=origin_offset,
    )


def _ensure_export_crop_state(session: Any) -> None:
    prefix = session.session_id
    enabled_key = f"{prefix}:export_crop_enabled"
    padding_key = f"{prefix}:export_crop_padding"
    threshold_key = f"{prefix}:export_crop_threshold"
    if enabled_key not in st.session_state:
        st.session_state[enabled_key] = session.export_crop_config.enabled
    if padding_key not in st.session_state:
        st.session_state[padding_key] = session.export_crop_config.padding
    if threshold_key not in st.session_state:
        st.session_state[threshold_key] = session.export_crop_config.alpha_threshold


def _fallback_centering(
    frames: Sequence[Image.Image],
    config: AutoCenterConfig,
) -> CenteringResult:
    adjustments: list[FrameAdjustment] = []
    for index, frame in enumerate(frames):
        adjustments.append(
            FrameAdjustment(
                frame_index=index,
                auto_anchor=(frame.width / 2, frame.height / 2),
                auto_confidence=0.0,
                manual_offset_x=0,
                manual_offset_y=0,
                final_anchor=tuple(map(float, config.canonical_anchor)),
                applied_translation=(0, 0),
                body_bbox=(0, 0, frame.width, frame.height),
                locked=False,
                notes="",
                manual_review=True,
            )
        )
    return CenteringResult(
        frames=tuple(frame.convert("RGBA") for frame in frames),
        adjustments=tuple(adjustments),
        jitter_report={
            "source_anchor_mean_delta": 0.0,
            "source_anchor_max_delta": 0.0,
            "manual_offset_max_delta": 0.0,
            "final_anchor_mean_error": 0.0,
            "final_anchor_max_error": 0.0,
            "minimum_confidence": 0.0,
            "mean_confidence": 0.0,
        },
        status="manual_review",
    )


def _safe_trim_transparent_frames(
    frames: Sequence[Image.Image],
    config: ExportCropConfig,
) -> tuple[ExportCropResult, str | None]:
    return trim_transparent_frames(frames, config), None


def _new_or_existing_session(store: SheetSessionStore) -> Any | None:
    sessions = store.list_sessions()
    active = st.session_state.get("active_sheet_session")
    if active not in sessions:
        active = sessions[0] if sessions else None
        st.session_state.active_sheet_session = active

    st.sidebar.markdown("### Sesión")
    options = ["Nueva sesión…", *sessions]
    index = options.index(active) if active in options else 0
    selected = st.sidebar.selectbox("Abrir sesión", options, index=index)
    if selected != "Nueva sesión…" and selected != active:
        st.session_state.active_sheet_session = selected
        st.rerun()

    upload = st.sidebar.file_uploader("Subir sprite sheet PNG", type=["png"])
    if upload is not None:
        digest = hashlib.sha256(upload.getvalue()).hexdigest()
        st.sidebar.caption(f"{upload.name} · {len(upload.getvalue()) / 1024:.1f} KB")
        if st.sidebar.button(
            "Crear sesión con este PNG",
            type="primary",
            width="stretch",
            key=f"create:{digest}",
        ):
            session = store.create(upload.getvalue(), source_name=upload.name)
            st.session_state.active_sheet_session = session.session_id
            st.rerun()

    active = st.session_state.get("active_sheet_session")
    return store.load(active) if active else None


def main() -> None:
    st.set_page_config(
        page_title="sprite-builder · Sheet Studio",
        page_icon="🟪",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _load_css()
    workspace = _workspace()
    store = SheetSessionStore(workspace)
    st.sidebar.markdown("# sprite-builder")
    st.sidebar.caption("Godot-ready pixel sprite pipeline")
    session = _new_or_existing_session(store)

    if session is None:
        st.title("Sheet Studio")
        st.caption("Postprocesado local, preciso y reversible para sprite sheets.")
        with st.container(border=True):
            st.subheader("Empieza con una sprite sheet")
            st.write(
                "Sube un PNG en la barra lateral. Se guardará una copia inmutable "
                "con SHA-256 antes de procesarlo."
            )
            st.info("La generación de imágenes no forma parte de esta interfaz.")
        return

    source = _load_source(store, session)
    inspection = session.inspection
    badge, tone = _session_badge(session)

    st.sidebar.markdown("### Fondo")
    use_corner = st.sidebar.toggle(
        "Usar esquina superior izquierda",
        value=False,
        key=f"{session.session_id}:use_corner",
    )
    color_hex = st.sidebar.color_picker(
        "Color a remover",
        value=_rgb_to_hex(session.background_removal_config.color),
        disabled=use_corner,
        key=f"{session.session_id}:background_color",
    )
    background_rgb = inspection.top_left_rgb if use_corner else _hex_to_rgb(color_hex)
    tolerance = float(
        st.sidebar.slider(
            "Tolerancia RGB",
            min_value=0,
            max_value=200,
            value=int(session.background_removal_config.tolerance),
            key=f"{session.session_id}:tolerance",
        )
    )
    cleanup = st.sidebar.toggle(
        "Cleanup de fringe",
        value=session.background_removal_config.cleanup_enabled,
        key=f"{session.session_id}:cleanup",
    )
    fringe = int(
        st.sidebar.slider(
            "Fuerza de cleanup",
            0,
            3,
            session.background_removal_config.fringe_cleanup_strength,
            disabled=not cleanup,
            key=f"{session.session_id}:fringe",
        )
    )
    preserve_outline = st.sidebar.toggle(
        "Preservar outline",
        value=session.background_removal_config.preserve_outline,
        key=f"{session.session_id}:preserve_outline",
    )
    remove_near = st.sidebar.toggle(
        "Quitar casi transparentes",
        value=session.background_removal_config.remove_near_transparent,
        key=f"{session.session_id}:remove_near",
    )
    background_config = BackgroundRemovalConfig(
        color=background_rgb,
        tolerance=tolerance,
        cleanup_enabled=cleanup,
        fringe_cleanup_strength=fringe,
        remove_near_transparent=remove_near,
        preserve_outline=preserve_outline,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Segmentación")
    frame_count = int(
        st.sidebar.number_input(
            "Número de frames",
            min_value=1,
            max_value=512,
            value=session.segmentation_config.frame_count,
            step=1,
            key=f"{session.session_id}:frame_count",
        )
    )
    orientation_labels = {
        "Horizontal": "horizontal",
        "Vertical": "vertical",
        "Grid": "grid",
    }
    current_orientation = session.segmentation_config.orientation
    orientation_label = st.sidebar.selectbox(
        "Orientación",
        tuple(orientation_labels),
        index=list(orientation_labels.values()).index(current_orientation),
        key=f"{session.session_id}:orientation",
    )
    orientation = orientation_labels[orientation_label]
    rows = int(
        st.sidebar.number_input(
            "Filas",
            min_value=1,
            max_value=512,
            value=max(1, session.segmentation_config.rows),
            disabled=orientation != "grid",
            key=f"{session.session_id}:rows",
        )
    )
    columns = int(
        st.sidebar.number_input(
            "Columnas",
            min_value=1,
            max_value=512,
            value=max(1, session.segmentation_config.columns),
            disabled=orientation != "grid",
            key=f"{session.session_id}:columns",
        )
    )
    auto_cell = st.sidebar.toggle(
        "Auto-calcular tamaño de celda",
        value=session.segmentation_config.cell_width is None,
        key=f"{session.session_id}:auto_cell",
    )
    cell_width = int(
        st.sidebar.number_input(
            "Cell width",
            min_value=1,
            value=session.segmentation_config.cell_width or inspection.width,
            disabled=auto_cell,
            key=f"{session.session_id}:cell_width",
        )
    )
    cell_height = int(
        st.sidebar.number_input(
            "Cell height",
            min_value=1,
            value=session.segmentation_config.cell_height or inspection.height,
            disabled=auto_cell,
            key=f"{session.session_id}:cell_height",
        )
    )
    cut_col1, cut_col2 = st.sidebar.columns(2)
    offset_x = int(
        cut_col1.number_input(
            "Offset X",
            min_value=0,
            value=session.segmentation_config.offset_x,
            key=f"{session.session_id}:offset_x",
        )
    )
    offset_y = int(
        cut_col2.number_input(
            "Offset Y",
            min_value=0,
            value=session.segmentation_config.offset_y,
            key=f"{session.session_id}:offset_y",
        )
    )
    gap_col1, gap_col2 = st.sidebar.columns(2)
    spacing_x = int(
        gap_col1.number_input(
            "Spacing X",
            min_value=0,
            value=session.segmentation_config.spacing_x,
            key=f"{session.session_id}:spacing_x",
        )
    )
    spacing_y = int(
        gap_col2.number_input(
            "Spacing Y",
            min_value=0,
            value=session.segmentation_config.spacing_y,
            key=f"{session.session_id}:spacing_y",
        )
    )
    segmentation_config = SegmentationConfig(
        frame_count=frame_count,
        orientation=orientation,  # type: ignore[arg-type]
        rows=rows,
        columns=columns,
        cell_width=None if auto_cell else cell_width,
        cell_height=None if auto_cell else cell_height,
        offset_x=offset_x,
        offset_y=offset_y,
        spacing_x=spacing_x,
        spacing_y=spacing_y,
    )
    current_cut_positions = _normalized_segmentation_cut_positions(
        source.size,
        segmentation_config,
        st.session_state.get(
            f"{session.session_id}:segmentation_cut_positions",
            session.segmentation_config.manual_cut_positions,
        ),
    )
    segmentation_config = SegmentationConfig(
        frame_count=segmentation_config.frame_count,
        orientation=segmentation_config.orientation,
        rows=segmentation_config.rows,
        columns=segmentation_config.columns,
        cell_width=segmentation_config.cell_width,
        cell_height=segmentation_config.cell_height,
        offset_x=segmentation_config.offset_x,
        offset_y=segmentation_config.offset_y,
        spacing_x=segmentation_config.spacing_x,
        spacing_y=segmentation_config.spacing_y,
        manual_cut_positions=current_cut_positions,
    )

    manual_cut_positions = _ensure_segmentation_cut_state(
        session,
        source.size,
        segmentation_config,
    )
    segmentation_config = SegmentationConfig(
        frame_count=segmentation_config.frame_count,
        orientation=segmentation_config.orientation,
        rows=segmentation_config.rows,
        columns=segmentation_config.columns,
        cell_width=segmentation_config.cell_width,
        cell_height=segmentation_config.cell_height,
        offset_x=segmentation_config.offset_x,
        offset_y=segmentation_config.offset_y,
        spacing_x=segmentation_config.spacing_x,
        spacing_y=segmentation_config.spacing_y,
        manual_cut_positions=manual_cut_positions,
    )

    try:
        resolved_config, _ = resolve_segmentation_config(source.size, segmentation_config)
        resolved_cell = (
            resolved_config.cell_width or source.width,
            resolved_config.cell_height or source.height,
        )
    except ValueError:
        resolved_cell = source.size

    st.sidebar.markdown("### Auto Center")
    auto_canvas = st.sidebar.toggle(
        "Canvas igual a celda",
        value=True,
        key=f"{session.session_id}:auto_canvas",
    )
    canvas_col1, canvas_col2 = st.sidebar.columns(2)
    canvas_width = (
        resolved_cell[0]
        if auto_canvas
        else int(
            canvas_col1.number_input(
                "Canvas W",
                min_value=1,
                value=session.auto_center_config.canvas_width,
                key=f"{session.session_id}:canvas_width",
            )
        )
    )
    canvas_height = (
        resolved_cell[1]
        if auto_canvas
        else int(
            canvas_col2.number_input(
                "Canvas H",
                min_value=1,
                value=session.auto_center_config.canvas_height,
                key=f"{session.session_id}:canvas_height",
            )
        )
    )
    if auto_canvas:
        canvas_col1.metric("Canvas W", canvas_width)
        canvas_col2.metric("Canvas H", canvas_height)
    method_label = st.sidebar.radio(
        "Método",
        ("Body / torso anchor", "Bounding box simple"),
        index=0 if session.auto_center_config.method == "body" else 1,
        key=f"{session.session_id}:center_method",
    )
    auto_target = st.sidebar.toggle(
        "Anchor recomendado",
        value=True,
        key=f"{session.session_id}:auto_target",
    )
    anchor_col1, anchor_col2 = st.sidebar.columns(2)
    canonical_anchor = (
        (canvas_width // 2, round(canvas_height * 0.55))
        if auto_target
        else (
            int(
                anchor_col1.number_input(
                    "Anchor X",
                    min_value=0,
                    max_value=max(0, canvas_width - 1),
                    value=min(
                        session.auto_center_config.canonical_anchor[0],
                        max(0, canvas_width - 1),
                    ),
                    key=f"{session.session_id}:anchor_x",
                )
            ),
            int(
                anchor_col2.number_input(
                    "Anchor Y",
                    min_value=0,
                    max_value=max(0, canvas_height - 1),
                    value=min(
                        session.auto_center_config.canonical_anchor[1],
                        max(0, canvas_height - 1),
                    ),
                    key=f"{session.session_id}:anchor_y",
                )
            ),
        )
    )
    if auto_target:
        anchor_col1.metric("Anchor X", canonical_anchor[0])
        anchor_col2.metric("Anchor Y", canonical_anchor[1])
    confidence = float(
        st.sidebar.slider(
            "Umbral de confianza",
            min_value=0.0,
            max_value=1.0,
            value=float(session.auto_center_config.confidence_threshold),
            step=0.05,
            key=f"{session.session_id}:confidence",
        )
    )
    center_config = AutoCenterConfig(
        method="body" if method_label.startswith("Body") else "bounding_box",
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        canonical_anchor=canonical_anchor,
        confidence_threshold=confidence,
    )

    background_source = source
    segmentation = None
    background_frames: tuple[Image.Image, ...] = ()
    centered = None
    preview_centered = None
    center_error: str | None = None
    processing_error: str | None = None
    try:
        background_source = apply_background_removal(
            (source,),
            background_config,
        )[0]
        _ensure_manual_background_state(store, session, 1)
        _ensure_background_editor_state(session, 1)
        prefix = session.session_id
        background_source = apply_manual_background_edits(
            (background_source,),
            st.session_state[f"{prefix}:background_manual_ops"],
        )[0]
        segmentation = segment_sheet(
            background_source,
            segmentation_config,
            background_rgb=background_config.color,
        )
        background_frames = segmentation.frames
        _ensure_adjustment_state(session, len(background_frames))
        try:
            centered = auto_center_frames(
                background_frames,
                center_config,
                manual_offsets=st.session_state[f"{prefix}:offsets"],
                locked=st.session_state[f"{prefix}:locks"],
                notes=st.session_state[f"{prefix}:notes"],
                overflow_strategy="clamp",
            )
            preview_centered = auto_center_frames(
                background_frames,
                center_config,
                manual_offsets=[(0, 0)] * len(background_frames),
                locked=st.session_state[f"{prefix}:locks"],
                notes=st.session_state[f"{prefix}:notes"],
                overflow_strategy="clamp",
            )
        except (OverflowError, IndexError) as exc:
            center_error = str(exc)
            centered = _fallback_centering(background_frames, center_config)
            preview_centered = _fallback_centering(background_frames, center_config)
    except (ValueError, OverflowError) as exc:
        processing_error = str(exc)

    st.title("sprite-builder")
    st.caption("Godot-ready pixel sprite pipeline · Sheet Studio")
    st.markdown(status_badge(badge, tone), unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="metric-row">
          <span class="metric-pill">{inspection.width} × {inspection.height}px</span>
          <span class="metric-pill">Modo {inspection.mode}</span>
          <span class="metric-pill">Alpha: {"sí" if inspection.has_alpha else "no"}</span>
          <span class="metric-pill">Sesión {session.session_id}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if processing_error:
        st.error(processing_error)
    elif center_error:
        st.warning(
            f"{center_error} · Se abrió un fallback manual para que puedas ajustar el sheet."
        )

    sheet_tab, background_tab, align_tab, export_tab = st.tabs(
        ("Sheet", "Background", "Segmentación + Auto Center", "Export")
    )

    with sheet_tab:
        st.subheader("Carga y segmentación")
        left, right = st.columns((1.65, 1), gap="large")
        with left:
            if segmentation:
                prefix = session.session_id
                _ensure_segmentation_cut_controls_state(session)
                guide_overlay = render_segmentation_guides(background_source, segmentation)
                with st.container(border=True):
                    st.markdown("#### Líneas de corte · preview 1:1 / pixelated")
                    event = pixel_editor(
                        background_source,
                        overlay=guide_overlay,
                        sample=None,
                        tool="drag",
                        mode="segmentation-cut",
                        zoom=int(st.session_state[f"{prefix}:segmentation_cut_zoom"]),
                        cut_positions=st.session_state[f"{prefix}:segmentation_cut_positions"],
                        allow_cut_drag=bool(
                            st.session_state[f"{prefix}:segmentation_free_adjust"]
                        ),
                        fit_on_load=True,
                        frame_token=(
                            f"{prefix}:segmentation-cut:{background_source.width}x"
                            f"{background_source.height}:{segmentation_config.frame_count}:"
                            f"{segmentation_config.orientation}"
                        ),
                        key=f"{prefix}:segmentation_cut_editor",
                    )
                    changed = _handle_segmentation_cut_event(
                        session,
                        segmentation.resolved_config.frame_count,
                        event,
                    )
                    if changed:
                        st.rerun()
            else:
                _show_pixel(source, "Sprite sheet original")
        with right, st.container(border=True):
            st.markdown("#### Inspección")
            st.write(f"Dimensiones reales: `{inspection.width} × {inspection.height}`")
            st.write(f"Canal alpha: `{'sí' if inspection.has_alpha else 'no'}`")
            st.write(
                "Fondo sólido/chroma: "
                f"`{'probable' if inspection.solid_background_likely else 'no concluyente'}`"
            )
            st.write(f"Color de borde: `{_rgb_to_hex(inspection.border_rgb)}`")
            st.write(f"Confianza de borde: `{inspection.background_confidence:.0%}`")
            if segmentation:
                resolved = segmentation.resolved_config
                st.write(
                    f"Celda resuelta: `{resolved.cell_width} × {resolved.cell_height}`"
                )
                if resolved.manual_cut_positions:
                    st.write(
                        "Cortes manuales: "
                        f"`{', '.join(map(str, resolved.manual_cut_positions))}`"
                    )
                for warning in segmentation.warnings:
                    st.warning(warning)
            if segmentation:
                st.markdown("#### Herramientas manuales")
                if st.button(
                    "Auto cut",
                    width="stretch",
                    key=f"{session.session_id}:segmentation_auto_cut",
                ):
                    auto_cuts = _set_auto_segmentation_cuts(
                        session,
                        source.size,
                        segmentation_config,
                    )
                    st.session_state[f"{session.session_id}:segmentation_cut_positions"] = list(auto_cuts)
                    st.rerun()
                zoom_col1, zoom_col2 = st.columns(2)
                if zoom_col1.button(
                    "Zoom -",
                    width="stretch",
                    key=f"{session.session_id}:segmentation_cut_zoom_out",
                ):
                    st.session_state[f"{session.session_id}:segmentation_cut_zoom"] = max(
                        1,
                        int(st.session_state[f"{session.session_id}:segmentation_cut_zoom"]) - 1,
                    )
                    st.session_state[f"{session.session_id}:segmentation_cut_zoom_widget_sync"] = (
                        st.session_state[f"{session.session_id}:segmentation_cut_zoom"]
                    )
                    st.rerun()
                if zoom_col2.button(
                    "Zoom +",
                    width="stretch",
                    key=f"{session.session_id}:segmentation_cut_zoom_in",
                ):
                    st.session_state[f"{session.session_id}:segmentation_cut_zoom"] = min(
                        40,
                        int(st.session_state[f"{session.session_id}:segmentation_cut_zoom"]) + 1,
                    )
                    st.session_state[f"{session.session_id}:segmentation_cut_zoom_widget_sync"] = (
                        st.session_state[f"{session.session_id}:segmentation_cut_zoom"]
                    )
                    st.rerun()
                free_adjust = st.toggle(
                    "Free adjust",
                    value=bool(st.session_state[f"{session.session_id}:segmentation_free_adjust"]),
                    key=f"{session.session_id}:segmentation_free_adjust_widget",
                    help="Actívalo para arrastrar las líneas verticales de corte.",
                )
                st.session_state[f"{session.session_id}:segmentation_free_adjust"] = bool(free_adjust)
                st.caption(
                    "Arrastra las líneas verticales del canvas para mover los cortes "
                    "y luego guarda la segmentación."
                )
                st.write(f"Modo libre: `{'sí' if free_adjust else 'no'}`")
        if segmentation:
            st.markdown("#### Frames extraídos")
            gallery = st.columns(min(6, len(segmentation.frames)))
            for index, frame in enumerate(segmentation.frames):
                with gallery[index % len(gallery)]:
                    _show_pixel(frame, f"Frame {index}", max_height=180)
            if st.button(
                "Guardar segmentación",
                type="primary",
                key=f"{session.session_id}:save_segmentation",
            ):
                session.segmentation_config = segmentation_config
                store.commit_stage(
                    session,
                    "segmentation",
                    segmentation.frames,
                    config=segmentation_config.to_dict(),
                    warnings=segmentation.warnings,
                    metadata={
                        "regions": [list(region) for region in segmentation.regions],
                        "resolved_config": segmentation.resolved_config.to_dict(),
                        "empty_frames": list(segmentation.empty_frames),
                    },
                )
                st.success("Segmentación guardada como intento inmutable.")

    with background_tab:
        st.subheader("Remoción de fondo")
        if background_source:
            prefix = session.session_id
            wide_mode = st.toggle(
                "Modo editor ancho",
                value=bool(st.session_state.get(f"{prefix}:background_wide_mode", True)),
                key=f"{prefix}:background_wide_mode",
                help="Oculta la barra lateral para darle el máximo ancho posible al canvas.",
            )
            _set_editor_width_mode(wide_mode)
            tool_col1, tool_col2, tool_col3 = st.columns((1.45, 1, 0.8), gap="small")
            tool_key = f"{prefix}:background_tool"
            tool_widget_key = f"{prefix}:background_tool_widget"
            tool_sync_key = f"{prefix}:background_tool_widget_sync"
            brush_key = f"{prefix}:background_brush_radius"
            brush_widget_key = f"{prefix}:background_brush_radius_widget"
            brush_sync_key = f"{prefix}:background_brush_radius_widget_sync"
            if tool_sync_key in st.session_state:
                st.session_state[tool_widget_key] = st.session_state.pop(tool_sync_key)
            elif tool_widget_key not in st.session_state:
                st.session_state[tool_widget_key] = st.session_state[tool_key]
            if brush_sync_key in st.session_state:
                st.session_state[brush_widget_key] = st.session_state.pop(brush_sync_key)
            elif brush_widget_key not in st.session_state:
                st.session_state[brush_widget_key] = st.session_state[brush_key]
            with tool_col1:
                tool_value = st.radio(
                    "Herramienta",
                    ("wand", "eraser", "eyedropper"),
                    horizontal=True,
                    key=tool_widget_key,
                    format_func=_background_tool_label,
                    help="W varita, E borrador, I cuentagotas.",
                )
                st.session_state[tool_key] = _normalize_background_tool(tool_value)
            with tool_col2:
                brush_value = st.slider(
                    "Radio",
                    min_value=1,
                    max_value=48,
                    key=brush_widget_key,
                    disabled=st.session_state[tool_key] != "eraser",
                    help="Tamaño del borrador manual en píxeles.",
                )
                st.session_state[brush_key] = max(1, min(48, int(brush_value)))
            with tool_col3:
                st.metric("Activo", _background_tool_label(st.session_state[tool_key]))
            selected_bg = 0
            sampled_rgba = st.session_state[f"{prefix}:background_sampled_color"]
            contiguous = st.toggle(
                "Varita contigua",
                value=True,
                key=f"{prefix}:bg_contiguous:{selected_bg}",
            )
            manual_tolerance = float(
                st.slider(
                    "Tolerancia de la varita",
                    min_value=0,
                    max_value=255,
                    value=min(255, int(background_config.tolerance)),
                    key=f"{prefix}:bg_manual_tol:{selected_bg}",
                )
            )
            selection_masks = st.session_state[f"{prefix}:background_selection_masks"]
            normalized_selection_masks: list[np.ndarray | None] = []
            invalid_mask = False
            for frame, mask in zip((background_source,), selection_masks):
                if isinstance(mask, np.ndarray) and mask.shape == (frame.height, frame.width):
                    normalized_selection_masks.append(mask)
                else:
                    normalized_selection_masks.append(None)
                    if mask is not None:
                        invalid_mask = True
            if invalid_mask:
                st.session_state[f"{prefix}:background_selection_masks"] = normalized_selection_masks
            selection_masks = normalized_selection_masks
            selection_mask = selection_masks[selected_bg]
            overlay = render_selection_overlay(
                background_source.size,
                selection_mask if isinstance(selection_mask, np.ndarray) else None,
            )
            tool_zoom = int(st.session_state[f"{prefix}:background_zoom"])
            editor_box = st.container(border=True)
            with editor_box:
                st.markdown("#### Canvas de edición")
                event = pixel_editor(
                    background_source,
                    overlay=overlay,
                    sample=st.session_state[f"{prefix}:background_sampled_color"],
                    tool=st.session_state[tool_key],
                    brush_radius=int(st.session_state[brush_key]),
                    zoom=tool_zoom,
                    key=f"{prefix}:pixel_editor:{selected_bg}",
                )
                changed = _handle_background_editor_event(
                    session,
                    (background_source,),
                    selected_bg,
                    event,
                    tolerance=manual_tolerance,
                    contiguous=contiguous,
                )
                if changed:
                    st.rerun()
                st.caption(
                    "Click sobre el canvas. `I` activa cuentagotas, `W` activa varita, "
                    "`E` activa borrador, `Shift` suma, `Alt/Option` resta, `Esc` limpia selección y "
                    "`Delete/Backspace` borra los pixels seleccionados."
                )
            left_col, right_col = st.columns((1.15, 0.85), gap="large")
            with left_col:
                preview_col1, preview_col2 = st.columns(2, gap="large")
                with preview_col1:
                    _show_pixel(source, "Sprite sheet original")
                with preview_col2:
                    _show_pixel(
                        background_source,
                        "Procesado · fondo removido",
                    )
                _show_pixel(
                    background_source,
                    "Sheet limpio · base para segmentar",
                    max_height=420,
                )
            with right_col, st.container(border=True):
                st.markdown("#### Estado de la herramienta")
                st.markdown(
                    f"Color muestreado: `{_rgb_to_hex(sampled_rgba[:3])}` · Alpha `{sampled_rgba[3]}`"
                )
                selection_pixels = (
                    int(selection_mask.sum())
                    if isinstance(selection_mask, np.ndarray) and selection_mask.size
                    else 0
                )
                st.write(f"Tool actual: `{st.session_state[f'{prefix}:background_tool']}`")
                st.write(
                    f"Herramienta activa: `{_background_tool_label(st.session_state[f'{prefix}:background_tool'])}`"
                )
                st.write(f"Zoom actual: `{tool_zoom}x`")
                if st.session_state[f"{prefix}:background_tool"] == "eraser":
                    st.write(
                        f"Radio del borrador: `{int(st.session_state[f'{prefix}:background_brush_radius'])}`"
                    )
                st.write(f"Pixels seleccionados: `{selection_pixels}`")
                st.write(f"Tolerancia: `{int(manual_tolerance)}`")
                st.write(f"Contiguo: `{'sí' if contiguous else 'no'}`")
                zoom_col1, zoom_col2, zoom_col3 = st.columns(3)
                if zoom_col1.button("Zoom -", width="stretch", key=f"{prefix}:bg_zoom_out:{selected_bg}"):
                    st.session_state[f"{prefix}:background_zoom"] = max(1, tool_zoom - 1)
                    st.rerun()
                if zoom_col2.button("Zoom 100%", width="stretch", key=f"{prefix}:bg_zoom_reset:{selected_bg}"):
                    st.session_state[f"{prefix}:background_zoom"] = 8
                    st.rerun()
                if zoom_col3.button("Zoom +", width="stretch", key=f"{prefix}:bg_zoom_in:{selected_bg}"):
                    st.session_state[f"{prefix}:background_zoom"] = min(40, tool_zoom + 1)
                    st.rerun()
                action_col1, action_col2 = st.columns(2)
                if action_col1.button(
                    "Borrar selección",
                    width="stretch",
                    disabled=selection_pixels == 0,
                    key=f"{prefix}:bg_delete_selection:{selected_bg}",
                ):
                    operations = {
                        int(index): [dict(item) for item in items]
                        for index, items in st.session_state[f"{prefix}:background_manual_ops"].items()
                    }
                    if isinstance(selection_mask, np.ndarray) and selection_mask.any():
                        operations.setdefault(selected_bg, []).append(
                            {"kind": "erase_mask", **encode_mask(selection_mask)}
                        )
                        st.session_state[f"{prefix}:background_manual_ops"] = operations
                        selection_masks[selected_bg] = None
                        st.session_state[f"{prefix}:background_selection_masks"] = selection_masks
                        st.rerun()
                if action_col2.button(
                    "Limpiar selección",
                    width="stretch",
                    disabled=selection_pixels == 0,
                    key=f"{prefix}:bg_clear_selection:{selected_bg}",
                ):
                    selection_masks[selected_bg] = None
                    st.session_state[f"{prefix}:background_selection_masks"] = selection_masks
                    st.rerun()
                operations = st.session_state[f"{prefix}:background_manual_ops"]
                frame_ops = operations.get(selected_bg, [])
                st.markdown("#### Historial del frame")
                st.write(f"Operaciones manuales: `{len(frame_ops)}`")
                if frame_ops:
                    history_rows = [
                        {
                            "paso": str(index + 1),
                            "tipo": {
                                "erase_similar": "varita",
                                "erase_brush": "borrador",
                                "erase_mask": "selección",
                            }.get(op["kind"], op["kind"]),
                            "punto": ",".join(map(str, op.get("point", ()))),
                            "tol": str(op.get("tolerance", "-")),
                            "radio": str(op.get("radius", "-")),
                            "contiguo": str(op.get("contiguous", "-")),
                        }
                        for index, op in enumerate(frame_ops)
                    ]
                    st.dataframe(history_rows, width="stretch", hide_index=True)
                else:
                    st.info("Este frame no tiene ediciones manuales todavía.")
                clear_col, clear_all_col = st.columns(2)
                if clear_col.button(
                    "Reset frame",
                    width="stretch",
                    key=f"{prefix}:bg_clear_frame:{selected_bg}",
                ):
                    updated = {
                        int(index): [dict(item) for item in items]
                        for index, items in operations.items()
                        if int(index) != selected_bg and items
                    }
                    st.session_state[f"{prefix}:background_manual_ops"] = updated
                    st.rerun()
                if clear_all_col.button(
                    "Reset todo",
                    width="stretch",
                    key=f"{prefix}:bg_clear_all",
                ):
                    st.session_state[f"{prefix}:background_manual_ops"] = {}
                    st.session_state[f"{prefix}:background_selection_masks"] = [
                        None
                    ]
                    st.rerun()
            if st.button(
                "Guardar remoción de fondo",
                type="primary",
                key=f"{session.session_id}:save_background",
            ):
                session.background_removal_config = background_config
                store.commit_stage(
                    session,
                    "background",
                    [background_source],
                    config=background_config.to_dict(),
                    metadata={
                        "manual_edit_operations": {
                            str(index): list(items)
                            for index, items in st.session_state[
                                f"{prefix}:background_manual_ops"
                            ].items()
                            if items
                        }
                    },
                )
                st.success("Frames transparentes guardados.")
        else:
            st.info("No hay un resultado de fondo válido todavía.")

    with align_tab:
        st.subheader("Segmentación y centrado manual")
        if centered:
            prefix = session.session_id
            if f"{prefix}:center_guides" not in st.session_state:
                st.session_state[f"{prefix}:center_guides"] = True
            preview_crop_config = (
                session.export_crop_config
                if session.export_crop_config.enabled
                else ExportCropConfig(
                    enabled=True,
                    padding=max(8, min(canvas_width, canvas_height) // 10),
                    alpha_threshold=8,
                )
            )
            preview_source = centered
            preview_crop, preview_crop_warning = _safe_trim_transparent_frames(
                preview_source.frames,
                preview_crop_config,
            )
            if preview_crop_warning:
                st.warning(
                    "El preview de crop usa un fallback porque los frames tienen "
                    "tamaños distintos. La exportación seguirá usando el canvas de cada frame."
                )
            if centered.status == "manual_review":
                st.warning(
                    "Hay anchors de baja confianza. Revísalos y bloquéalos antes de exportar."
                )
            selected = st.selectbox(
                "Frame",
                tuple(range(len(preview_crop.frames))),
                key=f"{prefix}:selected_frame",
            )
            sheet_columns = min(6, len(preview_crop.frames))
            selected_frame = preview_crop.frames[selected]
            selected_home = _alignment_frame_position(preview_crop.frames, selected, sheet_columns)
            selected_offset = st.session_state[f"{prefix}:offsets"][selected]
            selected_position = (
                selected_home[0] + int(selected_offset[0]),
                selected_home[1] + int(selected_offset[1]),
            )
            _ensure_center_guide_state(
                session,
                default_ground_line_y=max(0, selected_frame.height - 1),
                max_ground_line_y=max(0, selected_frame.height - 1),
            )
            preview_adjustment = preview_source.adjustments[selected]
            crop_origin_x, crop_origin_y = preview_crop.bbox[:2]
            current_anchor_x = (
                selected_home[0]
                + preview_adjustment.auto_anchor[0]
                + preview_adjustment.applied_translation[0]
                - crop_origin_x
                + int(selected_offset[0])
            )
            current_anchor_y = (
                selected_home[1]
                + preview_adjustment.auto_anchor[1]
                + preview_adjustment.applied_translation[1]
                - crop_origin_y
                + int(selected_offset[1])
            )
            target_anchor_x = (
                selected_home[0] + center_config.canonical_anchor[0] - crop_origin_x
            )
            target_anchor_y = (
                selected_home[1] + center_config.canonical_anchor[1] - crop_origin_y
            )
            ground_line_y = (
                selected_home[1]
                + int(st.session_state[f"{prefix}:center_ground_line_y"])
            )
            combined_canvas = _alignment_workspace_preview(
                preview_crop.frames,
                preview_source.adjustments,
                selected,
                sheet_columns,
                origin_offset=(preview_crop.bbox[0], preview_crop.bbox[1]),
            )
            st.caption(
                "La previsualización y la edición viven en el mismo canvas. "
                "Arrastra el frame activo dentro de la grilla para reajustarlo."
            )
            center_zoom_key = f"{prefix}:center_zoom:{selected}"
            has_persisted_zoom = center_zoom_key in st.session_state
            center_zoom = max(
                1,
                min(40, int(st.session_state.get(center_zoom_key, 12))),
            )
            event = pixel_editor(
                combined_canvas,
                overlay=selected_frame,
                sample=None,
                tool="drag",
                mode="segmentation-center",
                zoom=center_zoom,
                offset_x=selected_position[0],
                offset_y=selected_position[1],
                home_offset_x=selected_home[0],
                home_offset_y=selected_home[1],
                show_guides=bool(st.session_state[f"{prefix}:center_guides"]),
                guide_opacity=float(
                    st.session_state[f"{prefix}:center_guide_opacity"]
                ),
                show_cell_center=bool(
                    st.session_state[f"{prefix}:center_show_cell_center"]
                ),
                show_frame_guide=bool(
                    st.session_state[f"{prefix}:center_show_frame_guide"]
                ),
                show_ground_line=bool(
                    st.session_state[f"{prefix}:center_show_ground_line"]
                ),
                ground_line_y=ground_line_y,
                current_anchor_x=(
                    current_anchor_x
                    if st.session_state[f"{prefix}:center_show_body_anchor"]
                    else None
                ),
                current_anchor_y=(
                    current_anchor_y
                    if st.session_state[f"{prefix}:center_show_body_anchor"]
                    else None
                ),
                target_anchor_x=(
                    target_anchor_x
                    if st.session_state[f"{prefix}:center_show_target_anchor"]
                    else None
                ),
                target_anchor_y=(
                    target_anchor_y
                    if st.session_state[f"{prefix}:center_show_target_anchor"]
                    else None
                ),
                show_anchor_delta=bool(
                    st.session_state[f"{prefix}:center_show_anchor_delta"]
                ),
                allow_drag=True,
                show_autocenter=True,
                show_autocrop=True,
                fit_on_load=not has_persisted_zoom,
                fit_token=(
                    f"{prefix}:center:{selected}:{combined_canvas.width}x{combined_canvas.height}:"
                    f"{selected_frame.width}x{selected_frame.height}"
                ),
                frame_token=(
                    f"{prefix}:center:{selected}:{combined_canvas.width}x{combined_canvas.height}:"
                    f"{selected_frame.width}x{selected_frame.height}"
                ),
                key=f"{prefix}:center_pixel_editor",
            )
            changed = _handle_center_editor_event(
                session,
                len(centered.frames),
                selected,
                event,
                home_offset=selected_home,
            )
            if changed:
                st.rerun()
            if st.button(
                "Fijar frame",
                type="primary",
                key=f"{session.session_id}:save_center",
            ):
                _ensure_adjustment_state(session, len(background_frames))
                final_result = auto_center_frames(
                    background_frames,
                    center_config,
                    manual_offsets=st.session_state[f"{prefix}:offsets"],
                    locked=st.session_state[f"{prefix}:locks"],
                    notes=st.session_state[f"{prefix}:notes"],
                    overflow_strategy="clamp",
                )
                session.segmentation_config = segmentation_config
                session.background_removal_config = background_config
                session.auto_center_config = center_config
                store.commit_stage(
                    session,
                    "alignment",
                    final_result.frames,
                    config={
                        "segmentation": segmentation_config.to_dict(),
                        "background": background_config.to_dict(),
                        "auto_center": center_config.to_dict(),
                        "manual_offsets": list(st.session_state[f"{prefix}:offsets"]),
                    },
                    status=final_result.status,
                    metrics=final_result.jitter_report,
                    metadata={
                        "frames": [item.to_dict() for item in final_result.adjustments]
                    },
                )
                store.save_adjustments(session, final_result.adjustments)
                st.success("Frame fijado y anchors guardados.")
                st.rerun()
            st.caption(
                f"Canvas visible recortado a `{preview_crop.bbox[2] - preview_crop.bbox[0]} × "
                f"{preview_crop.bbox[3] - preview_crop.bbox[1]}` para que el drag sea más natural."
            )
            st.dataframe(
                [
                    {
                        "frame": item.frame_index,
                        "anchor_x": round(item.auto_anchor[0], 2),
                        "anchor_y": round(item.auto_anchor[1], 2),
                        "confidence": round(item.auto_confidence, 3),
                        "offset_x": item.manual_offset_x,
                        "offset_y": item.manual_offset_y,
                        "status": "review" if item.manual_review else "passed",
                    }
                    for item in centered.adjustments
                ],
                width="stretch",
                hide_index=True,
            )
            with st.expander("Reporte de jitter"):
                st.json(centered.jitter_report)
            adjustment = centered.adjustments[selected]
            view_col, property_col = st.columns((1.7, 1), gap="large")
            with view_col:
                offset_x = st.session_state[f"{prefix}:offsets"][selected][0]
                offset_y = st.session_state[f"{prefix}:offsets"][selected][1]
                st.write(f"Offset manual actual: `{offset_x}, {offset_y}`")
            with property_col, st.container(border=True):
                st.markdown("#### Propiedades del frame")
                offsets = st.session_state[f"{prefix}:offsets"]
                locks = st.session_state[f"{prefix}:locks"]
                notes = st.session_state[f"{prefix}:notes"]
                sync_widgets = bool(st.session_state.get(f"{prefix}:center_widget_sync", False))
                x_widget_key = f"{prefix}:offset_x_widget:{selected}"
                y_widget_key = f"{prefix}:offset_y_widget:{selected}"
                if sync_widgets or x_widget_key not in st.session_state:
                    st.session_state[x_widget_key] = int(offsets[selected][0])
                if sync_widgets or y_widget_key not in st.session_state:
                    st.session_state[y_widget_key] = int(offsets[selected][1])
                st.number_input(
                    "Offset X",
                    min_value=-canvas_width,
                    max_value=canvas_width,
                    key=x_widget_key,
                )
                st.number_input(
                    "Offset Y",
                    min_value=-canvas_height,
                    max_value=canvas_height,
                    key=y_widget_key,
                )
                guides_enabled = bool(st.session_state[f"{prefix}:center_guides"])
                st.checkbox(
                    "Mostrar guías",
                    key=f"{prefix}:center_guides_widget",
                    help="Activa únicamente ayudas visuales; no modifica ni guarda el sprite.",
                )
                st.slider(
                    "Opacidad de guías",
                    min_value=0.1,
                    max_value=1.0,
                    step=0.05,
                    key=f"{prefix}:center_guide_opacity_widget",
                    disabled=not guides_enabled,
                )
                guide_col1, guide_col2 = st.columns(2)
                guide_col1.checkbox(
                    "Centro de celda",
                    key=f"{prefix}:center_show_cell_center_widget",
                    disabled=not guides_enabled,
                )
                guide_col2.checkbox(
                    "Frame móvil",
                    key=f"{prefix}:center_show_frame_guide_widget",
                    disabled=not guides_enabled,
                )
                st.checkbox(
                    "Línea de suelo",
                    key=f"{prefix}:center_show_ground_line_widget",
                    disabled=not guides_enabled,
                )
                st.number_input(
                    "Suelo Y dentro de la celda",
                    min_value=0,
                    max_value=max(0, selected_frame.height - 1),
                    key=f"{prefix}:center_ground_line_y_widget",
                    disabled=(
                        not guides_enabled
                        or not st.session_state[f"{prefix}:center_show_ground_line"]
                    ),
                    help=(
                        "Coordenada local de la celda. El canvas recibe la posición absoluta "
                        "correspondiente al frame activo."
                    ),
                )
                anchor_col1, anchor_col2 = st.columns(2)
                anchor_col1.checkbox(
                    "Ancla corporal",
                    key=f"{prefix}:center_show_body_anchor_widget",
                    disabled=not guides_enabled,
                )
                anchor_col2.checkbox(
                    "Ancla objetivo",
                    key=f"{prefix}:center_show_target_anchor_widget",
                    disabled=not guides_enabled,
                )
                st.checkbox(
                    "Mostrar Δ del ancla",
                    key=f"{prefix}:center_show_anchor_delta_widget",
                    disabled=not guides_enabled,
                )
                anchor_delta_x = current_anchor_x - target_anchor_x
                anchor_delta_y = current_anchor_y - target_anchor_y
                st.caption(
                    f"Actual `{current_anchor_x:.1f}, {current_anchor_y:.1f}` · "
                    f"Objetivo `{target_anchor_x:.1f}, {target_anchor_y:.1f}` · "
                    f"Δ `{anchor_delta_x:+.1f}, {anchor_delta_y:+.1f}`"
                )
                note_key = f"{prefix}:note:{selected}"
                if note_key not in st.session_state:
                    st.session_state[note_key] = str(notes[selected])
                st.text_area(
                    "Notas",
                    key=note_key,
                )
                st.write(
                    f"Auto anchor: `{adjustment.auto_anchor[0]:.2f}, "
                    f"{adjustment.auto_anchor[1]:.2f}`"
                )
                st.write(f"Confianza: `{adjustment.auto_confidence:.2%}`")
                if sync_widgets:
                    st.session_state[f"{prefix}:center_widget_sync"] = False
                else:
                    widget_offset = (
                        int(st.session_state[x_widget_key]),
                        int(st.session_state[y_widget_key]),
                    )
                    if widget_offset != tuple(offsets[selected]):
                        offsets = list(offsets)
                        offsets[selected] = widget_offset
                        st.session_state[f"{prefix}:offsets"] = offsets
                        st.rerun()
                reset_col, copy_col = st.columns(2)
                if reset_col.button(
                    "Reset frame",
                    width="stretch",
                    key=f"{prefix}:reset:{selected}",
                ):
                    values = list(st.session_state[f"{prefix}:offsets"])
                    values[selected] = (0, 0)
                    st.session_state[f"{prefix}:offsets"] = values
                    for key in (
                        x_widget_key,
                        y_widget_key,
                    ):
                        st.session_state.pop(key, None)
                    st.rerun()
                if copy_col.button(
                    "Copiar a todos",
                    width="stretch",
                    key=f"{prefix}:copy:{selected}",
                ):
                    value = tuple(st.session_state[f"{prefix}:offsets"][selected])
                    st.session_state[f"{prefix}:offsets"] = [
                        value for _ in centered.frames
                    ]
                    for index in range(len(centered.frames)):
                        st.session_state.pop(f"{prefix}:offset_x_widget:{index}", None)
                        st.session_state.pop(f"{prefix}:offset_y_widget:{index}", None)
                    st.rerun()
            if st.button(
                "Guardar overrides",
                type="primary",
                key=f"{prefix}:save_overrides",
            ):
                _ensure_adjustment_state(session, len(background_frames))
                requested_offsets = list(st.session_state[f"{prefix}:offsets"])
                final_result = auto_center_frames(
                    background_frames,
                    center_config,
                    manual_offsets=requested_offsets,
                    locked=st.session_state[f"{prefix}:locks"],
                    notes=st.session_state[f"{prefix}:notes"],
                    overflow_strategy="clamp",
                )
                session.segmentation_config = segmentation_config
                session.background_removal_config = background_config
                session.auto_center_config = center_config
                store.commit_stage(
                    session,
                    "alignment",
                    final_result.frames,
                    config={
                        "segmentation": segmentation_config.to_dict(),
                        "background": background_config.to_dict(),
                        "auto_center": center_config.to_dict(),
                        "manual_offsets": requested_offsets,
                    },
                    status=final_result.status,
                    metrics=final_result.jitter_report,
                    metadata={
                        "frames": [item.to_dict() for item in final_result.adjustments]
                    },
                )
                store.save_adjustments(session, final_result.adjustments)
                st.success("Overrides guardados como una nueva revisión.")
        else:
            st.info("Completa el procesamiento automático antes del ajuste fino.")

    with export_tab:
        st.subheader("Export")
        if centered:
            prefix = session.session_id
            export_frames_source = centered.frames
            try:
                persisted_alignment_frames = _load_stage_frames(
                    store,
                    session,
                    "alignment",
                )
            except ArtifactIntegrityError as exc:
                st.warning(f"Alignment guardado inválido: {exc}")
                persisted_alignment_frames = ()
            if len(persisted_alignment_frames) == len(centered.frames):
                export_frames_source = persisted_alignment_frames
            if f"{prefix}:export_crop_enabled" not in st.session_state:
                st.session_state[f"{prefix}:export_crop_enabled"] = session.export_crop_config.enabled
            if f"{prefix}:export_crop_padding" not in st.session_state:
                st.session_state[f"{prefix}:export_crop_padding"] = session.export_crop_config.padding
            if f"{prefix}:export_crop_threshold" not in st.session_state:
                st.session_state[f"{prefix}:export_crop_threshold"] = session.export_crop_config.alpha_threshold
            if f"{session.session_id}:export_frames" not in st.session_state:
                st.session_state[f"{session.session_id}:export_frames"] = True
            if f"{session.session_id}:export_contact" not in st.session_state:
                st.session_state[f"{session.session_id}:export_contact"] = True
            if f"{session.session_id}:export_gif" not in st.session_state:
                st.session_state[f"{session.session_id}:export_gif"] = False
            if f"{session.session_id}:fps" not in st.session_state:
                st.session_state[f"{session.session_id}:fps"] = 8.0
            if f"{session.session_id}:export_columns" not in st.session_state:
                st.session_state[f"{session.session_id}:export_columns"] = min(4, len(centered.frames))
            export_col, preview_col = st.columns((1, 1.45), gap="large")
            with export_col, st.container(border=True):
                layout = st.selectbox(
                    "Layout de salida",
                    ("horizontal", "vertical", "grid"),
                    key=f"{session.session_id}:export_layout",
                )
                export_crop_enabled_key = f"{prefix}:export_crop_enabled"
                export_crop_padding_key = f"{prefix}:export_crop_padding"
                export_crop_threshold_key = f"{prefix}:export_crop_threshold"
                export_crop_enabled = st.checkbox(
                    "Recorte inteligente",
                    key=export_crop_enabled_key,
                    help="Recorta la unión transparente compartida por todos los frames.",
                )
                export_crop_padding = int(
                    st.slider(
                        "Padding crop",
                        min_value=0,
                        max_value=max(0, min(canvas_width, canvas_height) // 2),
                        disabled=not export_crop_enabled,
                        key=export_crop_padding_key,
                    )
                )
                export_crop_threshold = int(
                    st.slider(
                        "Umbral alpha",
                        min_value=0,
                        max_value=255,
                        disabled=not export_crop_enabled,
                        key=export_crop_threshold_key,
                    )
                )
                session.export_crop_config = ExportCropConfig(
                    enabled=export_crop_enabled,
                    padding=export_crop_padding,
                    alpha_threshold=export_crop_threshold,
                )
                export_columns = (
                    int(
                        st.number_input(
                            "Columnas de grid",
                            min_value=1,
                            max_value=len(centered.frames),
                            key=f"{session.session_id}:export_columns",
                        )
                    )
                    if layout == "grid"
                    else None
                )
                include_frames = st.checkbox(
                    "Exportar frames individuales",
                    key=f"{session.session_id}:export_frames",
                )
                include_contact = st.checkbox(
                    "Exportar contact/anchor sheet",
                    key=f"{session.session_id}:export_contact",
                )
                include_gif = st.checkbox(
                    "Exportar preview GIF",
                    key=f"{session.session_id}:export_gif",
                )
                fps = float(
                    st.number_input(
                        "FPS del GIF",
                        min_value=1.0,
                        max_value=60.0,
                        disabled=not include_gif,
                        key=f"{session.session_id}:fps",
                    )
                )
                review_count = sum(
                    item.manual_review for item in centered.adjustments
                )
                if review_count:
                    st.info(
                        f"{review_count} frame(s) siguen marcados como revisión, "
                        "pero la exportación ya no está bloqueada."
                    )
                preview_crop, preview_crop_warning = _safe_trim_transparent_frames(
                    export_frames_source,
                    session.export_crop_config,
                )
                if preview_crop_warning:
                    st.warning(
                        "El preview de crop usa un fallback porque los frames tienen "
                        "tamaños distintos. La exportación seguirá usando el canvas de cada frame."
                    )
                if st.button(
                    "Exportar sprite .png",
                    type="primary",
                    width="stretch",
                    key=f"{session.session_id}:export",
                ):
                    session.segmentation_config = segmentation_config
                    session.background_removal_config = background_config
                    session.auto_center_config = center_config
                    session.frame_adjustments = list(centered.adjustments)
                    store.save(session)
                    manifest = store.export(
                        session,
                        export_frames_source,
                        layout=layout,
                        columns=export_columns,
                        export_frames=include_frames,
                        export_contact_sheet=include_contact,
                        export_gif=include_gif,
                        fps=fps,
                    )
                    st.session_state[f"{session.session_id}:last_export"] = manifest
                    st.success("Exportación terminada y manifest guardado.")
                manifest = st.session_state.get(
                    f"{session.session_id}:last_export",
                    session.export_manifest,
                )
                if manifest:
                    png_path = workspace / manifest["output_png"]
                    if png_path.is_file():
                        st.download_button(
                            "Descargar sprite-sheet PNG",
                            data=png_path.read_bytes(),
                            file_name=png_path.name,
                            mime="image/png",
                            width="stretch",
                        )
                    st.download_button(
                        "Descargar manifest JSON",
                        data=json.dumps(
                            manifest,
                            indent=2,
                            ensure_ascii=False,
                        ),
                        file_name="sprite-sheet.manifest.json",
                        mime="application/json",
                        width="stretch",
                    )
            with preview_col:
                guide_col, axis_col, anchor_col = st.columns(3)
                show_export_cell_guides = guide_col.checkbox(
                    "Cortes",
                    value=True,
                    key=f"{prefix}:export_preview_cell_guides",
                )
                show_export_axes = axis_col.checkbox(
                    "Ejes XY",
                    value=True,
                    key=f"{prefix}:export_preview_axes",
                )
                show_export_anchors = anchor_col.checkbox(
                    "Anchors",
                    value=True,
                    key=f"{prefix}:export_preview_anchors",
                )
                _show_pixel(
                    render_contact_sheet(
                        preview_crop.frames,
                        adjustments=centered.adjustments,
                        columns=min(6, len(centered.frames)),
                        origin_offset=(preview_crop.bbox[0], preview_crop.bbox[1]),
                        show_cell_guides=show_export_cell_guides,
                        show_center_axes=show_export_axes,
                        show_anchor_guides=show_export_anchors,
                        show_bbox=False,
                        guide_padding=8
                        if (
                            show_export_cell_guides
                            or show_export_axes
                            or show_export_anchors
                        )
                        else 0,
                    ),
                    "Preview final con anchors y recorte",
                    max_height=640,
                )
        else:
            st.info("No hay frames centrados para exportar.")

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Workspace: {workspace}")
    st.sidebar.caption("Procesamiento local · sin APIs externas")


if __name__ == "__main__":
    main()
