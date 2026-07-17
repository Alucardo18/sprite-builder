"""Small Streamlit render helpers for crisp pixel-art previews."""

from __future__ import annotations

import base64
import html
import io
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import streamlit.components.v1 as components
from PIL import Image

_PIXEL_EDITOR = components.declare_component(
    "sprite_builder_pixel_editor",
    path=str(Path(__file__).parent / "pixel_editor_component"),
)

_TILESET_EDITOR = components.declare_component(
    "sprite_builder_tileset_editor",
    path=str(Path(__file__).parent / "tileset_editor_component"),
)

_HEADER_NAV = components.declare_component(
    "sprite_builder_header_nav",
    path=str(Path(__file__).parent / "header_nav_component"),
)


@lru_cache(maxsize=384)
def _image_data_uri_cached(
    mode: str,
    size: tuple[int, int],
    pixels: bytes,
) -> str:
    image = Image.frombytes(mode, size, pixels)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def image_data_uri(image: Image.Image) -> str:
    stable = image if image.mode in {"1", "L", "LA", "RGB", "RGBA"} else image.convert("RGBA")
    return _image_data_uri_cached(stable.mode, stable.size, stable.tobytes())


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


def header_navigation(active_page: str) -> None:
    """Mount page navigation inside Streamlit's native header toolbar."""

    _HEADER_NAV(
        activePage="tilesets" if active_page == "tilesets" else "sprites",
        key="sprite_builder_header_navigation",
        default=None,
    )


def tileset_editor(
    image: Image.Image,
    *,
    image_token: str,
    tile_size: int,
    offset_x: int = 0,
    offset_y: int = 0,
    spacing_x: int = 0,
    spacing_y: int = 0,
    key: str,
) -> dict[str, Any] | None:
    """Render the full-width tileset canvas."""

    result = _TILESET_EDITOR(
        image=image_data_uri(image.convert("RGBA")),
        imageToken=str(image_token),
        tileSize=max(1, min(64, int(tile_size))),
        offsetX=max(0, int(offset_x)),
        offsetY=max(0, int(offset_y)),
        spacingX=max(0, int(spacing_x)),
        spacingY=max(0, int(spacing_y)),
        key=key,
        default=None,
    )
    return cast(dict[str, Any] | None, result)


def pixel_editor(
    image: Image.Image,
    *,
    overlay: Image.Image | None = None,
    move_base: Image.Image | None = None,
    sample: tuple[int, int, int, int] | None = None,
    paint_color: tuple[int, int, int, int] | None = None,
    tool: str,
    mode: str = "background",
    brush_radius: int = 5,
    wand_tolerance: int = 0,
    wand_contiguous: bool = True,
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
    cut_positions_x: tuple[int, ...] | list[int] | None = None,
    cut_positions_y: tuple[int, ...] | list[int] | None = None,
    allow_cut_drag: bool = False,
    studio_layers: Sequence[Mapping[str, Any]] | None = None,
    active_layer_id: str | None = None,
    active_frame: int = 0,
    frame_count: int = 0,
    selected_frames: Sequence[int] | None = None,
    floating_selection: Image.Image | None = None,
    floating_highlight: Image.Image | None = None,
    floating_selection_x: int = 0,
    floating_selection_y: int = 0,
    floating_selection_bounds: tuple[int, int, int, int] | None = None,
    can_undo: bool = False,
    can_redo: bool = False,
    undo_label: str = "",
    redo_label: str = "",
    animation_frames: Sequence[Image.Image] | None = None,
    animation_fps: int = 8,
    animation_durations: Sequence[int] | None = None,
    key: str,
) -> dict[str, Any] | None:
    image_uri = image_data_uri(image)
    overlay_uri = image_data_uri(overlay) if overlay is not None else None
    move_base_uri = image_data_uri(move_base) if move_base is not None else None
    result = _PIXEL_EDITOR(
        image=image_uri,
        overlay=overlay_uri,
        moveBase=move_base_uri,
        width=image.width,
        height=image.height,
        zoom=max(1, int(zoom)),
        tool=tool,
        mode=mode,
        sample=sample,
        paintColor=paint_color if paint_color is not None else sample,
        brushRadius=max(1, int(brush_radius)),
        wandTolerance=max(0, min(255, int(wand_tolerance))),
        wandContiguous=bool(wand_contiguous),
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
        cutPositionsX=None if cut_positions_x is None else [int(value) for value in cut_positions_x],
        cutPositionsY=None if cut_positions_y is None else [int(value) for value in cut_positions_y],
        allowCutDrag=bool(allow_cut_drag),
        studioLayers=None if studio_layers is None else [dict(layer) for layer in studio_layers],
        activeLayerId=None if active_layer_id is None else str(active_layer_id),
        activeFrame=max(0, int(active_frame)),
        frameCount=max(0, int(frame_count)),
        selectedFrames=(
            [] if selected_frames is None else [max(0, int(value)) for value in selected_frames]
        ),
        floatingSelection=(
            None if floating_selection is None else image_data_uri(floating_selection)
        ),
        floatingHighlight=(
            None if floating_highlight is None else image_data_uri(floating_highlight)
        ),
        floatingSelectionX=int(floating_selection_x),
        floatingSelectionY=int(floating_selection_y),
        floatingSelectionBounds=(
            None
            if floating_selection_bounds is None
            else [int(value) for value in floating_selection_bounds]
        ),
        canUndo=bool(can_undo),
        canRedo=bool(can_redo),
        undoLabel=str(undo_label),
        redoLabel=str(redo_label),
        animationFrames=(
            []
            if not animation_frames
            else [image_data_uri(frame) for frame in animation_frames]
        ),
        animationFps=max(1, min(60, int(animation_fps))),
        animationDurations=(
            []
            if animation_durations is None
            else [max(16, int(value)) for value in animation_durations]
        ),
        key=key,
        default=None,
    )
    return cast(dict[str, Any] | None, result)
