"""Small Streamlit render helpers for crisp pixel-art previews."""

from __future__ import annotations

import base64
import hashlib
import html
import io
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
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

_TERRAIN_PATTERN_STUDIO = components.declare_component(
    "sprite_builder_terrain_pattern_studio",
    path=str(Path(__file__).parent / "terrain_pattern_studio_component"),
)

_HEADER_NAV = components.declare_component(
    "sprite_builder_header_nav",
    path=str(Path(__file__).parent / "header_nav_component"),
)


_IMAGE_DATA_URI_CACHE_MAX_BYTES = 16 * 1024 * 1024


class _ByteBudgetImageUriCache:
    """Deterministic LRU for encoded image URIs with a hard byte budget.

    The old ``lru_cache`` used raw pixel bytes as part of every key and kept a
    second copy of each encoded URI as its value.  This cache keys entries by a
    content digest instead, so raw pixels are released after encoding, and
    accounts for the retained digest and URI when evicting.
    """

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max(0, int(max_bytes))
        self._entries: OrderedDict[tuple[Any, ...], tuple[str, int]] = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()

    @staticmethod
    def _entry_bytes(key: tuple[Any, ...], value: str) -> int:
        digest = key[-1]
        digest_bytes = len(digest) if isinstance(digest, bytes) else 0
        # Include a small fixed allowance for the tuple/metadata retained by
        # the entry.  The exact object overhead is interpreter-specific; this
        # conservative deterministic weight keeps the budget bounded.
        return len(value.encode("ascii")) + digest_bytes + 64

    def get(self, key: tuple[Any, ...]) -> str | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return entry[0]

    def put(self, key: tuple[Any, ...], value: str) -> None:
        entry_bytes = self._entry_bytes(key, value)
        if entry_bytes > self.max_bytes:
            return
        with self._lock:
            previous = self._entries.pop(key, None)
            if previous is not None:
                self._bytes -= previous[1]
            while self._entries and self._bytes + entry_bytes > self.max_bytes:
                _, (_, removed_bytes) = self._entries.popitem(last=False)
                self._bytes -= removed_bytes
            self._entries[key] = (value, entry_bytes)
            self._bytes += entry_bytes

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._bytes = 0

    def info(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "bytes": self._bytes,
                "max_bytes": self.max_bytes,
            }


_IMAGE_DATA_URI_CACHE = _ByteBudgetImageUriCache(_IMAGE_DATA_URI_CACHE_MAX_BYTES)


def _image_data_uri_cached(
    mode: str,
    size: tuple[int, int],
    pixels: bytes,
) -> str:
    # A digest key preserves deterministic reuse without retaining the raw
    # pixel buffer in the cache's key tuple.
    key = (mode, size, len(pixels), hashlib.sha256(pixels).digest())
    cached = _IMAGE_DATA_URI_CACHE.get(key)
    if cached is not None:
        return cached
    image = Image.frombytes(mode, size, pixels)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    _IMAGE_DATA_URI_CACHE.put(key, uri)
    return uri


def image_data_uri(image: Image.Image, *, revision: str | None = None) -> str:
    stable = image if image.mode in {"1", "L", "LA", "RGB", "RGBA"} else image.convert("RGBA")
    if revision:
        key = ("revision", str(revision), stable.mode, stable.size)
        cached = _IMAGE_DATA_URI_CACHE.get(key)
        if cached is not None:
            return cached
        buffer = io.BytesIO()
        stable.save(buffer, format="PNG", optimize=False)
        uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        _IMAGE_DATA_URI_CACHE.put(key, uri)
        return uri
    uri = _image_data_uri_cached(stable.mode, stable.size, stable.tobytes())
    return uri


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


