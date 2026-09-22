from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PIL import Image

from sprite_builder.ui import app, components

COMPONENT_HTML = (
    Path(components.__file__).parent / "pixel_editor_component" / "index.html"
)
TILESET_COMPONENT_HTML = (
    Path(components.__file__).parent / "tileset_editor_component" / "index.html"
)
TERRAIN_STUDIO_HTML = (
    Path(components.__file__).parent
    / "terrain_pattern_studio_component"
    / "index.html"
)
UI_APP = Path(components.__file__).resolve().parent / "app.py"


def _component_source() -> str:
    return COMPONENT_HTML.read_text(encoding="utf-8")


def _ui_app_source() -> str:
    return UI_APP.read_text(encoding="utf-8")


def _json_payload_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


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


def test_terrain_pattern_studio_forwards_fragment_composer_contract(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_component(**kwargs: Any) -> None:
        captured.update(kwargs)
        return None

    monkeypatch.setattr(components, "_TERRAIN_PATTERN_STUDIO", fake_component)
    components.terrain_pattern_studio(
        Image.new("RGBA", (48, 32)),
        pattern_image=Image.new("RGBA", (64, 48)),
        image_token="atlas-v2",
        tile_size=(16, 8),
        offset=(2, 3),
        spacing=(1, 2),
        kind="blob_47",
        roles=[{"index": 0, "mask": 0, "neighbors": [], "sourceIndex": None}],
        project={
            "version": 3,
            "sources": [{"id": "center", "x": 0, "y": 0, "width": 8, "height": 8}],
            "tiles": [],
            "sets": [],
        },
        set_previews=[
            {
                "id": "set-1",
                "image": Image.new("RGBA", (64, 48)),
                "roles": [{"mask": 0}],
            }
        ],
        key="pattern-contract",
    )

    assert captured["imageToken"] == "atlas-v2"
    assert captured["tileWidth"] == 16
    assert captured["tileHeight"] == 8
    assert captured["offsetX"] == 2
    assert captured["offsetY"] == 3
    assert captured["spacingX"] == 1
    assert captured["spacingY"] == 2
    assert captured["kind"] == "blob_47"
    assert captured["roles"][0]["sourceIndex"] is None
    assert captured["project"]["sources"][0]["id"] == "center"
    assert captured["setPreviews"][0]["image"].startswith("data:image/png;base64,")
    assert captured["patternImage"].startswith("data:image/png;base64,")


def test_terrain_pattern_studio_uses_tilesetter_set_view_flow() -> None:
    source = TERRAIN_STUDIO_HTML.read_text(encoding="utf-8")

    for copy in (
        "Set View",
        "Tile Properties",
        "Sources",
        "Importar grilla",
        "Build Borders · Blob",
        "Build Borders · Wang",
        "Selecciona exactamente 1 tile base completo",
        "Selecciona exactamente 2 tiles base completos",
        "1 · Tile base",
        "2 · Bordes",
        "3 · Corners",
        "Completar 4 por rotación",
        "Source + transformación + cutoff por orientación",
        "Ajustes avanzados",
        "Cutoff rápido · los 4 bordes",
        "Cutoff Wang · admite valores negativos",
        "Aplica la misma entrada del terreno a todos",
        "Composite automático",
        "Composite",
        "Custom",
        "Custom corners · opcionales",
        "Elegir desde Set View",
        "Usar composición automática",
        "Sandbox",
    ):
        assert copy in source
    assert 'startPick("edge"' in source
    assert 'startPick("corner"' in source
    assert 'id="cornerCompositeBoard"' in source
    assert '$("#cornerSection").hidden=false' in source
    assert 'set.kind==="wang_16"?-cutoffLimit:0' in source
    assert 'set.kind==="wang_16"?-Math.floor(axis/2):0' in source
    assert "Flip Y" in source
    assert "raw&&typeof raw===\"object\"?raw:{}" in source
    assert "sets:Array.isArray(raw?.sets)?raw.sets.map(cleanSet):[]" in source
    assert "set.autoOrientEdges=true" in source
    assert "set.autoOrientEdges?[\"top\",\"right\",\"bottom\",\"left\"]" in source
    assert "setRoleColumn(item)" in source
    assert "setRoleRow(item)" in source
    assert "role.setColumn??role.previewColumn" in source
    assert "role.setRow??role.previewRow" in source
    assert 'setCtx.fillStyle="rgba(255,199,109,.10)"' in source
    assert 'setCtx.fillStyle="rgba(4,8,14,.62)"' not in source
    assert "Composición: Base +" in source
    assert 'columns:kind==="blob_47"?11:4' in source
    assert 'rows:kind==="blob_47"?5:4' in source
    assert "Compositor de tile" not in source
    assert "Variantes generadas" not in source
    assert 'type:"project-change"' in source


def test_tileset_canvas_has_pixel_tools_grid_and_seamless_preview() -> None:
    source = TILESET_COMPONENT_HTML.read_text(encoding="utf-8")

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
        "crop_tile",
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
    assert 'Imán de recorte y movimiento · ${state.magnetCrop ? "ON" : "OFF"}' in source
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
    assert "magneticMoveDelta" in source
    assert "snapAxisToTile" in source
    assert "moveGridSnap" in source
    assert 'edge === "end" ? [start + state.tileSize - 1] : [start]' in source
    assert 'magneticCropPoint(rawPoint, "start")' in source
    assert 'magneticCropPoint(rawPoint, "end")' in source
    assert 'const { dx, dy } = magneticMoveDelta(rawDx, rawDy);' in source
    assert 'Desactivar ajuste magnético del recorte y movimiento' in source
    assert 'data-tool="crop_tile"' in source
    assert 'Recorte tile por tile (T)' in source
    assert 't: "crop_tile"' in source
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


def test_terrain_pattern_studio_exposes_sources_properties_and_sandbox() -> None:
    source = TERRAIN_STUDIO_HTML.read_text(encoding="utf-8")

    assert 'id="setCanvas"' in source
    assert 'id="sourceCanvas"' in source
    assert 'id="importGrid"' in source
    assert 'id="buildBlob"' in source
    assert 'id="buildWang"' in source
    assert 'id="edgeRows"' in source
    assert 'id="baseSourceSlot"' in source
    assert 'id="edgeBoard"' in source
    assert 'id="cornerAutoCard"' in source
    assert 'id="cornerRows"' in source
    assert 'id="pickBanner"' in source
    assert 'id="assignOverride"' in source
    assert 'id="compositeToggle"' in source
    assert 'id="sandboxCanvas"' in source
    assert 'type:"project-change"' in source
    assert "drawPatternRole" in source
    assert "roleForMapCell" in source


def test_terrain_pattern_studio_keeps_dom_ids_unique() -> None:
    source = TERRAIN_STUDIO_HTML.read_text(encoding="utf-8")
    ids = re.findall(r'\sid="([^"]+)"', source)

    assert len(ids) == len(set(ids))


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
    assert "setZoom(computeFitZoom(), true)" in pixel_source
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
        show_pixel_grid=True,
        pixel_grid_size=32,
        show_cell_center=False,
        show_frame_guide=False,
        show_column_guides=False,
        show_row_guides=True,
        grid_columns=4,
        grid_rows=3,
        show_ground_line=True,
        ground_line_y=9,
        current_anchor_x=7.5,
        current_anchor_y=6.25,
        target_anchor_x=8,
        target_anchor_y=7,
        show_anchor_delta=True,
        show_autocenter_all=True,
        active_frame=2,
        frame_count=4,
        frame_locks=(False, True, False, True),
        key="guide-contract",
    )

    assert result == {"type": "noop"}
    assert captured["showGuides"] is True
    assert captured["guideOpacity"] == 0.45
    assert captured["showPixelGrid"] is True
    assert captured["pixelGridSize"] == 32
    assert captured["showCellCenter"] is False
    assert captured["showFrameGuide"] is False
    assert captured["showColumnGuides"] is False
    assert captured["showRowGuides"] is True
    assert captured["gridColumns"] == 4
    assert captured["gridRows"] == 3
    assert captured["showGroundLine"] is True
    assert captured["groundLineY"] == 9
    assert captured["currentAnchorX"] == 7.5
    assert captured["currentAnchorY"] == 6.25
    assert captured["targetAnchorX"] == 8
    assert captured["targetAnchorY"] == 7
    assert captured["showAnchorDelta"] is True
    assert captured["showAutocenterAll"] is True
    assert captured["activeFrame"] == 2
    assert captured["frameCount"] == 4
    assert captured["frameLocks"] == [False, True, False, True]
    assert captured["paintColor"] == (12, 34, 56, 255)

    source = _component_source()
    assert 'data-action="autocenter-all"' in source
    assert 'action: "toggle-column-guides"' in source
    assert 'action: "toggle-row-guides"' in source
    assert "updateGridCenterLines(guideColumns, state.gridColumns, \"x\")" in source
    assert "updateGridCenterLines(guideRows, state.gridRows, \"y\")" in source
    assert 'type: "frame-selection"' in source
    assert "frameIndexAtPoint(point)" in source
    assert 'id="frame-context-menu"' in source
    assert 'key === "[" || key === "]"' in source
    assert 'id="visual-grid"' in source
    assert "state.pixelGridSize * state.zoom" in source


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


