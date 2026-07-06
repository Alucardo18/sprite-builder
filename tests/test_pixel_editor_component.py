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
UI_APP = Path(components.__file__).resolve().parent / "app.py"


def _component_source() -> str:
    return COMPONENT_HTML.read_text(encoding="utf-8")


def _ui_app_source() -> str:
    return UI_APP.read_text(encoding="utf-8")


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

    assert '"Auto cut"' in source
    assert '"Free adjust"' in source
    assert 'mode="segmentation-cut"' in source
    assert 'cut_positions=st.session_state[f"{prefix}:segmentation_cut_positions"]' in source
    assert 'segmentation_free_adjust_widget' in source
    assert 'segmentation_cut_zoom_widget_sync' in source


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


def test_center_zoom_is_local_until_the_next_manual_event() -> None:
    source = _component_source()

    local_only = r"state\.mode\s*!==\s*[\"']segmentation-center[\"']"
    assert len(
        re.findall(rf"setZoom\([^;]+,\s*{local_only}\s*\)", source)
    ) >= 4
    emit_value = re.search(
        r"function\s+emitValue\(value\)\s*\{([\s\S]*?)\n\s{6}\}",
        source,
    )
    assert emit_value
    assert 'state.mode === "segmentation-center"' in emit_value.group(1)
    assert "zoom: state.zoom" in emit_value.group(1)