def pixel_gif_html(
    gif_bytes: bytes,
    *,
    caption: str = "",
    size: int = 64,
) -> str:
    b64 = base64.b64encode(gif_bytes).decode("ascii")
    uri = f"data:image/gif;base64,{b64}"
    label = html.escape(caption)
    caption_html = f"<figcaption>{label}</figcaption>" if label else ""
    return f"""
    <figure class="pixel-figure">
      <div class="pixel-stage" style="min-height: auto; padding: 16px;">
        <img class="pixel-image" src="{uri}" alt="{label}"
             style="width: {size}px; height: auto; max-width: 100%;" />
      </div>
      {caption_html}
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


def terrain_pattern_studio(
    image: Image.Image,
    *,
    pattern_image: Image.Image,
    image_token: str,
    tile_size: tuple[int, int],
    offset: tuple[int, int] = (0, 0),
    spacing: tuple[int, int] = (0, 0),
    kind: str,
    roles: Sequence[Mapping[str, Any]],
    project: Mapping[str, Any],
    set_previews: Sequence[Mapping[str, Any]] = (),
    key: str,
) -> dict[str, Any] | None:
    """Render the fragment library, layered tile composer, and terrain sandbox."""

    preview_payload: list[dict[str, Any]] = []
    for preview in set_previews:
        item = dict(preview)
        preview_image = item.get("image")
        if isinstance(preview_image, Image.Image):
            item["image"] = image_data_uri(preview_image.convert("RGBA"))
        preview_payload.append(item)
    result = _TERRAIN_PATTERN_STUDIO(
        image=image_data_uri(image.convert("RGBA")),
        patternImage=image_data_uri(pattern_image.convert("RGBA")),
        imageToken=str(image_token),
        tileWidth=max(1, int(tile_size[0])),
        tileHeight=max(1, int(tile_size[1])),
        offsetX=max(0, int(offset[0])),
        offsetY=max(0, int(offset[1])),
        spacingX=max(0, int(spacing[0])),
        spacingY=max(0, int(spacing[1])),
        kind=str(kind),
        roles=[dict(role) for role in roles],
        project=dict(project),
        setPreviews=preview_payload,
        key=key,
        default=None,
    )
    return cast(dict[str, Any] | None, result)


def _safe_image_data_uri(image: Image.Image, *, revision: str | None = None) -> str:
    try:
        return image_data_uri(image, revision=revision)
    except TypeError:
        return image_data_uri(image)


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
    zoom: float = 12.0,
    offset_x: int = 0,
    offset_y: int = 0,
    home_offset_x: int | None = None,
    home_offset_y: int | None = None,
    show_guides: bool = False,
    guide_opacity: float = 0.7,
    show_pixel_grid: bool = False,
    pixel_grid_size: int = 16,
    show_cell_center: bool = True,
    show_frame_guide: bool = True,
    show_column_guides: bool = True,
    show_row_guides: bool = True,
    grid_columns: int = 1,
    grid_rows: int = 1,
    show_ground_line: bool = False,
    ground_line_y: float | None = None,
    current_anchor_x: float | None = None,
    current_anchor_y: float | None = None,
    target_anchor_x: float | None = None,
    target_anchor_y: float | None = None,
    show_anchor_delta: bool = True,
    allow_drag: bool = False,
    show_autocenter: bool = True,
    show_autocenter_all: bool = False,
    show_autocrop: bool = True,
    fit_on_load: bool = False,
    fit_token: str = "",
    frame_token: str = "",
    acknowledged_event_id: str = "",
    cut_positions: tuple[int, ...] | list[int] | None = None,
    cut_positions_x: tuple[int, ...] | list[int] | None = None,
    cut_positions_y: tuple[int, ...] | list[int] | None = None,
    allow_cut_drag: bool = False,
    studio_layers: Sequence[Mapping[str, Any]] | None = None,
    active_layer_id: str | None = None,
    active_frame: int = 0,
    frame_count: int = 0,
    frame_locks: Sequence[bool] | None = None,
    selected_frames: Sequence[int] | None = None,
    floating_selection: Image.Image | None = None,
    floating_highlight: Image.Image | None = None,
    floating_selection_x: int = 0,
    floating_selection_y: int = 0,
    floating_selection_bounds: tuple[int, int, int, int] | None = None,
    floating_operation_kind: str = "move_mask",
    can_undo: bool = False,
    can_redo: bool = False,
    undo_label: str = "",
    redo_label: str = "",
    animation_frames: Sequence[Image.Image] | None = None,
    animation_fps: int = 8,
    animation_durations: Sequence[int] | None = None,
    palette_colors: Sequence[str] | None = None,
    image_revision: str | None = None,
    overlay_revision: str | None = None,
    move_base_revision: str | None = None,
    key: str,
) -> dict[str, Any] | None:
    image_uri = _safe_image_data_uri(image, revision=image_revision)
    overlay_uri = (
        _safe_image_data_uri(overlay, revision=overlay_revision) if overlay is not None else None
    )
    move_base_uri = (
        _safe_image_data_uri(move_base, revision=move_base_revision)
        if move_base is not None
        else None
    )
    animation_payload = tuple(animation_frames or ())
    result = _PIXEL_EDITOR(
        image=image_uri,
        overlay=overlay_uri,
        moveBase=move_base_uri,
        width=image.width,
        height=image.height,
        zoom=max(0.05, float(zoom)),
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
        showPixelGrid=bool(show_pixel_grid),
        pixelGridSize=max(1, int(pixel_grid_size)),
        showCellCenter=bool(show_cell_center),
        showFrameGuide=bool(show_frame_guide),
        showColumnGuides=bool(show_column_guides),
        showRowGuides=bool(show_row_guides),
        gridColumns=max(1, int(grid_columns)),
        gridRows=max(1, int(grid_rows)),
        showGroundLine=bool(show_ground_line),
        groundLineY=None if ground_line_y is None else float(ground_line_y),
        currentAnchorX=None if current_anchor_x is None else float(current_anchor_x),
        currentAnchorY=None if current_anchor_y is None else float(current_anchor_y),
        targetAnchorX=None if target_anchor_x is None else float(target_anchor_x),
        targetAnchorY=None if target_anchor_y is None else float(target_anchor_y),
        showAnchorDelta=bool(show_anchor_delta),
        allowDrag=bool(allow_drag),
        showAutocenter=bool(show_autocenter),
        showAutocenterAll=bool(show_autocenter_all),
        showAutocrop=bool(show_autocrop),
        fitOnLoad=bool(fit_on_load),
        fitToken=str(fit_token),
        frameToken=str(frame_token),
        imageRevision=str(image_revision or ""),
        overlayRevision=str(overlay_revision or ""),
        moveBaseRevision=str(move_base_revision or ""),
        acknowledgedEventId=str(acknowledged_event_id),
        cutPositions=None if cut_positions is None else [int(value) for value in cut_positions],
        cutPositionsX=(
            None if cut_positions_x is None else [int(value) for value in cut_positions_x]
        ),
        cutPositionsY=(
            None if cut_positions_y is None else [int(value) for value in cut_positions_y]
        ),
        allowCutDrag=bool(allow_cut_drag),
        studioLayers=None if studio_layers is None else [dict(layer) for layer in studio_layers],
        activeLayerId=None if active_layer_id is None else str(active_layer_id),
        activeFrame=max(0, int(active_frame)),
        frameCount=max(0, int(frame_count)),
        frameLocks=[] if frame_locks is None else [bool(value) for value in frame_locks],
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
        floatingOperationKind=str(floating_operation_kind),
        canUndo=bool(can_undo),
        canRedo=bool(can_redo),
        undoLabel=str(undo_label),
        redoLabel=str(redo_label),
        animationFrames=(
            []
            if not animation_payload
            else [image_data_uri(frame) for frame in animation_payload]
        ),
        animationFps=max(1, min(60, int(animation_fps))),
        animationDurations=(
            []
            if not animation_payload or animation_durations is None
            else [max(16, int(value)) for value in animation_durations]
        ),
        paletteColors=[str(c) for c in palette_colors] if palette_colors else [],
        key=key,
        default=None,
    )
    return cast(dict[str, Any] | None, result)