def test_pixel_editor_omits_animation_payload_until_frames_are_requested(monkeypatch) -> None:
    payloads: list[dict[str, Any]] = []

    def fake_component(**kwargs: Any) -> None:
        payloads.append(kwargs)
        return None

    monkeypatch.setattr(components, "_PIXEL_EDITOR", fake_component)
    base = Image.new("RGBA", (16, 16), (12, 34, 56, 255))
    components.pixel_editor(
        base,
        tool="pencil",
        mode="layer-edit",
        frame_count=4,
        animation_durations=(125, 125, 125, 125),
        key="animation-idle",
    )
    components.pixel_editor(
        base,
        tool="pencil",
        mode="layer-edit",
        frame_count=4,
        animation_frames=(
            base,
            Image.new("RGBA", base.size, (90, 80, 70, 255)),
            Image.new("RGBA", base.size, (70, 80, 90, 255)),
            Image.new("RGBA", base.size, (30, 40, 50, 255)),
        ),
        animation_durations=(125, 125, 125, 125),
        key="animation-requested",
    )

    idle, requested = payloads
    assert idle["animationFrames"] == []
    assert idle["animationDurations"] == []
    assert len(requested["animationFrames"]) == 4
    assert len(requested["animationDurations"]) == 4
    assert _json_payload_bytes(requested) - _json_payload_bytes(idle) > 100


