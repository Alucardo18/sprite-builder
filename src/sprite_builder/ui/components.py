"""Small Streamlit render helpers for crisp pixel-art previews."""

from __future__ import annotations

import base64
import html
import io
from pathlib import Path
from typing import Any

from PIL import Image
import streamlit.components.v1 as components

_PIXEL_EDITOR = components.declare_component(
    "sprite_builder_pixel_editor",
    path=str(Path(__file__).parent / "pixel_editor_component"),
)


def image_data_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def pixel_image_html(
    image: Image.Image,
    *,
    caption: str = "",
    max_height: int = 560,
) -> str:
    uri = image_data_uri(image)
    label = html.escape(caption)
    return f"""
    <figure class="pixel-figure">
      <div class="pixel-stage">
        <img class="pixel-image" src="{uri}" alt="{label}"
             style="max-height:{max_height}px" />
      </div>
      <figcaption>{label}</figcaption>
    </figure>
    """


def status_badge(label: str, tone: str = "pending") -> str:
    return f'<span class="status-badge {html.escape(tone)}">{html.escape(label)}</span>'


def pixel_editor(
    image: Image.Image,
    *,
    overlay: Image.Image | None = None,
    sample: tuple[int, int, int, int] | None = None,
    tool: str,
    mode: str = "background",
    brush_radius: int = 5,
    zoom: int = 12,
    offset_x: int = 0,
    offset_y: int = 0,
    home_offset_x: int | None = None,
    home_offset_y: int | None = None,
    show_guides: bool = False,
    guide_opacity: float = 0.7,
    show_cell_center: bool = True,
    show_frame_guide: bool = True,
    show_ground_line: bool = False,
    ground_line_y: float | None = None,
    current_anchor_x: float | None = None,
    current_anchor_y: float | None = None,
    target_anchor_x: float | None = None,
    target_anchor_y: float | None = None,
    show_anchor_delta: bool = True,
    allow_drag: bool = False,
    show_autocenter: bool = True,
    show_autocrop: bool = True,
    fit_on_load: bool = False,
    fit_token: str = "",
    frame_token: str = "",
    cut_positions: tuple[int, ...] | list[int] | None = None,
    allow_cut_drag: bool = False,
    key: str,
) -> dict[str, Any] | None:
    image_uri = image_data_uri(image)
    overlay_uri = image_data_uri(overlay) if overlay is not None else None
    return _PIXEL_EDITOR(
        image=image_uri,
        overlay=overlay_uri,
        width=image.width,
        height=image.height,
        zoom=max(1, int(zoom)),
        tool=tool,
        mode=mode,
        sample=sample,
        brushRadius=max(1, int(brush_radius)),
        offsetX=int(offset_x),
        offsetY=int(offset_y),
        homeOffsetX=int(offset_x if home_offset_x is None else home_offset_x),
        homeOffsetY=int(offset_y if home_offset_y is None else home_offset_y),
        showGuides=bool(show_guides),
        guideOpacity=max(0.0, min(1.0, float(guide_opacity))),
        showCellCenter=bool(show_cell_center),
        showFrameGuide=bool(show_frame_guide),
        showGroundLine=bool(show_ground_line),
        groundLineY=None if ground_line_y is None else float(ground_line_y),
        currentAnchorX=None if current_anchor_x is None else float(current_anchor_x),
        currentAnchorY=None if current_anchor_y is None else float(current_anchor_y),
        targetAnchorX=None if target_anchor_x is None else float(target_anchor_x),
        targetAnchorY=None if target_anchor_y is None else float(target_anchor_y),
        showAnchorDelta=bool(show_anchor_delta),
        allowDrag=bool(allow_drag),
        showAutocenter=bool(show_autocenter),
        showAutocrop=bool(show_autocrop),
        fitOnLoad=bool(fit_on_load),
        fitToken=str(fit_token),
        frameToken=str(frame_token),
        cutPositions=None if cut_positions is None else [int(value) for value in cut_positions],
        allowCutDrag=bool(allow_cut_drag),
        key=key,
        default=None,
    )
