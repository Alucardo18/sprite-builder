from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any

from PIL import Image

from sprite_builder.ui import components

COMPONENT_HTML = (
    Path(components.__file__).parent / "pixel_editor_component" / "index.html"
)
TILESET_COMPONENT_HTML = (
    Path(components.__file__).parent / "tileset_editor_component" / "index.html"
)
UI_APP = Path(components.__file__).resolve().parent / "app.py"


def _component_source() -> str:
    return COMPONENT_HTML.read_text(encoding="utf-8")


def _ui_app_source() -> str:
    return UI_APP.read_text(encoding="utf-8")


def test_tileset_editor_forwards_grid_contract(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_component(**kwargs: Any) -> None:
        captured.update(kwargs)
        return None

    monkeypatch.setattr(components, "_TILESET_EDITOR", fake_component)
    components.tileset_editor(
        Image.new("RGBA", (48, 32)),
        image_token="atlas-v1",
        tile_size=12,
        offset_x=2,
        offset_y=3,
        spacing_x=1,
        spacing_y=2,
        key="tileset-contract",
    )

    assert captured["imageToken"] == "atlas-v1"
    assert captured["tileSize"] == 12
    assert captured["offsetX"] == 2
    assert captured["offsetY"] == 3
    assert captured["spacingX"] == 1
    assert captured["spacingY"] == 2


def test_tileset_canvas_has_pixel_tools_grid_and_seamless_preview() -> None:
    source = TILESET_COMPONENT_HTML.read_text(encoding="utf-8")
    studio_source = _component_source()

    for tool in (
        "wand",
        "pencil",
        "eraser",
        "eyedropper",
        "move",
        "fill",
        "replace_color",
        "crop_lasso",
        "crop_rect",
        "crop_ellipse",
        "select_lasso",
        "select_rect",
        "select_ellipse",
    ):
        assert f'data-tool="{tool}"' in source
    for action in (
        "flip-horizontal",
        "flip-vertical",
        "rotate-cw",
        "scale-2x",
        "scale-half",
        "outline",
        "cleanup-isolated",
    ):
        assert f'data-pixel-action="{action}"' in source
    assert 'id="undo"' in source
    assert 'id="redo"' in source
    assert 'id="tileSize"' in source
    assert 'id="seamless"' in source
    assert 'id="toggleGrid"' in source
    assert 'id="magnetCrop"' in source
    assert 'Imán de recorte · ${state.magnetCrop ? "ON" : "OFF"}' in source
    assert "button:hover { border-color" in source
    assert "button:hover, button.active" not in source
    assert 'id="hexColor"' in source
    assert 'id="brushCard"' in source
    assert 'id="brushRange"' in source
    assert "? state.brush" in source
    assert "brushY < size" in source
    assert "brushX < size" in source
    assert 'state.tool !== "pencil" && state.tool !== "eraser"' in source
    assert 'event.target.closest("#brushCard")' in source
    assert "target instanceof HTMLInputElement" in source
    assert 'id="wandToleranceNumber"' in source
    assert 'id="wandToleranceRange"' in source
    assert 'id="wandContiguous"' in source
    assert 'imageSmoothingEnabled = false' in source
    assert "floodFill" in source
    assert "magicWand" in source
    assert "state.wandTolerance * state.wandTolerance" in source
    assert "state.wandContiguous" in source
    assert 'w: "wand"' in source
    assert "replaceColor" in source
    assert "commitShape" in source
    assert "prepareMoveSnapshot" in source
    assert "applyPixelAction" in source
    assert "deleteSelection" in source
    assert "selectAll" in source
    assert "magneticCropPoint" in source
    assert "snapAxisToTile" in source
    assert 'edge === "end" ? [start + state.tileSize - 1] : [start]' in source
    assert 'magneticCropPoint(rawPoint, "start")' in source
    assert 'magneticCropPoint(rawPoint, "end")' in source
    assert 'const usesPath = state.tool.endsWith("lasso")' in source
    assert 'document.addEventListener("pointerup"' in source
    assert 'if (isCropTool(state.tool) && !state.shapeMoved)' in source
    assert "const cutForMove = isCropTool(state.tool)" in source
    assert "state.selectionBounds = bounds" in source
    assert 'setTool("move")' in source
    assert 'emitImage("crop")' not in source
    assert '<use href="#icon-flip-horizontal"></use>' in source
    assert '<use href="#icon-flip-vertical"></use>' in source
    assert "stageResizeObserver.observe(stage)" in source
    assert 'input.addEventListener("input", commitGridInput)' in source
    assert 'dataType: "json"' in source
    assert 'addEventListener("mousedown"' not in source
    assert 'addEventListener("mousemove"' not in source


def test_tileset_brush_card_is_owned_by_the_paint_tool_group() -> None:
    source = TILESET_COMPONENT_HTML.read_text(encoding="utf-8")
    studio_source = _component_source()

    tool_group = re.search(
        r'<div class="group tool-group">([\s\S]*?)\n\s*</div>\n\s*<div class="group">',
        source,
    )
    assert tool_group
    assert 'id="brushCard"' in tool_group.group(1)
    assert 'data-tool="pencil"' in tool_group.group(1)
    assert 'data-tool="eraser"' in tool_group.group(1)
    for icon in (
        "eyedropper",
        "pencil",
        "move",
        "eraser",
        "lasso",
        "rect",
        "ellipse",
        "zoom-in",
        "zoom-out",
        "fit",
        "undo",
        "redo",
    ):
        symbol = re.search(
            rf'<symbol id="icon-{re.escape(icon)}".*?</symbol>',
            studio_source,
        )
        assert symbol is not None
        assert symbol.group(0) in source


def test_both_editors_refit_when_their_container_width_changes() -> None:
    pixel_source = _component_source()
    tileset_source = TILESET_COMPONENT_HTML.read_text(encoding="utf-8")

    assert "responsiveFitObserver.observe(stage)" in pixel_source
    assert "setZoom(computeFitZoom(), false)" in pixel_source
    assert "stageResizeObserver.observe(stage)" in tileset_source
    assert "state.fitResponsive" in tileset_source


def test_pixel_editor_forwards_manual_guide_contract(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_component(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"type": "noop"}

    monkeypatch.setattr(components, "_PIXEL_EDITOR", fake_component)
    result = components.pixel_editor(
        Image.new("RGBA", (16, 12)),
        tool="drag",
        mode="segmentation-center",
        paint_color=(12, 34, 56, 255),
        show_guides=True,
        guide_opacity=0.45,
        show_cell_center=False,
        show_frame_guide=False,
        show_ground_line=True,
        ground_line_y=9,
        current_anchor_x=7.5,
        current_anchor_y=6.25,
        target_anchor_x=8,
        target_anchor_y=7,
        show_anchor_delta=True,
        key="guide-contract",
    )

    assert result == {"type": "noop"}
    assert captured["showGuides"] is True
    assert captured["guideOpacity"] == 0.45
    assert captured["showCellCenter"] is False
    assert captured["showFrameGuide"] is False
    assert captured["showGroundLine"] is True
    assert captured["groundLineY"] == 9
    assert captured["currentAnchorX"] == 7.5
    assert captured["currentAnchorY"] == 6.25
    assert captured["targetAnchorX"] == 8
    assert captured["targetAnchorY"] == 7
    assert captured["showAnchorDelta"] is True
    assert captured["paintColor"] == (12, 34, 56, 255)


def test_pixel_editor_forwards_the_layer_frame_matrix(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_component(**kwargs: Any) -> None:
        captured.update(kwargs)
        return None

    monkeypatch.setattr(components, "_PIXEL_EDITOR", fake_component)
    components.pixel_editor(
        Image.new("RGBA", (16, 12)),
        tool="pencil",
        mode="layer-edit",
        studio_layers=(
            {
                "layerId": "retouch",
                "name": "Retoque",
                "visible": True,
                "locked": False,
                "cels": (True, True, False),
            },
        ),
        active_layer_id="retouch",
        active_frame=1,
        frame_count=3,
        key="studio-contract",
    )

    assert captured["studioLayers"] == [
        {
            "layerId": "retouch",
            "name": "Retoque",
            "visible": True,
            "locked": False,
            "cels": (True, True, False),
        }
    ]
    assert captured["activeLayerId"] == "retouch"
    assert captured["activeFrame"] == 1
    assert captured["frameCount"] == 3


def test_pixel_editor_guide_defaults_are_backward_compatible() -> None:
    signature = inspect.signature(components.pixel_editor)

    assert signature.parameters["show_guides"].default is False
    assert signature.parameters["guide_opacity"].default == 0.7
    assert signature.parameters["show_cell_center"].default is True
    assert signature.parameters["show_frame_guide"].default is True
    assert signature.parameters["show_ground_line"].default is False
    assert signature.parameters["ground_line_y"].default is None
    assert signature.parameters["current_anchor_x"].default is None
    assert signature.parameters["current_anchor_y"].default is None
    assert signature.parameters["target_anchor_x"].default is None
    assert signature.parameters["target_anchor_y"].default is None
    assert signature.parameters["show_anchor_delta"].default is True
    assert signature.parameters["frame_token"].default == ""
    assert signature.parameters["cut_positions"].default is None
    assert signature.parameters["allow_cut_drag"].default is False


def test_component_receives_every_manual_guide_prop() -> None:
    source = _component_source()

    for prop in (
        "guideOpacity",
        "showCellCenter",
        "showFrameGuide",
        "showGroundLine",
        "groundLineY",
        "currentAnchorX",
        "currentAnchorY",
        "targetAnchorX",
        "targetAnchorY",
        "showAnchorDelta",
        "frameToken",
        "cutPositions",
        "allowCutDrag",
    ):
        assert f'"{prop}"' in source, f"{prop} is not read from Streamlit render args"
        assert re.search(rf"\bstate\.{prop}\b", source), (
            f"{prop} is received but is not part of component state"
        )


def test_center_canvas_uses_a_stable_component_key() -> None:
    source = _ui_app_source()

    assert 'if st.button(\n                "Fijar frame",' in source
    assert 'key=f"{prefix}:center_pixel_editor"' in source
    assert 'key=f"{prefix}:center_pixel_editor:{selected}"' not in source
    assert "frame_token=(" in source
    assert "preview_source = centered" in source


def test_sheet_canvas_exposes_free_adjust_controls() -> None:
    source = _ui_app_source()

    assert '"Cortes automáticos"' in source
    assert '"Ajuste manual"' in source
    assert 'mode="segmentation-cut"' in source
    assert 'cut_positions=st.session_state[f"{prefix}:segmentation_cut_positions"]' in source
    assert 'segmentation_free_adjust_widget' in source
    assert 'cut_positions_x=st.session_state.get(' in source
    assert 'cut_positions_y=st.session_state.get(' in source
    assert source.index('free_adjust_enabled =') < source.index('mode="segmentation-cut"')


def test_cut_canvas_supports_vertical_and_horizontal_handles() -> None:
    source = _component_source()

    assert "cutPositionsX" in source
    assert "cutPositionsY" in source
    assert 'cut-boundary${axis === "y" ? " horizontal" : ""}' in source
    assert 'cursor: row-resize' in source
    assert 'cutAxis: state.cutDraggingAxis' in source


def test_cut_drag_only_syncs_with_streamlit_when_the_drag_ends() -> None:
    source = _component_source()

    pointer_move = source[source.index('document.addEventListener("pointermove"') :]
    pointer_move = pointer_move[: pointer_move.index('document.addEventListener("pointerup"')]
    assert "updateCutGhostPosition(" in pointer_move
    assert "commitCutPosition(" not in pointer_move
    assert "emitCutState(" not in pointer_move
    assert 'emitCutState(event, "end", positionsForAxis)' in source
    assert "state.cutCommitPending = {" in source
    assert "pendingAcknowledged" in source
    assert "pendingExpired" in source


def test_sheet_cut_commit_immediately_reruns_with_confirmed_state() -> None:
    source = _ui_app_source()

    handler = source[source.index("changed = _handle_segmentation_cut_event(") :]
    handler = handler[: handler.index("else:\n            with st.container", 1)]
    assert 'event.get("type") == "cut"' in handler
    assert 'event.get("action") == "end"' in handler
    assert "st.rerun()" in handler


def test_cut_drag_uses_a_transient_half_opacity_ghost() -> None:
    source = _component_source()

    assert "const guideOverlayVisible = cutMode || (centerMode && state.showGuides)" in source
    assert 'guides.style.opacity = cutMode\n          ? "1"' in source
    assert 'guides.style.opacity = state.mode === "segmentation-cut"\n          ? "1"' in source
    assert ".cut-boundary.ghost" in source
    assert "background: rgba(255, 196, 91, 0.5)" in source
    assert "width: 3px" in source
    assert ".cut-ghost-label" in source
    assert 'label.textContent = `${axis.toUpperCase()} ${clamped}px`' in source
    assert 'ghost.className = `cut-boundary ghost${axis === "y" ? " horizontal" : ""}`' in source
    assert "state.cutGhostPosition = clamped" in source
    assert "removeCutGhost();" in source
    assert "endCutDrag(event, false);" in source


def test_pixel_editor_toolbar_uses_svg_icons_and_accessible_names() -> None:
    source = _component_source()

    for icon in (
        "icon-wand",
        "icon-eyedropper",
        "icon-eraser",
        "icon-zoom-in",
        "icon-zoom-out",
        "icon-fit",
        "icon-pencil",
        "icon-move",
    ):
        assert f'id="{icon}"' in source
    assert 'aria-label="Acercar"' in source
    assert 'aria-label="Alejar"' in source
    assert 'title="Varita (W)"' in source
    assert "[hidden] {\n        display: none !important;" in source


def test_pixel_editor_supports_layer_edit_tools_and_events() -> None:
    source = _component_source()

    assert 'mode === "layer-edit"' in source
    assert 'data-tool="pencil"' in source
    assert 'data-tool="move"' in source
    assert 'type: "edit-batch"' in source
    assert "pendingEdits" in source
    assert "previewStroke" in source
    assert 'color: state.paintColor' in source
    assert "drawPendingEdits();" in source
    assert "imageUrl === state.imageUrl ? state.image : loadImage(imageUrl)" in source
    assert 'state.mode === "layer-edit"' in source
    assert "state.moveBase" in source


def test_pixel_editor_supports_studio_crop_tools() -> None:
    source = _component_source()
    app_source = _ui_app_source()

    for tool in ("crop_lasso", "crop_rect", "crop_ellipse"):
        assert f'data-tool="{tool}"' in source
        assert f'nextTool === "{tool}"' in source
        assert f'"{tool}"' in app_source
    assert 'type: isSelectionTool(state.tool) ? "selection" : "crop"' in source
    assert "drawCropPreview" in source
    assert "emitCrop" in source
    assert "isShapeTool(state.tool)" in source
    assert "_extract_layer_piece(image, mask)" in app_source
    assert 'layer_editor_floating_selection' in app_source
    assert 'type: "floating-transform"' in source
    assert "drawFloatingSelection" in source
    assert "floating_selection=floating_piece" in app_source
    assert "_layer_crop_mask_from_event" in app_source
    assert "_crop_target_layer_id" in app_source
    assert "_opaque_crop_mask" in app_source


def test_studio_timeline_selects_cels_and_reorders_layers() -> None:
    source = _component_source()

    assert 'emitStudio("select-layer"' in source
    assert 'emitStudio("select-cel"' in source
    assert 'emitStudio("reorder-layer"' in source
    assert 'row.draggable = state.studioLayers.length > 1' in source
    assert 'button.timeline-cel' in source


def test_layer_eyedropper_accepts_the_canvas_click_event() -> None:
    source = _ui_app_source()

    assert 'event_type in {"pointer", "pointerdown"} and tool == "eyedropper"' in source
    assert 'layer_editor_color_picker_sync' in source


def test_component_events_do_not_force_a_second_streamlit_rerun() -> None:
    source = _ui_app_source()

    for handler in (
        "_handle_segmentation_cut_event",
        "_handle_background_editor_event",
        "_handle_center_editor_event",
    ):
        start = source.index(f"changed = {handler}")
        window = source[start : start + 500]
        assert "st.rerun()" not in window

    # Crop and cancel need an immediate refresh so the component receives the
    # temporary floating selection instead of a stale flattened canvas.
    assert '"selection-command",' in source
    assert '"floating-selection",' in source


def test_background_editor_keeps_zoom_and_tools_in_the_canvas_toolbar() -> None:
    source = _ui_app_source()
    component_source = _component_source()

    assert '"Zoom 100%"' not in source
    assert '"Modo editor ancho"' not in source
    assert '"Lienzo amplio"' in source
    for tool in ("crop_lasso", "crop_rect", "crop_ellipse"):
        assert f'"{tool}"' in source
    assert "toolCropLasso.hidden = centerMode || cutMode" in component_source
    assert "toolCropRect.disabled = centerMode || cutMode" in component_source
    assert '(state.mode === "layer-edit" || state.mode === "background") && isShapeTool(state.tool)' in component_source
    assert 'event_type == "crop"' in source
    assert "incoming = _layer_crop_mask_from_event(" in source
    assert ":background_floating_selection" in source
    assert '"kind": "move_mask"' in source
    assert "floating_selection=floating_piece" in source
    assert 'state.mode === "background" && state.floatingSelection' in component_source
    assert 'type: "floating-transform"' in component_source
    assert "toolMove.hidden = centerMode || cutMode" in component_source
    assert '"Mover selección (haz un recorte primero)"' in component_source


def test_magic_wand_opens_a_color_tolerance_card_in_the_canvas_toolbar() -> None:
    source = _component_source()
    app_source = _ui_app_source()

    assert 'id="wand-card"' in source
    assert 'role="dialog" aria-label="Ajustes de la varita"' in source
    assert 'id="wand-tolerance-range" type="range" min="0" max="255"' in source
    assert 'id="wand-tolerance-number" type="number" min="0" max="255"' in source
    assert "0</strong> selecciona estrictamente el mismo color" in source
    assert 'action: "wand-settings"' in source
    assert "wandTolerance: state.wandTolerance" in source
    assert "wandContiguous: state.wandContiguous" in source
    assert 'if (tool === "wand")' in source
    assert "setWandCardOpen(true)" in source
    assert 'event.key === "Enter"' in source
    assert 'f"{prefix}:background_wand_tolerance"' in app_source
    assert 'f"{prefix}:background_wand_contiguous"' in app_source
    assert 'str(event.get("action", "")) == "wand-settings"' in app_source


def test_pixel_editor_forwards_magic_wand_settings(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_component(**kwargs: Any) -> None:
        captured.update(kwargs)
        return None

    monkeypatch.setattr(components, "_PIXEL_EDITOR", fake_component)
    components.pixel_editor(
        Image.new("RGBA", (8, 8)),
        tool="wand",
        wand_tolerance=37,
        wand_contiguous=False,
        key="wand-settings",
    )

    assert captured["wandTolerance"] == 37
    assert captured["wandContiguous"] is False


def test_cut_canvas_exposes_zoom_and_fit_controls() -> None:
    source = _component_source()

    assert 'id="zoom-out-cut"' in source
    assert 'id="zoom-in-cut"' in source
    assert 'id="fit-cut"' in source
    assert 'id="zoom-pill-cut"' in source


def test_center_canvas_persists_state_per_frame_token() -> None:
    source = _component_source()

    assert "frameStateByToken" in source
    assert "captureFrameState" in source
    assert "restoreFrameState" in source
    assert "activeFrameToken" in source
    assert "frameToken" in source


def test_manual_anchor_guides_keep_target_fixed_and_move_current_with_offset() -> None:
    source = _component_source()

    current_position = re.search(
        r"function\s+currentAnchorPosition\(\)\s*\{([\s\S]*?)\n\s{6}\}",
        source,
    )
    assert current_position, "current anchor screen geometry must be explicit"
    assert "state.offsetX" in current_position.group(1)
    assert "state.offsetY" in current_position.group(1)
    target_geometry = re.search(
        r"setPointGeometry\(\s*guideTargetAnchor,\s*([^,]+),\s*([^)]+)\)",
        source,
    )
    assert target_geometry, "target anchor screen geometry must be explicit"
    assert "targetAnchorX" in target_geometry.group(1)
    assert "targetAnchorY" in target_geometry.group(2)
    assert "offsetX" not in target_geometry.group(1)
    assert "offsetY" not in target_geometry.group(2)


def test_manual_anchor_delta_is_derived_from_current_and_target() -> None:
    source = _component_source()

    assert 'id="delta-pill"' in source
    delta_function = re.search(
        r"function\s+guideDelta\(\)\s*\{([\s\S]*?)\n\s{6}\}",
        source,
    )
    assert delta_function
    assert "currentAnchor.x" in delta_function.group(1)
    assert "state.targetAnchorX" in delta_function.group(1)
    assert "currentAnchor.y" in delta_function.group(1)
    assert "state.targetAnchorY" in delta_function.group(1)
    assert re.search(r"if\s*\(state\.showAnchorDelta\s*&&\s*currentAnchor", source)


def test_guide_opacity_is_clamped_and_applied() -> None:
    source = _component_source()

    opacity_assignment = re.search(
        r"state\.guideOpacity\s*=\s*([^;]+);",
        source,
    )
    assert opacity_assignment
    assert "Math.max" in opacity_assignment.group(1)
    assert "Math.min" in opacity_assignment.group(1)
    assert re.search(
        r"guides\.style\.setProperty\(\s*[\"']--guide-opacity[\"']"
        r",\s*String\(state\.guideOpacity\)\s*\)",
        source,
    )


def test_arrow_hotkeys_nudge_one_pixel_or_five_with_shift() -> None:
    source = _component_source()

    for key in ("arrowleft", "arrowright", "arrowup", "arrowdown"):
        assert key in source.lower()
    assert re.search(
        r"(?:nudge|step)\s*=\s*event\.shiftKey\s*\?\s*5\s*:\s*1",
        source,
    )
    assert re.search(
        r"setObjectOffset\([^;]*state\.offsetX[^;]*state\.offsetY",
        source,
    )
    assert re.search(
        r"\[[^\]]*[\"']arrowleft[\"'][^\]]*\]\.includes\(key\)"
        r"[\s\S]{0,800}?event\.preventDefault\(\)",
        source,
        re.IGNORECASE,
    )


def test_component_guide_layer_changes_are_published_for_persistence() -> None:
    source = _component_source()

    target_listener = re.search(
        r'guideTargetLayer\.addEventListener\("change",\s*\(\)\s*=>\s*\{'
        r"([\s\S]*?)\n\s{6}\}\);",
        source,
    )
    ground_listener = re.search(
        r'guideGroundLayer\.addEventListener\("change",\s*\(\)\s*=>\s*\{'
        r"([\s\S]*?)\n\s{6}\}\);",
        source,
    )
    frame_listener = re.search(
        r'guideFrameLayer\.addEventListener\("change",\s*\(\)\s*=>\s*\{'
        r"([\s\S]*?)\n\s{6}\}\);",
        source,
    )
    assert target_listener and "toggle-cell-center" in target_listener.group(1)
    assert ground_listener and "toggle-ground-line" in ground_listener.group(1)
    assert frame_listener and "toggle-frame-guide" in frame_listener.group(1)


def test_canvas_zoom_is_local_and_does_not_trigger_a_rerun() -> None:
    source = _component_source()

    assert source.count("setZoom(state.zoom + 1, false)") >= 1
    assert source.count("setZoom(state.zoom - 1, false)") >= 1
    emit_value = re.search(
        r"function\s+emitValue\(value\)\s*\{([\s\S]*?)\n\s{6}\}",
        source,
    )
    assert emit_value
    assert 'state.mode === "segmentation-center"' in emit_value.group(1)
    assert "zoom: state.zoom" in emit_value.group(1)


def test_component_coalesces_drag_redraws_and_cursor_updates() -> None:
    source = _component_source()

    assert "function scheduleDraw()" in source
    assert "drawFrameId = requestAnimationFrame" in source
    assert "function scheduleCursorUpdate()" in source
    assert "cursorFrameId = requestAnimationFrame" in source
    assert "state.floatingSelectionY = nextY;\n            scheduleDraw();" in source
    assert "state.cropPath.push(point);\n            scheduleDraw();" in source


def test_component_ignores_stale_async_renders_and_optimistic_props() -> None:
    source = _component_source()

    assert "const renderId = ++latestRenderId" in source
    assert "await Promise.all([" in source
    assert "if (renderId !== latestRenderId)" in source
    for pending_state in (
        "transformCommitPending",
        "floatingTransformPending",
        "committedEditsPending",
        "studioSelectionPending",
        "studioOrderPending",
    ):
        assert f"state.{pending_state}" in source
    assert "transformAcknowledged" in source
    assert "floatingAcknowledged" in source
    assert "selectionAcknowledged" in source
    assert 'pendingTransform.mode === "segmentation-center"' in source
    assert "(args.overlay || null) !== pendingTransform.overlayUrl" in source
    assert "(args.image || null) !== pendingTransform.imageUrl" in source


def test_pending_edits_are_scoped_to_frame_and_layer_context() -> None:
    source = _component_source()

    assert "pendingEditsByContext" in source
    assert "function editContextKey(" in source
    assert "function switchPendingEditContext(nextContext)" in source
    assert "pendingEditsByContext.set(activeEditContext, {" in source
    assert "edits: state.pendingEdits.slice()" in source
    assert "redo: state.pendingRedoEdits.slice()" in source
    assert "switchPendingEditContext(editContextKey());" in source


def test_history_controls_support_server_and_pending_edit_undo_redo() -> None:
    source = _component_source()

    assert 'data-action="undo"' in source
    assert 'data-action="redo"' in source
    assert 'key === "z"' in source
    assert 'key === "y"' in source
    assert 'type: "history"' in source
    assert 'state.pendingRedoEdits.push(state.pendingEdits.pop())' in source
    assert 'state.pendingEdits.push(state.pendingRedoEdits.pop())' in source
    assert "state.canUndo = !!args.canUndo" in source
    assert "state.canRedo = !!args.canRedo" in source


def test_component_exposes_selection_clipboard_pixel_tools_and_local_playback() -> None:
    source = _component_source()
    app_source = _ui_app_source()

    for tool in ("select_lasso", "select_rect", "select_ellipse", "fill", "replace_color"):
        assert f'data-tool="{tool}"' in source
        assert f'"{tool}"' in app_source
    for action in ("copy", "cut", "paste", "select-all", "deselect"):
        assert f'"{action}"' in source
    assert 'type: "pixel-action"' in source
    assert 'data-pixel-action="scale-2x"' in source
    assert 'data-pixel-action="scale-half"' in source
    assert "event.shiftKey && state.lastStrokePoint" in source
    assert '"Bloquear transparencia"' in app_source
    assert '"Simetría horizontal"' in app_source
    assert "function nudgeObject(deltaX, deltaY)" in source
    assert "}, 80);" in source
    assert "function togglePlayback()" in source
    assert "state.animationFrames" in source
    assert "composite_document_frame(" in app_source
    assert 'f"{prefix}:studio_playback": False' not in app_source
    assert "if playback_enabled" not in app_source
    assert "animation_frames = tuple(" in app_source
    assert "clearTimeout(state.playbackTimer)" in source
    assert "if playback_fps != previous_fps:" in app_source
    assert "round(1000 / playback_fps)" in app_source
    assert "for _ in range(document.frame_count)" in app_source


def test_pointer_cancel_restores_the_local_transform_origin() -> None:
    source = _component_source()

    cancel = source[source.index('canvas.addEventListener("pointercancel"') :]
    cancel = cancel[: cancel.index('document.addEventListener("pointermove"')]
    assert "state.offsetX = state.dragOriginX" in cancel
    assert "state.offsetY = state.dragOriginY" in cancel
    assert "state.transformCommitPending = null" in cancel
    assert 'emitDrag({ button: 0' in cancel


def test_redraw_does_not_repeat_canvas_or_timeline_work() -> None:
    source = _component_source()

    redraw = source[source.index("function redraw()") : source.index("function pointerToPixel")]
    assert redraw.count("draw();") == 1
    assert "setActiveTool(state.tool, false)" in redraw
    assert "studioTimelineSignature" in source
    assert "if (!force && signature === studioTimelineSignature)" in source
    assert "cutGuidesSignature" in source
    assert "if (!force && signature === cutGuidesSignature)" in source