def test_animation_payload_request_and_release_are_component_scoped(monkeypatch) -> None:
    session_state: dict[str, Any] = {}
    monkeypatch.setattr(app.st, "session_state", session_state)
    session = SimpleNamespace(session_id="session-a")
    document = SimpleNamespace(document_id="document-a")
    payload_key = "session-a:layer_editor_animation_payload:document-a"
    common = {
        "store": None,
        "session": session,
        "document": document,
        "images": {},
        "active_layer_id": "layer-a",
        "active_frame": 0,
        "target_frames": (0,),
        "composite": Image.new("RGBA", (2, 2)),
    }

    request = {
        "eventId": "animation-1",
        "type": "animation",
        "action": "request",
        "request": "play",
    }
    release = {"eventId": "animation-2", "type": "animation", "action": "release"}
    assert app._handle_layer_editor_event(event=request, **common) is True
    assert session_state[payload_key] is True
    assert app._handle_layer_editor_event(event=request, **common) is False
    assert app._handle_layer_editor_event(event=release, **common) is True
    assert session_state[payload_key] is False


def test_image_uri_cache_uses_digest_keys_and_deterministic_byte_eviction() -> None:
    cache = components._ByteBudgetImageUriCache(max_bytes=220)
    key_a = ("RGBA", (8, 8), 256, b"a" * 32)
    key_b = ("RGBA", (8, 8), 256, b"b" * 32)
    cache.put(key_a, "a" * 120)
    cache.put(key_b, "b" * 120)

    assert cache.info()["bytes"] <= 220
    assert cache.get(key_a) is None
    assert cache.get(key_b) == "b" * 120

    components._IMAGE_DATA_URI_CACHE.clear()
    image = Image.new("RGBA", (8, 8), (1, 2, 3, 255))
    components.image_data_uri(image)
    cache_keys = list(components._IMAGE_DATA_URI_CACHE._entries)
    assert len(cache_keys) == 1
    assert cache_keys[0][2] == len(image.tobytes())
    assert cache_keys[0][-1] != image.tobytes()
    assert (
        components._IMAGE_DATA_URI_CACHE.info()["bytes"]
        <= components._IMAGE_DATA_URI_CACHE_MAX_BYTES
    )


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

    assert re.search(r'if st\.button\(\s*"Guardar alineación",', source)
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
    handler = handler[: handler.index('st.markdown("#### Frames extraídos")')]
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


def test_pose_editor_owns_non_destructive_selection_and_move_tools() -> None:
    source = _ui_app_source()
    component_source = _component_source()

    assert '"Zoom 100%"' not in source
    assert '"Modo editor ancho"' not in source
    assert '"Lienzo amplio"' in source
    for tool in ("crop_lasso", "crop_rect", "crop_ellipse"):
        assert f'"{tool}"' in source
    assert 'aria-label="Rotar selección libremente"' in component_source
    assert 'id="rotate-angle-number" type="number" min="-180" max="180"' in component_source
    assert 'id="rotate-angle-range" type="range" min="-180" max="180"' in component_source
    assert 'action: "rotate-selection"' in component_source
    assert "degrees: state.rotateAngle" in component_source
    assert "function floatingRotationGeometry" in component_source
    assert "function pointHitsRotationHandle" in component_source
    assert "state.rotationDragging" in component_source
    assert "state.floatingRotationPreview = nextAngle" in component_source
    assert "context.rotate(previewAngle * Math.PI / 180)" in component_source
    assert "nextAngle = Math.round(nextAngle / 15) * 15" in component_source
    assert "ROTATE_CURSOR" in component_source
    assert "tirador exterior para rotar" in component_source
    assert "Ctrl/Cmd+C" in component_source
    assert "Ctrl/Cmd+V" in component_source
    assert 'aria-label="Copiar selección"' not in component_source
    assert 'aria-label="Pegar selección"' not in component_source
    assert "toolCropLasso.hidden = !(layerMode || poseMode || backgroundMode)" in component_source
    assert "toolCropRect.disabled = !(layerMode || poseMode || backgroundMode)" in component_source
    assert 'state.mode === "pose-layout"' in component_source
    assert 'mode="pose-layout"' in source
    assert ':pose_layout_tool' in source
    assert ':pose_selections' in source
    assert 'event_type == "crop"' in source
    assert "incoming = _layer_crop_mask_from_event(" in source
    assert ":background_floating_selection" in source
    assert ":background_clipboard" in source
    assert '"copy_mask"' in source
    assert 'str(event.get("action", "")) == "paste"' in source
    assert "floatingOperationKind=str(floating_operation_kind)" in inspect.getsource(
        components.pixel_editor
    )
    assert "operationKind: state.floatingOperationKind" in component_source
    assert "floating_selection=floating_piece" in source
    assert 'state.mode === "background" && state.floatingSelection' in component_source
    assert 'type: "floating-transform"' in component_source
    assert "toolMove.hidden = !(layerMode || poseMode || backgroundMode)" in component_source
    assert '"Mover selección (haz un recorte primero)"' in component_source


def test_floating_selection_resize_has_corner_handles_presets_and_grid_snap() -> None:
    component_source = _component_source()
    app_source = _ui_app_source()

    assert 'aria-label="Redimensionar selección"' in component_source
    for scale in ("0.75", "0.5", "0.25"):
        assert f'data-resize-scale="{scale}"' in component_source
    assert "function floatingResizeHandles" in component_source
    assert "function resizeHandleAtPoint" in component_source
    assert "function snapResizeEdge" in component_source
    assert "Math.min(1, 8 / Math.max(0.1, state.zoom))" in component_source
    assert "state.resizeFineMode" in component_source
    assert "state.resizeFineMode = !!event.altKey" in component_source
    assert "mantén Alt/Option para un ajuste preciso sin imán" in component_source
    assert "state.pixelGridSize" in component_source
    assert 'type: "floating-resize"' in component_source
    assert "scaleX:" in component_source
    assert "scaleY:" in component_source
    assert 'event_type == "floating-resize"' in app_source
    assert "Image.Resampling.NEAREST" in app_source
    assert 'layer_editor_floating_selection"] = selection' in app_source
    assert 'background_floating_selection"] = {' in app_source
    assert "Puedes moverla sin volver a seleccionarla" in app_source


def test_floating_selection_can_fit_alpha_bounds_to_active_grid_from_context_menu() -> None:
    component_source = _component_source()
    app_source = _ui_app_source()

    assert 'aria-label="Encajar selección al grid"' in component_source
    assert 'data-selection-action="fit-grid"' in component_source
    assert "function pointHitsFloatingSelection" in component_source
    assert "showSelectionContextMenu(event)" in component_source
    assert "function previewFitSelectionToGrid" in component_source
    assert "state.pixelGridSize || 16" in component_source
    assert "Math.ceil(requiredWidth / grid) * grid" in component_source
    assert "Math.ceil(requiredHeight / grid) * grid" in component_source
    assert "availableWidth / sourceWidth" in component_source
    assert "availableHeight / sourceHeight" in component_source
    assert 'fitGridAnchor.value || "top-left"' in component_source
    assert 'anchor === "bottom-center"' in component_source
    assert "state.fitGridTargetRect = targetRect" in component_source
    assert "fitGrid: fitGridAction" in component_source
    assert '"Encajar selección al grid"' in app_source


def test_context_menu_adjusts_selection_to_fill_nearest_grid_block() -> None:
    component_source = _component_source()
    app_source = _ui_app_source()

    assert 'data-selection-action="adjust-grid"' in component_source
    assert "function adjustSelectionToNearestGridBlock" in component_source
    assert "Math.round(sourceWidth / grid) * grid" in component_source
    assert "Math.round(sourceHeight / grid) * grid" in component_source
    assert "Math.min(targetWidth / sourceWidth, targetHeight / sourceHeight)" not in component_source
    assert "left: targetLeft," in component_source
    assert "top: targetTop," in component_source
    assert "right: targetLeft + targetWidth," in component_source
    assert "bottom: targetTop + targetHeight," in component_source
    assert 'state.resizeAction = "fit-grid-adjust"' in component_source
    assert 'fitGridMode = state.resizeAction === "fit-grid-adjust" ? "adjust"' in component_source
    assert "adjustSelectionToNearestGridBlock();" in component_source
    assert 'str(event.get("fitGridMode", "")) == "adjust"' in app_source
    assert '"Ajustar selección al grid"' in app_source


def test_selection_context_menu_covers_grid_edit_duplicate_and_existing_actions() -> None:
    source = _component_source()
    menu_start = source.index('id="selection-context-menu"')
    menu_end = source.index('id="studio-timeline"', menu_start)
    menu = source[menu_start:menu_end]

    for action in (
        "grid-position",
        "fit-grid-proportional",
        "align-grid",
        "adjust-grid",
        "fit-grid",
        "trim-visible",
        "toggle-repeat",
    ):
        assert f'data-selection-action="{action}"' in menu
    assert menu.count('data-selection-action="duplicate-grid"') == 4
    assert {
        match.group(1)
        for match in re.finditer(r'data-selection-action="duplicate-grid" data-direction="([^"]+)"', menu)
    } == {"left", "right", "up", "down"}
    assert menu.count("data-selection-align-anchor=") == 9
    assert 'data-selection-action="adjust-grid"' in menu
    assert 'data-selection-action="fit-grid"' in menu


def test_selection_context_actions_keep_resize_scale_and_bounds_contract() -> None:
    component_source = _component_source()
    app_source = _ui_app_source()

    position = component_source[
        component_source.index("function positionSelectionAtNearestGrid()") :
        component_source.index("function fitSelectionProportionallyToNearestGrid()")
    ]
    fit = component_source[
        component_source.index("function fitSelectionProportionallyToNearestGrid()") :
        component_source.index("function alignSelectionInsideNearestGrid(anchor)")
    ]
    align = component_source[
        component_source.index("function alignSelectionInsideNearestGrid(anchor)") :
        component_source.index("function emitFloatingSelectionAction(action")
    ]

    assert "Math.round(current.left / grid) * grid" in position
    assert "Math.round(current.top / grid) * grid" in position
    assert "}, 1);" in position
    assert "const uniformScale = Math.min(" in fit
    assert "const fittedWidth = sourceWidth * uniformScale" in fit
    assert "const fittedHeight = sourceHeight * uniformScale" in fit
    assert "}, uniformScale);" in fit
    assert "state.resizeScaleOverride === null" in component_source
    assert "data-selection-align-anchor" in component_source
    assert "}, 1);" in align
    assert "Image.Resampling.NEAREST" in app_source
    assert "Math.min(Math.max(0, state.width - targetWidth), Math.round(targetRect.left))" in component_source
    assert "Math.min(Math.max(0, state.height - targetHeight), Math.round(targetRect.top))" in component_source


def test_selection_repeat_preview_is_local_non_emitting_and_resets_without_selection() -> None:
    source = _component_source()
    toggle = source[
        source.index("function toggleRepeatPreview()") :
        source.index("function previewFitSelectionToGrid()")
    ]
    draw = source[
        source.index("if (state.floatingRepeatPreview) {") :
        source.index("context.drawImage(\n            state.floatingSelection", source.index("if (state.floatingRepeatPreview) {"))
    ]
    mode_ui = source[
        source.index("if ((!layerMode && !backgroundMode) || !state.floatingSelection)") :
        source.index("document.body.dataset.mode", source.index("if ((!layerMode && !backgroundMode) || !state.floatingSelection)"))
    ]

    assert "emitValue" not in toggle
    assert "for (const offsetY of [-1, 0, 1])" in draw
    assert "for (const offsetX of [-1, 0, 1])" in draw
    assert "if (!offsetX && !offsetY) continue" in draw
    assert "context.imageSmoothingEnabled = false" in source[: source.index("if (state.floatingRepeatPreview)")]
    assert "context.clip()" in draw
    assert "state.floatingRepeatPreview = false" in mode_ui
    assert "updateRepeatPreviewControl()" in mode_ui


def test_right_click_opens_selection_menu_without_committing_floating_transform() -> None:
    component_source = _component_source()
    pointerdown_handler = component_source.split(
        'canvas.addEventListener("pointerdown", (event) => {', 1
    )[1].split('canvas.addEventListener("pointermove", (event) => {', 1)[0]
    pointerup_handler = component_source.split(
        'canvas.addEventListener("pointerup", (event) => {', 1
    )[1].split('canvas.addEventListener("pointercancel", () => {', 1)[0]

    assert "state.dragging = event.button === 0;" in pointerdown_handler
    assert "if (!state.dragging)" in pointerdown_handler
    assert "if (event.button !== 0)" in pointerup_handler
    assert pointerup_handler.index("if (event.button !== 0)") < pointerup_handler.index(
        "emitFloatingTransform(event, point);"
    )


def test_adjust_resize_fills_both_target_grid_dimensions_without_alpha_padding() -> None:
    piece = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    for y in range(7, 42):
        for x in range(5, 59):
            piece.putpixel((x, y), (120, 160, 90, 255))

    bounds = app._alpha_tight_bounds(piece)
    assert bounds == (5, 7, 59, 42)
    resized = app._resize_floating_piece(
        piece,
        bounds,
        scale_x=48 / 54,
        scale_y=32 / 35,
    )
    resized_bounds = app._alpha_tight_bounds(resized)

    assert resized_bounds == (5, 7, 53, 39)
    assert resized_bounds[2] - resized_bounds[0] == 48
    assert resized_bounds[3] - resized_bounds[1] == 32


def test_floating_resize_bounds_ignore_transparent_lasso_padding() -> None:
    piece = Image.new("RGBA", (12, 10), (0, 0, 0, 0))
    piece.putpixel((4, 3), (255, 255, 255, 255))
    piece.putpixel((7, 6), (255, 255, 255, 255))

    assert app._alpha_tight_bounds(piece) == (4, 3, 8, 7)


def test_fit_bounds_ignore_sparse_edge_pixels_that_create_visual_padding() -> None:
    piece = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    for y in range(4, 16):
        for x in range(3, 17):
            piece.putpixel((x, y), (140, 170, 100, 255))
    piece.putpixel((9, 2), (140, 170, 100, 255))
    piece.putpixel((1, 9), (140, 170, 100, 255))

    assert app._alpha_tight_bounds(piece) == (1, 2, 17, 16)
    assert app._alpha_fit_bounds(piece) == (3, 4, 17, 16)


def test_background_mode_exposes_full_studio_tools() -> None:
    component_source = _component_source()
    app_source = _ui_app_source()

    assert "const studioToolsVisible = layerMode || backgroundMode;" in component_source
    assert "toolPencil.hidden = !studioToolsVisible;" in component_source
    assert "toolFill.hidden = !studioToolsVisible;" in component_source
    assert "toolReplaceColor.hidden = !studioToolsVisible;" in component_source
    assert "toolSelectLasso.hidden = !studioToolsVisible;" in component_source
    assert "toolSelectRect.hidden = !studioToolsVisible;" in component_source
    assert "toolSelectEllipse.hidden = !studioToolsVisible;" in component_source
    assert "pixelActionsGroup.hidden = !studioToolsVisible;" in component_source
    assert "rotateControl.hidden = centerMode || cutMode;" in component_source
    assert '"1. Fondo & Estudio"' in app_source
    assert '"Fondo & Estudio de píxeles"' in app_source
    assert "paint_color=tuple(" in app_source


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


def test_canvas_zoom_buttons_persist_their_value() -> None:
    source = _component_source()

    assert source.count("setZoom(zoomInStep(state.zoom), true)") >= 1
    assert source.count("setZoom(state.zoom - 1, true)") >= 1


def test_toolbar_zoom_persists_and_tools_have_visible_hover_descriptions() -> None:
    source = _component_source()
    app_source = _ui_app_source()

    assert 'class="tool-tooltip" id="tool-tooltip" role="tooltip"' in source
    assert "function showToolTooltip" in source
    assert 'toolbar.querySelectorAll("button, select, summary, .pill")' in source
    assert 'element.addEventListener("pointerenter"' in source
    assert 'action: "zoom"' in source
    assert "setZoom(zoomInStep(state.zoom), true)" in source
    assert "setZoom(zoomOutStep(state.zoom), true)" in source
    assert "setZoom(computeFitZoom(), true)" in source
    assert "const MAX_ZOOM = 256" in source
    assert "state.autoFitZoom = false" in source
    assert "!state.autoFitZoom" in source
    assert "!event.ctrlKey && !event.metaKey" in source
    assert "def _is_editor_zoom_event" in app_source
    assert "or _is_editor_zoom_event(event)" in app_source
    assert "not _is_editor_zoom_event(event)" in app_source
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
    assert 'type: "animation"' in source
    assert 'requestAnimationFrames("play")' in source
    assert 'emitAnimationControl("release")' in source
    assert "pendingAnimationAction" in source
    assert "composite_document_frame(" in app_source
    assert "animation_payload_requested" in app_source
    assert "if animation_payload_requested" in app_source
    assert "animation_frames = (" in app_source
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


def test_stage_height_controls_and_persistence() -> None:
    source = _component_source()
    tileset_source = TILESET_COMPONENT_HTML.read_text(encoding="utf-8")

    assert "--stage-height: 720px;" in source
    assert "height: var(--stage-height);" in source
    assert 'id="stage-height-select"' in source
    assert 'id="stage-height-select-center"' in source
    assert 'id="stage-height-select-cut"' in source
    assert "applyStageHeight" in source
    assert "sprite-builder:stage-height" in source

    assert "--stage-height: 720px;" in tileset_source
    assert "height: var(--stage-height, 720px);" in tileset_source
    assert 'id="tileset-stage-height-select"' in tileset_source
    assert "applyTilesetStageHeight" in tileset_source
    assert "sprite-builder:stage-height" in tileset_source


def test_fit_and_zoom_support_fractional_scale_for_large_images() -> None:
    source = _component_source()
    tileset_source = TILESET_COMPONENT_HTML.read_text(encoding="utf-8")

    assert "function clampZoom(value, defaultZoom = 8)" in source
    assert "function formatZoomLabel(zoom)" in source
    assert "function zoomInStep(current)" in source
    assert "function zoomOutStep(current)" in source
    assert "Math.max(0.05, Math.floor(fitScale * 100) / 100)" in source

    assert "function computeTilesetFitZoom()" in tileset_source
    assert "clamp(Math.floor(fitScale * 100) / 100, 0.05, 32)" in tileset_source
    assert "function formatTilesetZoom(zoom)" in tileset_source


def test_pixel_editor_component_wrapper_accepts_float_zoom() -> None:
    sig = inspect.signature(components.pixel_editor)
    assert sig.parameters["zoom"].default == 12.0


def test_final_export_allows_sessions_without_saved_alignment_stage() -> None:
    source = _ui_app_source()

    assert 'session.stages.get("alignment") or {}' in source
    assert 'session.stages["alignment"]["cache_key"]' not in source


def test_background_studio_exposes_direct_png_download_without_pipeline_commit() -> None:
    source = _ui_app_source()

    assert '"Descargar PNG actual"' in source
    assert 'key=f"{prefix}:download_studio_png"' in source
    assert 'on_click="ignore"' in source
    assert "_compose_direct_studio_export(" in source
    assert "No guarda etapas ni avanza la pipeline." in source


def test_center_mode_allows_dragging_frame_and_normalizes_tool() -> None:
    source = _component_source()

    assert 'tool === "drag"' in source
    assert 'return "move";' in source
    assert 'frameIndexAtPoint(point) === state.activeFrame' in source
    assert '(state.mode === "segmentation-center" || state.tool === "move")' in source
