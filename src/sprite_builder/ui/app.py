"""Apple-glass, pixel-perfect local editor for existing sprite sheets."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import uuid
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import streamlit as st
from PIL import Image, ImageDraw

from sprite_builder.domain.errors import ArtifactIntegrityError
from sprite_builder.sheets import (
    AutoCenterConfig,
    BackgroundRemovalConfig,
    CenteringAnalysis,
    CenteringResult,
    ExportCropResult,
    FrameAdjustment,
    LayeredSpriteDocument,
    SegmentationConfig,
    SheetSessionStore,
    SpriteLayer,
    apply_background_removal,
    apply_manual_background_edits,
    auto_cut_positions,
    auto_center_frames,
    analyze_center_frames,
    clear_selection,
    combine_selection_masks,
    composite_document_frame,
    composite_document_frames,
    delete_document_frame,
    duplicate_document_frame,
    encode_mask,
    fill_cel_selection,
    move_document_frame,
    outline_cel_pixels,
    paint_cel_stroke,
    render_contact_sheet,
    render_frame_overlay,
    render_segmentation_guides,
    render_selection_overlay,
    remove_isolated_pixels,
    replace_cel_color,
    resolve_segmentation_config,
    sample_pixel,
    segment_sheet,
    select_similar_pixels,
    trim_transparent_frames,
    transform_cel_selection,
)
from sprite_builder.sheets.models import ExportCropConfig
from sprite_builder.tilesets import (
    TilesetGrid,
    build_tileset_bundle,
    resize_tileset,
    resize_tileset_canvas,
    slice_tileset,
)
from sprite_builder.ui.components import (
    header_navigation,
    pixel_editor,
    pixel_image_html,
    status_badge,
    tileset_editor,
)


_EDITOR_HISTORY_LIMIT = 75
_TILESET_STATE_PREFIX = "tileset_builder"
_APP_PAGE_KEY = "sprite_builder_page"


def _workspace() -> Path:
    return Path(os.environ.get("SPRITE_BUILDER_WORKSPACE", ".")).expanduser().resolve()


def _load_css() -> None:
    css = (Path(__file__).parent / "assets" / "theme.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _render_header_navigation() -> str:
    """Mount app-level navigation in Streamlit's native header."""

    requested = str(st.query_params.get("page", "")).strip().lower()
    if requested in {"sprites", "tilesets"}:
        st.session_state[_APP_PAGE_KEY] = requested
    page = str(st.session_state.get(_APP_PAGE_KEY, "sprites"))
    if page not in {"sprites", "tilesets"}:
        page = "sprites"
    header_navigation(page)
    return page


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGBA").save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _tileset_state_image() -> Image.Image | None:
    value = st.session_state.get(f"{_TILESET_STATE_PREFIX}:image")
    if not isinstance(value, bytes):
        return None
    try:
        with Image.open(io.BytesIO(value)) as image:
            return image.convert("RGBA")
    except (OSError, ValueError):
        return None


def _set_tileset_image(image: Image.Image, *, source_name: str, reset_canvas: bool) -> None:
    st.session_state[f"{_TILESET_STATE_PREFIX}:image"] = _png_bytes(image)
    st.session_state[f"{_TILESET_STATE_PREFIX}:source_name"] = source_name
    if reset_canvas:
        st.session_state[f"{_TILESET_STATE_PREFIX}:canvas_token"] = uuid.uuid4().hex
        st.session_state[f"{_TILESET_STATE_PREFIX}:last_event"] = None


def _tileset_grid_from_state() -> TilesetGrid:
    prefix = _TILESET_STATE_PREFIX
    tile_size = max(1, min(64, int(st.session_state.get(f"{prefix}:tile_size", 16))))
    return TilesetGrid(
        tile_width=tile_size,
        tile_height=tile_size,
        offset_x=max(0, int(st.session_state.get(f"{prefix}:offset_x", 0))),
        offset_y=max(0, int(st.session_state.get(f"{prefix}:offset_y", 0))),
        spacing_x=max(0, int(st.session_state.get(f"{prefix}:spacing_x", 0))),
        spacing_y=max(0, int(st.session_state.get(f"{prefix}:spacing_y", 0))),
    )


def _apply_tileset_grid_event(event: Mapping[str, Any]) -> None:
    raw = event.get("grid")
    if not isinstance(raw, Mapping):
        return
    prefix = _TILESET_STATE_PREFIX
    st.session_state[f"{prefix}:tile_size"] = max(
        1, min(64, int(raw.get("tile_size", raw.get("tile_width", 16))))
    )
    for name in ("offset_x", "offset_y", "spacing_x", "spacing_y"):
        st.session_state[f"{prefix}:{name}"] = max(0, int(raw.get(name, 0)))


def _render_tileset_builder() -> None:
    """Render the standalone, full-width tileset authoring canvas."""

    prefix = _TILESET_STATE_PREFIX
    st.subheader("Tileset Builder")
    st.caption(
        "Edita el atlas a píxel real, define su cuadrícula y exporta PNG + metadata."
    )
    upload_col, scale_col = st.columns((1.1, 2.9), gap="large")
    with upload_col:
        upload = st.file_uploader(
            "Cargar tileset PNG",
            type=["png"],
            key=f"{prefix}:upload",
        )
        if upload is not None:
            payload = upload.getvalue()
            digest = hashlib.sha256(payload).hexdigest()
            if digest != st.session_state.get(f"{prefix}:upload_sha256"):
                try:
                    with Image.open(io.BytesIO(payload)) as incoming:
                        _set_tileset_image(
                            incoming.convert("RGBA"),
                            source_name=upload.name,
                            reset_canvas=True,
                        )
                    st.session_state[f"{prefix}:upload_sha256"] = digest
                except OSError as exc:
                    st.error(f"No se pudo abrir el PNG: {exc}")
    image = _tileset_state_image()
    with scale_col:
        if image is None:
            st.info("Carga un PNG para activar el canvas.")
        else:
            st.markdown("**Reescalado pixel-perfect · nearest-neighbor**")
            width_col, height_col, action_col = st.columns((1, 1, 1.25), gap="small")
            target_width = int(
                width_col.number_input(
                    "Ancho final",
                    min_value=1,
                    max_value=8192,
                    value=image.width,
                    key=f"{prefix}:target_width:{image.width}x{image.height}",
                )
            )
            target_height = int(
                height_col.number_input(
                    "Alto final",
                    min_value=1,
                    max_value=8192,
                    value=image.height,
                    key=f"{prefix}:target_height:{image.width}x{image.height}",
                )
            )
            if action_col.button(
                "Aplicar tamaño",
                type="primary",
                width="stretch",
                disabled=(target_width, target_height) == image.size,
                key=f"{prefix}:resize",
            ):
                _set_tileset_image(
                    resize_tileset(image, (target_width, target_height)),
                    source_name=str(
                        st.session_state.get(f"{prefix}:source_name", "tileset.png")
                    ),
                    reset_canvas=True,
                )
                st.rerun()
            preset_cols = st.columns(5, gap="small")
            for column, (label, divisor) in zip(
                preset_cols,
                (("½", 2), ("¼", 4), ("⅛", 8), ("2×", 0.5), ("4×", 0.25)),
                strict=True,
            ):
                size = (
                    max(1, round(image.width / divisor)),
                    max(1, round(image.height / divisor)),
                )
                if column.button(label, width="stretch", key=f"{prefix}:scale:{label}"):
                    _set_tileset_image(
                        resize_tileset(image, size),
                        source_name=str(
                            st.session_state.get(f"{prefix}:source_name", "tileset.png")
                        ),
                        reset_canvas=True,
                    )
                    st.rerun()
            with st.expander("Tamaño del lienzo · no escala la imagen"):
                st.caption(
                    "Añade transparencia o recorta bordes; cada píxel conserva su tamaño."
                )
                canvas_width_col, canvas_height_col = st.columns(2, gap="small")
                canvas_width = int(
                    canvas_width_col.number_input(
                        "Ancho del lienzo",
                        min_value=1,
                        max_value=8192,
                        value=image.width,
                        key=f"{prefix}:canvas_width:{image.width}x{image.height}",
                    )
                )
                canvas_height = int(
                    canvas_height_col.number_input(
                        "Alto del lienzo",
                        min_value=1,
                        max_value=8192,
                        value=image.height,
                        key=f"{prefix}:canvas_height:{image.width}x{image.height}",
                    )
                )
                anchor_labels = {
                    "Superior izquierda": "top-left",
                    "Superior centro": "top",
                    "Superior derecha": "top-right",
                    "Centro izquierda": "left",
                    "Centro": "center",
                    "Centro derecha": "right",
                    "Inferior izquierda": "bottom-left",
                    "Inferior centro": "bottom",
                    "Inferior derecha": "bottom-right",
                }
                anchor_label = st.selectbox(
                    "Anclaje del contenido",
                    tuple(anchor_labels),
                    key=f"{prefix}:canvas_anchor",
                )
                if st.button(
                    "Aplicar tamaño de lienzo",
                    type="primary",
                    width="stretch",
                    disabled=(canvas_width, canvas_height) == image.size,
                    key=f"{prefix}:resize_canvas",
                ):
                    _set_tileset_image(
                        resize_tileset_canvas(
                            image,
                            (canvas_width, canvas_height),
                            anchor=anchor_labels[anchor_label],
                        ),
                        source_name=str(
                            st.session_state.get(
                                f"{prefix}:source_name", "tileset.png"
                            )
                        ),
                        reset_canvas=True,
                    )
                    st.rerun()

    image = _tileset_state_image()
    if image is None:
        return
    grid = _tileset_grid_from_state()
    event = tileset_editor(
        image,
        image_token=str(
            st.session_state.setdefault(f"{prefix}:canvas_token", uuid.uuid4().hex)
        ),
        tile_size=grid.tile_width,
        offset_x=grid.offset_x,
        offset_y=grid.offset_y,
        spacing_x=grid.spacing_x,
        spacing_y=grid.spacing_y,
        key=f"{prefix}:canvas",
    )
    if isinstance(event, Mapping):
        event_id = str(event.get("eventId", ""))
        if event_id and event_id != st.session_state.get(f"{prefix}:last_event"):
            st.session_state[f"{prefix}:last_event"] = event_id
            _apply_tileset_grid_event(event)
            encoded = event.get("image")
            if isinstance(encoded, str) and encoded.startswith("data:image/png;base64,"):
                try:
                    payload = base64.b64decode(encoded.split(",", 1)[1], validate=True)
                    with Image.open(io.BytesIO(payload)) as edited:
                        _set_tileset_image(
                            edited.convert("RGBA"),
                            source_name=str(
                                st.session_state.get(
                                    f"{prefix}:source_name", "tileset.png"
                                )
                            ),
                            reset_canvas=False,
                        )
                    image = _tileset_state_image() or image
                except (OSError, ValueError):
                    st.warning(
                        "El canvas devolvió un PNG inválido; se conservó la versión anterior."
                    )
            st.rerun()

    tiles = slice_tileset(image, grid)
    duplicate_count = sum(tile.duplicate_of is not None for tile in tiles)
    empty_count = sum(tile.empty for tile in tiles)
    metric_cols = st.columns(5, gap="small")
    metric_cols[0].metric("Atlas", f"{image.width}×{image.height}")
    metric_cols[1].metric("Tile", f"{grid.tile_width}×{grid.tile_height}")
    metric_cols[2].metric("Tiles completos", len(tiles))
    metric_cols[3].metric("Duplicados", duplicate_count)
    metric_cols[4].metric("Vacíos", empty_count)
    if not tiles:
        st.warning("La cuadrícula actual no contiene ningún tile completo.")
        return
    png_payload = _png_bytes(image)
    source_name = str(st.session_state.get(f"{prefix}:source_name", "tileset.png"))
    download_cols = st.columns(2, gap="small")
    download_cols[0].download_button(
        "Descargar atlas PNG",
        data=png_payload,
        file_name="tileset.png",
        mime="image/png",
        width="stretch",
        key=f"{prefix}:download_png",
    )
    download_cols[1].download_button(
        "Descargar bundle PNG + JSON + tiles",
        data=build_tileset_bundle(image, grid, source_name=source_name),
        file_name="tileset-bundle.zip",
        mime="application/zip",
        width="stretch",
        key=f"{prefix}:download_bundle",
    )


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
        "crop_lasso": "Recorte lazo",
        "crop_rect": "Recorte rectangular",
        "crop_ellipse": "Recorte elíptico",
        "move": "Mover selección",
    }.get(tool, "Varita")


def _normalize_background_tool(tool: Any) -> str:
    value = str(tool or "wand")
    return value if value in {
        "wand",
        "eraser",
        "eyedropper",
        "crop_lasso",
        "crop_rect",
        "crop_ellipse",
        "move",
    } else "wand"


def _normalize_layer_tool(tool: Any) -> str:
    value = str(tool or "pencil")
    return value if value in {
        "pencil",
        "eraser",
        "eyedropper",
        "move",
        "crop_lasso",
        "crop_rect",
        "crop_ellipse",
        "select_lasso",
        "select_rect",
        "select_ellipse",
        "fill",
        "replace_color",
    } else "pencil"


def _layer_tool_label(tool: str) -> str:
    return {
        "pencil": "Lápiz",
        "eraser": "Borrador",
        "eyedropper": "Cuentagotas",
        "move": "Mover cel",
        "crop_lasso": "Cortar lazo",
        "crop_rect": "Cortar rectángulo",
        "crop_ellipse": "Cortar elipse",
        "select_lasso": "Selección lazo",
        "select_rect": "Selección rectangular",
        "select_ellipse": "Selección elíptica",
        "fill": "Cubeta",
        "replace_color": "Reemplazar color",
    }.get(tool, "Lápiz")


def _hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    return (*_hex_to_rgb(value), 255)


def _history_stacks(prefix: str) -> dict[str, list[dict[str, Any]]]:
    key = f"{prefix}:editor_history"
    value = st.session_state.get(key)
    if not isinstance(value, dict):
        value = {"undo": [], "redo": []}
        st.session_state[key] = value
    value.setdefault("undo", [])
    value.setdefault("redo", [])
    return value


def _history_controls(session: Any) -> dict[str, Any]:
    stacks = _history_stacks(session.session_id)
    undo_stack = stacks["undo"]
    redo_stack = stacks["redo"]
    return {
        "can_undo": bool(undo_stack),
        "can_redo": bool(redo_stack),
        "undo_label": str(undo_stack[-1].get("label", "")) if undo_stack else "",
        "redo_label": str(redo_stack[-1].get("label", "")) if redo_stack else "",
    }


def _pack_selection_masks(values: Sequence[Any]) -> list[dict[str, Any] | None]:
    packed: list[dict[str, Any] | None] = []
    for value in values:
        if not isinstance(value, np.ndarray):
            packed.append(None)
            continue
        mask = np.asarray(value, dtype=bool)
        packed.append(
            {
                "shape": [int(mask.shape[0]), int(mask.shape[1])],
                "data": np.packbits(mask.reshape(-1)).tobytes(),
            }
        )
    return packed


def _unpack_selection_masks(
    values: Sequence[Mapping[str, Any] | None],
) -> list[np.ndarray | None]:
    unpacked: list[np.ndarray | None] = []
    for value in values:
        if not isinstance(value, Mapping):
            unpacked.append(None)
            continue
        shape = value.get("shape")
        data = value.get("data")
        if (
            not isinstance(shape, (list, tuple))
            or len(shape) != 2
            or not isinstance(data, bytes)
        ):
            unpacked.append(None)
            continue
        height, width = int(shape[0]), int(shape[1])
        bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8), count=height * width)
        unpacked.append(bits.astype(bool).reshape((height, width)))
    return unpacked


def _background_history_snapshot(prefix: str) -> dict[str, Any]:
    operations = st.session_state.get(f"{prefix}:background_manual_ops", {})
    return {
        "manual_operations": json.loads(json.dumps(operations)),
        "selection_masks": _pack_selection_masks(
            st.session_state.get(f"{prefix}:background_selection_masks", [])
        ),
    }


def _clear_background_floating_selection(prefix: str) -> None:
    st.session_state.pop(f"{prefix}:background_floating_selection", None)


def _center_history_snapshot(prefix: str) -> dict[str, Any]:
    return {
        "offsets": [
            [int(offset[0]), int(offset[1])]
            for offset in st.session_state.get(f"{prefix}:offsets", [])
        ],
        "ground_line_y": int(st.session_state.get(f"{prefix}:center_ground_line_y", 0)),
    }


def _cut_history_snapshot(prefix: str) -> dict[str, Any]:
    return {
        "positions": list(st.session_state.get(f"{prefix}:segmentation_cut_positions", [])),
        "positions_x": list(st.session_state.get(f"{prefix}:segmentation_cut_positions_x", [])),
        "positions_y": list(st.session_state.get(f"{prefix}:segmentation_cut_positions_y", [])),
    }


def _layer_history_snapshot(session: Any) -> dict[str, Any]:
    prefix = session.session_id
    selections = st.session_state.get(f"{prefix}:layer_editor_selection_masks", {})
    return {
        "layer_document": dict(session.layer_document) if session.layer_document else None,
        "selection_masks": {
            str(key): _pack_selection_masks([mask])[0]
            for key, mask in selections.items()
            if isinstance(mask, np.ndarray)
        }
    }


def _save_layer_document_with_history(
    store: SheetSessionStore,
    session: Any,
    document: LayeredSpriteDocument,
    images: Mapping[tuple[str, int], Image.Image],
    *,
    reason: str,
    label: str,
) -> LayeredSpriteDocument:
    before = _layer_history_snapshot(session)
    saved = store.save_layer_document(session, document, images, reason=reason)
    _record_editor_history(
        session,
        scope="studio",
        label=label,
        before=before,
        after=_layer_history_snapshot(session),
    )
    return saved


def _record_editor_history(
    session: Any,
    *,
    scope: str,
    label: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> bool:
    if before == after:
        return False
    stacks = _history_stacks(session.session_id)
    stacks["undo"].append(
        {
            "command_id": uuid.uuid4().hex,
            "scope": scope,
            "label": label,
            "before": before,
            "after": after,
        }
    )
    if len(stacks["undo"]) > _EDITOR_HISTORY_LIMIT:
        del stacks["undo"][:-_EDITOR_HISTORY_LIMIT]
    stacks["redo"].clear()
    return True


def _apply_editor_history_snapshot(
    store: SheetSessionStore,
    session: Any,
    scope: str,
    snapshot: Mapping[str, Any],
) -> None:
    prefix = session.session_id
    if scope == "background":
        raw_operations = snapshot.get("manual_operations", {})
        st.session_state[f"{prefix}:background_manual_ops"] = {
            int(index): [dict(item) for item in items]
            for index, items in raw_operations.items()
        }
        st.session_state[f"{prefix}:background_selection_masks"] = _unpack_selection_masks(
            snapshot.get("selection_masks", [])
        )
        _clear_background_floating_selection(prefix)
        return
    if scope == "center":
        offsets = [tuple(map(int, value)) for value in snapshot.get("offsets", [])]
        st.session_state[f"{prefix}:offsets"] = offsets
        for index, offset in enumerate(offsets):
            st.session_state[f"{prefix}:offset_x_widget:{index}"] = offset[0]
            st.session_state[f"{prefix}:offset_y_widget:{index}"] = offset[1]
        ground_line_y = int(snapshot.get("ground_line_y", 0))
        st.session_state[f"{prefix}:center_ground_line_y"] = ground_line_y
        st.session_state[f"{prefix}:center_ground_line_y_widget"] = ground_line_y
        st.session_state[f"{prefix}:center_widget_sync"] = True
        return
    if scope == "cuts":
        st.session_state[f"{prefix}:segmentation_cut_positions"] = list(
            snapshot.get("positions", [])
        )
        st.session_state[f"{prefix}:segmentation_cut_positions_x"] = list(
            snapshot.get("positions_x", [])
        )
        st.session_state[f"{prefix}:segmentation_cut_positions_y"] = list(
            snapshot.get("positions_y", [])
        )
        return
    if scope == "studio":
        pointer = snapshot.get("layer_document")
        if isinstance(pointer, Mapping):
            store.restore_layer_document_attempt(session, pointer)
        else:
            session.layer_document = None
            store.save(session)
        packed_selections = snapshot.get("selection_masks", {})
        st.session_state[f"{prefix}:layer_editor_selection_masks"] = {
            str(key): restored[0]
            for key, value in packed_selections.items()
            if (restored := _unpack_selection_masks([value]))
            and isinstance(restored[0], np.ndarray)
        }
        _clear_floating_selection(prefix)


def _handle_editor_history_event(
    store: SheetSessionStore,
    session: Any,
    event: dict[str, Any] | None,
) -> bool:
    if not event or event.get("type") != "history":
        return False
    event_id = str(event.get("eventId", ""))
    event_key = f"{session.session_id}:editor_history_last_event"
    if not event_id or event_id == st.session_state.get(event_key):
        return False
    st.session_state[event_key] = event_id
    action = str(event.get("action", ""))
    stacks = _history_stacks(session.session_id)
    source_name, target_name, snapshot_name = (
        ("undo", "redo", "before") if action == "undo" else ("redo", "undo", "after")
    )
    if action not in {"undo", "redo"} or not stacks[source_name]:
        return False
    command = stacks[source_name].pop()
    _apply_editor_history_snapshot(
        store,
        session,
        str(command.get("scope", "")),
        command[snapshot_name],
    )
    stacks[target_name].append(command)
    st.session_state[f"{session.session_id}:editor_history_notice"] = (
        f"{'Deshecho' if action == 'undo' else 'Rehecho'}: {command.get('label', 'Edición')}"
    )
    return True


def _history_label(scope: str, event: Mapping[str, Any]) -> str:
    event_type = str(event.get("type", ""))
    if scope == "cuts":
        return "Mover guía de corte"
    if scope == "center":
        if event_type == "guide":
            return "Mover línea de suelo"
        action = str(event.get("action", ""))
        return "Auto Center" if action == "autocenter" else "Mover frame"
    if scope == "background":
        if event_type == "key" and str(event.get("key", "")).lower() in {"delete", "backspace"}:
            return "Borrar selección"
        if event_type == "key":
            return "Cambiar selección"
        tool = _normalize_background_tool(event.get("tool"))
        if event_type == "floating-transform":
            return "Mover selección"
        if event_type == "crop":
            return _background_tool_label(tool)
        return "Borrador" if tool == "eraser" or event_type == "edit-batch" else "Varita"
    if scope == "studio":
        return {
            "edit-batch": "Pintar",
            "paint": "Pintar",
            "transform": "Mover cel",
            "crop": "Cortar selección",
            "floating-transform": "Mover selección",
            "selection": "Cambiar selección",
            "selection-command": "Cambiar selección",
            "clipboard": "Portapapeles",
            "pixel-action": "Transformar píxeles",
        }.get(event_type, "Editar capas")
    return "Edición"


def _editor_event_points(
    event: dict[str, Any],
    *,
    offset_x: int,
    offset_y: int,
) -> tuple[tuple[int, int], ...]:
    raw_path = event.get("path")
    raw_points = raw_path if isinstance(raw_path, (list, tuple)) else ()
    points: list[tuple[int, int]] = []
    for value in raw_points:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            points.append((int(value[0]) - offset_x, int(value[1]) - offset_y))
    if points:
        return tuple(points)
    return ((int(event.get("x", 0)) - offset_x, int(event.get("y", 0)) - offset_y),)


def _symmetry_paths(
    points: Sequence[tuple[int, int]],
    size: tuple[int, int],
    *,
    horizontal: bool,
    vertical: bool,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    width, height = size
    variants = {tuple(points)}
    if horizontal:
        variants.add(tuple((width - 1 - x, y) for x, y in points))
    if vertical:
        variants.update(
            tuple((x, height - 1 - y) for x, y in path)
            for path in tuple(variants)
        )
    return tuple(variants)


def _respect_alpha_lock(
    original: Image.Image,
    edited: Image.Image,
    enabled: bool,
) -> Image.Image:
    if not enabled:
        return edited
    before = np.asarray(original.convert("RGBA"), dtype=np.uint8)
    after = np.asarray(edited.convert("RGBA"), dtype=np.uint8).copy()
    after[before[..., 3] == 0] = before[before[..., 3] == 0]
    return Image.fromarray(after, "RGBA")


def _layer_crop_mask_from_event(
    event: dict[str, Any],
    *,
    cel_size: tuple[int, int],
    offset_x: int,
    offset_y: int,
) -> np.ndarray:
    width, height = cel_size
    mask_image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask_image)
    shape = str(event.get("shape", "lasso"))

    def _point(value: Any) -> tuple[int, int] | None:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return int(value[0]) - offset_x, int(value[1]) - offset_y
        return None

    if shape == "lasso":
        points = [
            point
            for point in (_point(value) for value in event.get("path", ()))
            if point is not None
        ]
        if len(points) >= 3:
            draw.polygon(points, fill=255)
        elif len(points) == 2:
            draw.line(points, fill=255, width=1)
        elif len(points) == 1:
            draw.point(points[0], fill=255)
    else:
        start = _point(event.get("start"))
        end = _point(event.get("end"))
        if start is None or end is None:
            start = (
                int(event.get("startX", event.get("x", 0))) - offset_x,
                int(event.get("startY", event.get("y", 0))) - offset_y,
            )
            end = (
                int(event.get("endX", event.get("x", 0))) - offset_x,
                int(event.get("endY", event.get("y", 0))) - offset_y,
            )
        x0, x1 = sorted((start[0], end[0]))
        y0, y1 = sorted((start[1], end[1]))
        if x0 == x1 and y0 == y1:
            draw.point((x0, y0), fill=255)
        elif shape == "ellipse":
            draw.ellipse((x0, y0, x1, y1), fill=255)
        else:
            draw.rectangle((x0, y0, x1, y1), fill=255)
    return np.asarray(mask_image, dtype=np.uint8).astype(bool)


def _extract_layer_piece(
    image: Image.Image,
    mask: np.ndarray,
) -> tuple[Image.Image, Image.Image]:
    rgba = np.asarray(image.convert("RGBA")).copy()
    if mask.shape != rgba.shape[:2]:
        raise ValueError("Crop mask must match cel size")
    piece = rgba.copy()
    piece[~mask, 3] = 0
    remainder = rgba.copy()
    remainder[mask, 3] = 0
    return Image.fromarray(remainder, "RGBA"), Image.fromarray(piece, "RGBA")


def _floating_selection_highlight(mask: np.ndarray) -> Image.Image:
    """Render a crisp, translucent overlay for a floating Studio selection."""

    highlight = np.zeros((*mask.shape, 4), dtype=np.uint8)
    highlight[mask] = (255, 196, 91, 72)
    return Image.fromarray(highlight, "RGBA")


def _onion_skin_tint(
    image: Image.Image,
    color: tuple[int, int, int],
    opacity: float,
) -> Image.Image:
    """Tint a neighboring frame without interpolation for onion-skin preview."""

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    visible = rgba[..., 3] > 0
    rgba[visible, :3] = np.asarray(color, dtype=np.uint8)
    rgba[..., 3] = np.rint(rgba[..., 3].astype(np.float32) * max(0.0, min(1.0, opacity))).astype(
        np.uint8
    )
    return Image.fromarray(rgba, "RGBA")


def _clear_floating_selection(prefix: str) -> None:
    st.session_state.pop(f"{prefix}:layer_editor_floating_selection", None)


def _layer_selection_key(layer_id: str, frame_index: int) -> str:
    return f"{layer_id}:{int(frame_index)}"


def _layer_selection_mask(
    prefix: str,
    layer_id: str,
    frame_index: int,
) -> np.ndarray | None:
    selections = st.session_state.get(f"{prefix}:layer_editor_selection_masks", {})
    if not isinstance(selections, dict):
        return None
    value = selections.get(_layer_selection_key(layer_id, frame_index))
    return value if isinstance(value, np.ndarray) else None


def _set_layer_selection_mask(
    prefix: str,
    layer_id: str,
    frame_index: int,
    mask: np.ndarray | None,
) -> None:
    key = f"{prefix}:layer_editor_selection_masks"
    selections = dict(st.session_state.get(key, {}))
    selection_key = _layer_selection_key(layer_id, frame_index)
    if mask is None:
        selections.pop(selection_key, None)
    else:
        selections[selection_key] = np.asarray(mask, dtype=bool).copy()
    st.session_state[key] = selections


def _floating_selection_for_frame(
    prefix: str,
    *,
    layer_id: str,
    frame_index: int,
) -> dict[str, Any] | None:
    selection = st.session_state.get(f"{prefix}:layer_editor_floating_selection")
    if not isinstance(selection, dict) or selection.get("layer_id") != layer_id:
        return None
    frames = selection.get("frames")
    if not isinstance(frames, dict):
        return None
    frame = frames.get(frame_index)
    return frame if isinstance(frame, dict) else None


def _opaque_crop_mask(image: Image.Image, mask: np.ndarray) -> np.ndarray:
    """Keep a crop selection to pixels that actually belong to a layer."""

    alpha = np.asarray(image.convert("RGBA"), dtype=np.uint8)[..., 3] > 0
    if alpha.shape != mask.shape:
        raise ValueError("Crop mask must match cel size")
    return mask & alpha


def _crop_target_layer_id(
    document: LayeredSpriteDocument,
    images: dict[tuple[str, int], Image.Image],
    event: dict[str, Any],
    *,
    preferred_layer_id: str,
    frame_index: int,
) -> str | None:
    """Use the active layer first, then the topmost visible painted layer."""

    ordered_ids = [preferred_layer_id] + [
        layer.layer_id
        for layer in reversed(document.layers)
        if layer.layer_id != preferred_layer_id and layer.visible
    ]
    for layer_id in ordered_ids:
        cel = document.cel(layer_id, frame_index)
        image = images.get((layer_id, frame_index))
        if cel is None or image is None:
            continue
        shape_mask = _layer_crop_mask_from_event(
            event,
            cel_size=image.size,
            offset_x=cel.offset_x,
            offset_y=cel.offset_y,
        )
        if _opaque_crop_mask(image, shape_mask).any():
            return layer_id
    return None


def _handle_layer_editor_event(
    store: SheetSessionStore,
    session: Any,
    document: LayeredSpriteDocument,
    images: dict[tuple[str, int], Image.Image],
    event: dict[str, Any] | None,
    *,
    active_layer_id: str,
    active_frame: int,
    target_frames: Sequence[int],
    composite: Image.Image,
) -> bool:
    if not event:
        return False
    prefix = session.session_id
    event_id = event.get("eventId")
    event_key = f"{prefix}:layer_editor_last_event"
    if not event_id or event_id == st.session_state.get(event_key):
        return False
    st.session_state[event_key] = event_id
    event_type = str(event.get("type", ""))
    tool_key = f"{prefix}:layer_editor_tool"
    if event_type == "toolbar" and event.get("action") == "tool":
        st.session_state[tool_key] = _normalize_layer_tool(event.get("tool"))
        return True
    if event_type == "toolbar" and event.get("action") == "zoom":
        st.session_state[f"{prefix}:layer_editor_zoom"] = max(
            1,
            min(40, int(event.get("zoom", 12))),
        )
        return True
    if event_type == "toolbar" and event.get("action") == "brush-radius":
        st.session_state[f"{prefix}:layer_editor_brush_radius"] = max(
            1,
            min(24, int(event.get("brushRadius", 1))),
        )
        return True
    if event_type == "studio":
        action = str(event.get("action", ""))
        requested_layer_id = str(event.get("layerId", ""))
        layer_ids = [layer.layer_id for layer in document.layers]
        if requested_layer_id not in layer_ids:
            return False
        if action == "select-layer":
            _clear_floating_selection(prefix)
            st.session_state[f"{prefix}:layer_editor_active_layer"] = requested_layer_id
            return True
        if action == "select-cel":
            _clear_floating_selection(prefix)
            frame_index = int(event.get("frameIndex", active_frame))
            st.session_state[f"{prefix}:layer_editor_active_layer"] = requested_layer_id
            st.session_state[f"{prefix}:layer_editor_active_frame"] = max(
                0,
                min(document.frame_count - 1, frame_index),
            )
            return True
        if action == "select-range":
            frame_index = max(
                0,
                min(document.frame_count - 1, int(event.get("frameIndex", active_frame))),
            )
            range_start = max(
                0,
                min(document.frame_count - 1, int(event.get("rangeStart", active_frame))),
            )
            start, end = sorted((range_start, frame_index))
            st.session_state[f"{prefix}:layer_editor_active_layer"] = requested_layer_id
            st.session_state[f"{prefix}:layer_editor_active_frame"] = frame_index
            st.session_state[f"{prefix}:layer_editor_selected_frames"] = list(
                range(start, end + 1)
            )
            st.session_state[f"{prefix}:layer_editor_scope"] = "Frames elegidos"
            return True
        if action == "reorder-layer":
            target_layer_id = str(event.get("targetLayerId", ""))
            if target_layer_id not in layer_ids or target_layer_id == requested_layer_id:
                return False
            source_index = layer_ids.index(requested_layer_id)
            target_index = layer_ids.index(target_layer_id)
            # The timeline is displayed top-down whereas documents store layers
            # bottom-up.  Insert immediately above the drop target, compensating
            # for the source row being removed first.
            destination_index = target_index + 1
            if source_index < destination_index:
                destination_index -= 1
            store.save_layer_document(
                session,
                document.reordered(requested_layer_id, destination_index),
                images,
                reason="reorder-layer-drag",
            )
            st.session_state[f"{prefix}:layer_editor_active_layer"] = requested_layer_id
            return True
        return False

    tool = _normalize_layer_tool(event.get("tool", st.session_state.get(tool_key)))
    selection_tools = {"select_lasso", "select_rect", "select_ellipse"}
    frames = tuple(sorted({int(frame) for frame in target_frames}))
    if event_type == "selection" and tool in selection_tools:
        shape_event = dict(event)
        shape_event["shape"] = {
            "select_lasso": "lasso",
            "select_rect": "rect",
            "select_ellipse": "ellipse",
        }[tool]
        changed = False
        for frame_index in frames or (active_frame,):
            cel = document.cel(active_layer_id, frame_index)
            image = images.get((active_layer_id, frame_index))
            if cel is None or image is None:
                continue
            incoming = _layer_crop_mask_from_event(
                shape_event,
                cel_size=image.size,
                offset_x=cel.offset_x,
                offset_y=cel.offset_y,
            )
            current = _layer_selection_mask(prefix, active_layer_id, frame_index)
            combined = combine_selection_masks(
                current,
                incoming,
                mode=_selection_mode_from_event(event),
            )
            _set_layer_selection_mask(prefix, active_layer_id, frame_index, combined)
            changed = True
        return changed

    if event_type == "selection-command":
        action = str(event.get("action", ""))
        changed = False
        for frame_index in frames or (active_frame,):
            image = images.get((active_layer_id, frame_index))
            if image is None:
                continue
            if action == "select-all":
                _set_layer_selection_mask(
                    prefix,
                    active_layer_id,
                    frame_index,
                    np.ones((image.height, image.width), dtype=bool),
                )
                changed = True
            elif action == "deselect":
                _set_layer_selection_mask(prefix, active_layer_id, frame_index, None)
                changed = True
        return changed

    if event_type == "clipboard":
        action = str(event.get("action", ""))
        clipboard_key = f"{prefix}:layer_editor_clipboard"
        if action in {"copy", "cut"}:
            pieces: dict[int, Image.Image] = {}
            masks: dict[int, np.ndarray] = {}
            for frame_index in frames or (active_frame,):
                image = images.get((active_layer_id, frame_index))
                mask = _layer_selection_mask(prefix, active_layer_id, frame_index)
                if image is None or not isinstance(mask, np.ndarray) or not mask.any():
                    continue
                rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
                piece = rgba.copy()
                piece[~mask, 3] = 0
                pieces[frame_index] = Image.fromarray(piece, "RGBA")
                masks[frame_index] = mask.copy()
                if action == "cut":
                    rgba[mask] = (0, 0, 0, 0)
                    images[(active_layer_id, frame_index)] = Image.fromarray(rgba, "RGBA")
            if not pieces:
                return False
            st.session_state[clipboard_key] = {
                "pieces": pieces,
                "masks": masks,
                "source_layer_id": active_layer_id,
                "source_frame": active_frame,
            }
            if action == "cut":
                store.save_layer_document(
                    session,
                    document.revised(),
                    images,
                    reason="cut-selection",
                )
            return True
        if action == "paste":
            clipboard = st.session_state.get(clipboard_key)
            if not isinstance(clipboard, dict):
                return False
            pieces = clipboard.get("pieces")
            masks = clipboard.get("masks")
            if not isinstance(pieces, dict) or not pieces:
                return False
            fallback_piece = next(iter(pieces.values()))
            fallback_mask = next(iter(masks.values())) if isinstance(masks, dict) and masks else None
            changed = False
            for frame_index in frames or (active_frame,):
                image = images.get((active_layer_id, frame_index))
                piece = pieces.get(frame_index, fallback_piece)
                mask = masks.get(frame_index, fallback_mask) if isinstance(masks, dict) else None
                if image is None or not isinstance(piece, Image.Image):
                    continue
                pasted = image.convert("RGBA").copy()
                pasted.alpha_composite(piece.convert("RGBA"))
                images[(active_layer_id, frame_index)] = pasted
                if isinstance(mask, np.ndarray) and mask.shape == (pasted.height, pasted.width):
                    _set_layer_selection_mask(prefix, active_layer_id, frame_index, mask)
                changed = True
            if changed:
                store.save_layer_document(
                    session,
                    document.revised(),
                    images,
                    reason="paste-selection",
                )
            return changed

    if event_type in {"pointer", "pointerdown"} and tool in {"fill", "replace_color"}:
        layer = document.layer(active_layer_id)
        if layer.locked:
            st.session_state[f"{prefix}:layer_editor_notice"] = (
                f"{layer.name} está bloqueada. Selecciona una capa editable."
            )
            return True
        color = tuple(
            int(channel)
            for channel in st.session_state.get(
                f"{prefix}:layer_editor_color", (255, 255, 255, 255)
            )
        )
        tolerance = max(0, min(255, int(event.get("tolerance", 0))))
        changed = False
        for frame_index in frames or (active_frame,):
            cel = document.cel(active_layer_id, frame_index)
            image = images.get((active_layer_id, frame_index))
            if cel is None or image is None:
                continue
            point = (
                int(event.get("x", 0)) - cel.offset_x,
                int(event.get("y", 0)) - cel.offset_y,
            )
            selection = _layer_selection_mask(prefix, active_layer_id, frame_index)
            if tool == "fill":
                region = selection
                if region is None:
                    region = select_similar_pixels(
                        image,
                        seed_point=point,
                        tolerance=tolerance,
                        contiguous=True,
                    )
                edited_image = fill_cel_selection(
                    image,
                    region,
                    color,  # type: ignore[arg-type]
                )
            else:
                source = sample_pixel(image, point)
                edited_image = replace_cel_color(
                    image,
                    source,
                    color,  # type: ignore[arg-type]
                    tolerance=tolerance,
                    mask=selection,
                )
            images[(active_layer_id, frame_index)] = _respect_alpha_lock(
                image,
                edited_image,
                layer.alpha_locked,
            )
            changed = True
        if changed:
            store.save_layer_document(
                session,
                document.revised(),
                images,
                reason=tool,
            )
        return changed

    if event_type == "pixel-action":
        action = str(event.get("action", ""))
        layer = document.layer(active_layer_id)
        if layer.locked:
            return False
        color = tuple(
            int(channel)
            for channel in st.session_state.get(
                f"{prefix}:layer_editor_color", (255, 255, 255, 255)
            )
        )
        changed = False
        for frame_index in frames or (active_frame,):
            image = images.get((active_layer_id, frame_index))
            if image is None:
                continue
            mask = _layer_selection_mask(prefix, active_layer_id, frame_index)
            if action in {
                "flip-horizontal", "flip-vertical", "rotate-cw", "rotate-ccw", "rotate-180",
                "scale-2x", "scale-half",
            }:
                if mask is None or not mask.any():
                    mask = np.ones((image.height, image.width), dtype=bool)
                transformed, next_mask = transform_cel_selection(image, mask, action)
                images[(active_layer_id, frame_index)] = transformed
                _set_layer_selection_mask(prefix, active_layer_id, frame_index, next_mask)
            elif action == "outline":
                images[(active_layer_id, frame_index)] = outline_cel_pixels(
                    image,
                    color,  # type: ignore[arg-type]
                    radius=max(1, int(event.get("radius", 1))),
                    mask=mask,
                )
            elif action == "cleanup-isolated":
                images[(active_layer_id, frame_index)] = remove_isolated_pixels(
                    image,
                    minimum_neighbors=max(0, int(event.get("minimumNeighbors", 2))),
                    mask=mask,
                )
            else:
                continue
            changed = True
        if changed:
            store.save_layer_document(
                session,
                document.revised(),
                images,
                reason=f"pixel-action-{action}",
            )
        return changed

    if event_type == "edit-batch":
        raw_sample = event.get("sample")
        if isinstance(raw_sample, (list, tuple)) and len(raw_sample) == 4:
            sampled = tuple(int(channel) for channel in raw_sample)
            st.session_state[f"{prefix}:layer_editor_color"] = sampled
            st.session_state[f"{prefix}:layer_editor_color_picker_sync"] = _rgb_to_hex(
                sampled[:3]
            )
        layer = document.layer(active_layer_id)
        if layer.locked:
            st.session_state[f"{prefix}:layer_editor_notice"] = (
                f"{layer.name} está bloqueada para preservar la fuente. "
                "Crea o selecciona una capa editable para pintar."
            )
            return True
        frames = tuple(sorted({int(frame) for frame in target_frames}))
        edits = event.get("edits")
        if not frames or not isinstance(edits, (list, tuple)):
            return False
        changed = False
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            edit_tool = _normalize_layer_tool(edit.get("tool"))
            if edit_tool not in {"pencil", "eraser"}:
                continue
            color = edit.get("color", st.session_state[f"{prefix}:layer_editor_color"])
            if not isinstance(color, (list, tuple)) or len(color) != 4:
                color = st.session_state[f"{prefix}:layer_editor_color"]
            rgba = tuple(int(channel) for channel in color)
            for frame_index in frames:
                cel = document.cel(active_layer_id, frame_index)
                if cel is None:
                    continue
                points = _editor_event_points(
                    edit,
                    offset_x=cel.offset_x,
                    offset_y=cel.offset_y,
                )
                original_image = images[(active_layer_id, frame_index)]
                edited_image = original_image
                for symmetry_path in _symmetry_paths(
                    points,
                    original_image.size,
                    horizontal=bool(
                        st.session_state.get(f"{prefix}:layer_symmetry_horizontal", False)
                    ),
                    vertical=bool(
                        st.session_state.get(f"{prefix}:layer_symmetry_vertical", False)
                    ),
                ):
                    edited_image = paint_cel_stroke(
                        edited_image,
                        symmetry_path,
                        color=rgba,  # type: ignore[arg-type]
                        radius=max(0, int(edit.get("brushRadius", 1)) - 1),
                        erase=edit_tool == "eraser",
                    )
                images[(active_layer_id, frame_index)] = _respect_alpha_lock(
                    original_image,
                    edited_image,
                    layer.alpha_locked and edit_tool != "eraser",
                )
                changed = True
        if changed:
            store.save_layer_document(session, document.revised(), images, reason="paint-batch")
        return changed
    if event_type in {"pointer", "pointerdown"} and tool == "eyedropper":
        sampled = sample_pixel(
            composite,
            (int(event.get("x", 0)), int(event.get("y", 0))),
        )
        st.session_state[f"{prefix}:layer_editor_color"] = sampled
        # The colour picker widget is rendered before the canvas.  Schedule its
        # value for the next component-driven rerun so it does not overwrite a
        # colour just picked from the canvas with its previous widget value.
        st.session_state[f"{prefix}:layer_editor_color_picker_sync"] = _rgb_to_hex(
            sampled[:3]
        )
        return True

    layer = document.layer(active_layer_id)
    can_move_locked_source = event_type == "transform" and tool == "move"
    can_move_floating_selection = event_type == "floating-transform" and tool == "move"
    can_cancel_floating_selection = event_type == "floating-selection" and event.get("action") == "cancel"
    can_cut_locked_source = event_type == "crop" and tool in {
        "crop_lasso",
        "crop_rect",
        "crop_ellipse",
    }
    if (
        layer.locked
        and not can_move_locked_source
        and not can_move_floating_selection
        and not can_cancel_floating_selection
        and not can_cut_locked_source
    ):
        st.session_state[f"{prefix}:layer_editor_notice"] = (
            f"{layer.name} está bloqueada para preservar la fuente. "
            "Puedes moverla con M, pero pinta sobre una capa editable."
        )
        return True

    if not frames:
        return False
    if event_type == "floating-selection" and event.get("action") == "cancel":
        selection = st.session_state.get(f"{prefix}:layer_editor_floating_selection")
        floating_frames = selection.get("frames") if isinstance(selection, dict) else None
        selection_layer_id = (
            str(selection.get("layer_id"))
            if isinstance(selection, dict) and selection.get("layer_id")
            else active_layer_id
        )
        restored = False
        if isinstance(floating_frames, dict):
            for frame_index, floating in floating_frames.items():
                original = floating.get("original") if isinstance(floating, dict) else None
                if isinstance(original, Image.Image):
                    images[(selection_layer_id, int(frame_index))] = original
                    restored = True
        if restored:
            store.save_layer_document(
                session,
                document.revised(),
                images,
                reason="cancel-floating-selection",
            )
        _clear_floating_selection(prefix)
        return True
    if event_type == "crop" and tool in {"crop_lasso", "crop_rect", "crop_ellipse"}:
        shape = str(event.get("shape", "lasso"))
        crop_layer_id = _crop_target_layer_id(
            document,
            images,
            event,
            preferred_layer_id=active_layer_id,
            frame_index=active_frame,
        )
        if crop_layer_id is None:
            st.session_state[f"{prefix}:layer_editor_notice"] = (
                "El recorte no tocó píxeles visibles en ninguna capa."
            )
            return True
        floating_frames: dict[int, dict[str, Any]] = {}
        for frame_index in frames:
            cel = document.cel(crop_layer_id, frame_index)
            if cel is None:
                continue
            image = images[(crop_layer_id, frame_index)]
            mask = _layer_crop_mask_from_event(
                event,
                cel_size=image.size,
                offset_x=cel.offset_x,
                offset_y=cel.offset_y,
            )
            mask = _opaque_crop_mask(image, mask)
            if mask.any():
                remainder, piece = _extract_layer_piece(image, mask)
                images[(crop_layer_id, frame_index)] = remainder
                rows, columns = np.where(mask)
                floating_frames[frame_index] = {
                    "mask": mask,
                    "piece": piece,
                    "original": image.copy(),
                    "offset_x": cel.offset_x,
                    "offset_y": cel.offset_y,
                    "bounds": (
                        int(columns.min()),
                        int(rows.min()),
                        int(columns.max()) + 1,
                        int(rows.max()) + 1,
                    ),
                }
        if not floating_frames:
            st.session_state[f"{prefix}:layer_editor_notice"] = (
                "El recorte no encontró píxeles en los frames elegidos."
            )
            return False
        st.session_state[f"{prefix}:layer_editor_floating_selection"] = {
            "layer_id": crop_layer_id,
            "frames": floating_frames,
            "shape": shape,
        }
        # The cut is saved immediately. The detached pixels remain in transient
        # state only so Esc can restore the exact original cel.
        store.save_layer_document(
            session,
            document.revised(),
            images,
            reason=f"cut-floating-selection-{shape}",
        )
        st.session_state[tool_key] = "move"
        st.session_state[f"{prefix}:layer_editor_active_layer"] = crop_layer_id
        st.session_state[f"{prefix}:layer_editor_notice"] = (
            "Selección flotante lista. Arrástrala para moverla; Esc cancela."
        )
        return True
    if event_type == "floating-transform" and tool == "move":
        selection = st.session_state.get(f"{prefix}:layer_editor_floating_selection")
        if not isinstance(selection, dict) or selection.get("layer_id") != active_layer_id:
            return False
        floating_frames = selection.get("frames")
        if not isinstance(floating_frames, dict):
            return False
        delta_x = int(event.get("deltaX", 0))
        delta_y = int(event.get("deltaY", 0))
        changed = False
        for frame_index in frames:
            floating = floating_frames.get(frame_index)
            cel = document.cel(active_layer_id, frame_index)
            if not isinstance(floating, dict) or cel is None:
                continue
            piece = floating.get("piece")
            image = images.get((active_layer_id, frame_index))
            if not isinstance(piece, Image.Image) or image is None:
                continue
            moved = image.copy()
            moved.alpha_composite(piece, dest=(delta_x, delta_y))
            images[(active_layer_id, frame_index)] = moved
            changed = True
        if changed:
            store.save_layer_document(session, document.revised(), images, reason="place-floating-selection")
        _clear_floating_selection(prefix)
        return changed
    if event_type == "paint" and tool in {"pencil", "eraser"}:
        color = st.session_state.get(f"{prefix}:layer_editor_color", (255, 255, 255, 255))
        rgba = tuple(int(channel) for channel in color)
        for frame_index in frames:
            cel = document.cel(active_layer_id, frame_index)
            if cel is None:
                continue
            points = _editor_event_points(
                event,
                offset_x=cel.offset_x,
                offset_y=cel.offset_y,
            )
            original_image = images[(active_layer_id, frame_index)]
            edited_image = original_image
            for symmetry_path in _symmetry_paths(
                points,
                original_image.size,
                horizontal=bool(
                    st.session_state.get(f"{prefix}:layer_symmetry_horizontal", False)
                ),
                vertical=bool(
                    st.session_state.get(f"{prefix}:layer_symmetry_vertical", False)
                ),
            ):
                edited_image = paint_cel_stroke(
                    edited_image,
                    symmetry_path,
                    color=rgba,  # type: ignore[arg-type]
                    radius=max(0, int(event.get("brushRadius", 1)) - 1),
                    erase=tool == "eraser",
                )
            images[(active_layer_id, frame_index)] = _respect_alpha_lock(
                original_image,
                edited_image,
                layer.alpha_locked and tool != "eraser",
            )
        store.save_layer_document(session, document.revised(), images, reason=tool)
        return True

    if event_type == "transform" and tool == "move":
        current = document.cel(active_layer_id, active_frame)
        if current is None:
            return False
        next_x = int(event.get("offsetX", current.offset_x))
        next_y = int(event.get("offsetY", current.offset_y))
        delta_x = next_x - current.offset_x
        delta_y = next_y - current.offset_y
        updated = document
        for frame_index in frames:
            cel = updated.cel(active_layer_id, frame_index)
            if cel is not None:
                updated = updated.with_cel_offset(
                    active_layer_id,
                    frame_index,
                    offset_x=cel.offset_x + delta_x,
                    offset_y=cel.offset_y + delta_y,
                )
        store.save_layer_document(session, updated, images, reason="move-cel")
        return True
    return False


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
        cell = int(resolved.cell_height or source_size[1])
        count = resolved.frame_count
        spacing = resolved.spacing_y
    elif resolved.orientation == "horizontal":
        start = resolved.offset_x
        cell = int(resolved.cell_width or source_size[0])
        count = resolved.frame_count
        spacing = resolved.spacing_x
    else:
        start = resolved.offset_x
        cell = int(resolved.cell_width or source_size[0])
        count = resolved.columns
        spacing = resolved.spacing_x
    step = cell + spacing
    return tuple(
        int(round(start + step * index)) for index in range(1, count)
    )


def _auto_cut_axes(
    source: Image.Image,
    config: SegmentationConfig,
    anchor_config: AutoCenterConfig,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    return auto_cut_positions(source, config, anchor_config)


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


def _effective_segmentation_frame_count(
    orientation: str,
    requested_frame_count: int,
    rows: int,
    columns: int,
) -> int:
    """Use every visible grid cell while preserving linear frame counts."""
    if orientation == "grid":
        return max(1, int(rows)) * max(1, int(columns))
    return max(1, int(requested_frame_count))


def _normalized_grid_cut_positions(
    source_size: tuple[int, int],
    config: SegmentationConfig,
    positions_x: Sequence[int] | None,
    positions_y: Sequence[int] | None,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if config.orientation != "grid":
        return (), ()
    if max(1, int(config.rows)) * max(1, int(config.columns)) < int(config.frame_count):
        return (), ()
    resolved, _ = resolve_segmentation_config(
        source_size,
        SegmentationConfig(
            frame_count=config.frame_count,
            orientation="grid",
            rows=config.rows,
            columns=config.columns,
            cell_width=config.cell_width,
            cell_height=config.cell_height,
            offset_x=config.offset_x,
            offset_y=config.offset_y,
            spacing_x=config.spacing_x,
            spacing_y=config.spacing_y,
        ),
    )
    desired_x = max(0, resolved.columns - 1)
    desired_y = max(0, resolved.rows - 1)
    raw_x = tuple(int(value) for value in (positions_x or ()))
    raw_y = tuple(int(value) for value in (positions_y or ()))
    if len(raw_x) != desired_x:
        raw_x = tuple(
            resolved.offset_x + index * (resolved.cell_width + resolved.spacing_x)
            for index in range(1, resolved.columns)
        )
    if len(raw_y) != desired_y:
        raw_y = tuple(
            resolved.offset_y + index * (resolved.cell_height + resolved.spacing_y)
            for index in range(1, resolved.rows)
        )
    return raw_x, raw_y


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
            "manual_cut_positions_x": list(config.manual_cut_positions_x),
            "manual_cut_positions_y": list(config.manual_cut_positions_y),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    if config.orientation == "grid":
        saved_x, saved_y = _normalized_grid_cut_positions(
            source_size,
            config,
            config.manual_cut_positions_x,
            config.manual_cut_positions_y,
        )
        saved = ()
    else:
        saved = _normalized_segmentation_cut_positions(
            source_size,
            config,
            config.manual_cut_positions,
        )
        saved_x = saved if config.orientation == "horizontal" else ()
        saved_y = saved if config.orientation == "vertical" else ()
    cuts_x_key = f"{prefix}:segmentation_cut_positions_x"
    cuts_y_key = f"{prefix}:segmentation_cut_positions_y"
    legacy_expected = max(0, config.frame_count - 1) if config.orientation != "grid" else 0
    state_invalid = (
        len(st.session_state.get(cuts_key, ())) != legacy_expected
        or len(st.session_state.get(cuts_x_key, ())) != len(saved_x)
        or len(st.session_state.get(cuts_y_key, ())) != len(saved_y)
    )
    if (
        cuts_key not in st.session_state
        or st.session_state.get(sync_key) != signature
        or state_invalid
    ):
        st.session_state[cuts_key] = list(saved)
        st.session_state[cuts_x_key] = list(saved_x)
        st.session_state[cuts_y_key] = list(saved_y)
        st.session_state[sync_key] = signature
    return tuple(int(value) for value in st.session_state[cuts_key])


def _ensure_segmentation_cut_controls_state(session: Any) -> None:
    prefix = session.session_id
    zoom_key = f"{prefix}:segmentation_cut_zoom"
    free_key = f"{prefix}:segmentation_free_adjust"
    free_widget_key = f"{free_key}_widget"
    free_sync_key = f"{free_key}_widget_sync"
    if zoom_key not in st.session_state:
        st.session_state[zoom_key] = 8
    if free_key not in st.session_state:
        st.session_state[free_key] = False
    if free_sync_key in st.session_state:
        st.session_state[free_widget_key] = st.session_state.pop(free_sync_key)
    elif free_widget_key not in st.session_state:
        st.session_state[free_widget_key] = st.session_state[free_key]


def _set_auto_segmentation_cuts(
    session: Any,
    source: Image.Image,
    config: SegmentationConfig,
    anchor_config: AutoCenterConfig,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    prefix = session.session_id
    cuts_x, cuts_y = _auto_cut_axes(source, config, anchor_config)
    cuts = list(cuts_x if config.orientation == "horizontal" else cuts_y)
    st.session_state[f"{prefix}:segmentation_cut_positions"] = cuts
    st.session_state[f"{prefix}:segmentation_cut_positions_x"] = list(cuts_x)
    st.session_state[f"{prefix}:segmentation_cut_positions_y"] = list(cuts_y)
    st.session_state[f"{prefix}:segmentation_cut_positions_sig"] = json.dumps(
        {
            "source_size": [source.width, source.height],
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
            "manual_cut_positions_x": list(cuts_x),
            "manual_cut_positions_y": list(cuts_y),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return tuple(cuts_x), tuple(cuts_y)


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


def _alignment_export_readiness(
    manifest: dict[str, Any] | None,
    *,
    segmentation_config: SegmentationConfig,
    background_config: BackgroundRemovalConfig,
    center_config: AutoCenterConfig,
    manual_offsets: Sequence[tuple[int, int]],
    locks: Sequence[bool],
    frame_count: int,
) -> tuple[bool, str]:
    if not manifest:
        return False, "Guarda primero la alineación actual en Auto Center."
    if manifest.get("status") != "passed":
        return False, "La alineación guardada todavía requiere revisión manual."
    config = manifest.get("config")
    if not isinstance(config, dict):
        return False, "El manifest de alineación no contiene una configuración válida."
    expected = {
        "segmentation": segmentation_config.to_dict(),
        "background": background_config.to_dict(),
        "auto_center": center_config.to_dict(),
        "manual_offsets": [list(map(int, offset)) for offset in manual_offsets],
    }
    for key, value in expected.items():
        if config.get(key) != value:
            return False, "Auto Center cambió desde la última alineación guardada."
    frames = manifest.get("metadata", {}).get("frames", ())
    if not isinstance(frames, list) or len(frames) != frame_count:
        return False, "El manifest de alineación no coincide con los frames actuales."
    saved_locks = [bool(item.get("locked", False)) for item in frames if isinstance(item, dict)]
    if saved_locks != [bool(value) for value in locks]:
        return False, "La aprobación de anchors cambió; vuelve a guardar Auto Center."
    if any(bool(item.get("manual_review", True)) for item in frames if isinstance(item, dict)):
        return False, "La alineación guardada todavía contiene anchors en revisión."
    return True, ""


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


def _ensure_background_editor_state(
    session: Any,
    count: int,
    *,
    default_tolerance: float = 0,
    default_contiguous: bool = True,
) -> None:
    prefix = session.session_id
    tool_key = f"{prefix}:background_tool"
    tool_widget_key = f"{prefix}:background_tool_widget"
    color_key = f"{prefix}:background_sampled_color"
    selection_key = f"{prefix}:background_selection_masks"
    zoom_key = f"{prefix}:background_zoom"
    brush_key = f"{prefix}:background_brush_radius"
    brush_widget_key = f"{prefix}:background_brush_radius_widget"
    tolerance_key = f"{prefix}:background_wand_tolerance"
    contiguous_key = f"{prefix}:background_wand_contiguous"
    event_key = f"{prefix}:background_last_event"
    floating_key = f"{prefix}:background_floating_selection"
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
    if tolerance_key not in st.session_state:
        st.session_state[tolerance_key] = max(0, min(255, int(default_tolerance)))
    if contiguous_key not in st.session_state:
        st.session_state[contiguous_key] = bool(default_contiguous)
    if event_key not in st.session_state:
        st.session_state[event_key] = None
    if floating_key not in st.session_state:
        st.session_state[floating_key] = None


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
        if action == "wand-settings":
            st.session_state[f"{prefix}:background_wand_tolerance"] = max(
                0,
                min(255, int(event.get("wandTolerance", tolerance))),
            )
            st.session_state[f"{prefix}:background_wand_contiguous"] = bool(
                event.get("wandContiguous", contiguous)
            )
            return True
        if action == "zoom":
            zoom = int(event.get("zoom", st.session_state.get(f"{prefix}:background_zoom", 8)))
            st.session_state[f"{prefix}:background_zoom"] = max(1, min(40, zoom))
            return True
        return False

    event_type = str(event.get("type", ""))
    if event_type == "floating-selection" and event.get("action") == "cancel":
        _clear_background_floating_selection(prefix)
        selections = list(st.session_state[f"{prefix}:background_selection_masks"])
        selections[selected_frame] = None
        st.session_state[f"{prefix}:background_selection_masks"] = selections
        st.session_state[f"{prefix}:background_tool"] = "wand"
        st.session_state[f"{prefix}:background_tool_widget_sync"] = "wand"
        return True
    if event_type == "crop":
        tool = _normalize_background_tool(
            event.get("tool", st.session_state[f"{prefix}:background_tool"])
        )
        if tool not in {"crop_lasso", "crop_rect", "crop_ellipse"}:
            return False
        frame = frames[selected_frame]
        incoming = _layer_crop_mask_from_event(
            event,
            cel_size=frame.size,
            offset_x=0,
            offset_y=0,
        )
        selections = list(st.session_state[f"{prefix}:background_selection_masks"])
        current = selections[selected_frame]
        combined = combine_selection_masks(
            current if isinstance(current, np.ndarray) else None,
            incoming,
            mode=_selection_mode_from_event(event),
        )
        combined = _opaque_crop_mask(frame, combined)
        if not combined.any():
            _clear_background_floating_selection(prefix)
            selections[selected_frame] = None
            st.session_state[f"{prefix}:background_selection_masks"] = selections
            return True
        remainder, piece = _extract_layer_piece(frame, combined)
        rows, columns = np.where(combined)
        selections[selected_frame] = combined
        st.session_state[f"{prefix}:background_selection_masks"] = selections
        st.session_state[f"{prefix}:background_floating_selection"] = {
            "frame_index": selected_frame,
            "mask": combined,
            "piece": piece,
            "remainder": remainder,
            "tool": tool,
            "bounds": (
                int(columns.min()),
                int(rows.min()),
                int(columns.max()) + 1,
                int(rows.max()) + 1,
            ),
        }
        st.session_state[f"{prefix}:background_tool"] = "move"
        st.session_state[f"{prefix}:background_tool_widget_sync"] = "move"
        return True
    if event_type == "floating-transform":
        floating = st.session_state.get(f"{prefix}:background_floating_selection")
        if not isinstance(floating, dict) or int(floating.get("frame_index", -1)) != selected_frame:
            return False
        mask = floating.get("mask")
        if not isinstance(mask, np.ndarray) or mask.shape != (
            frames[selected_frame].height,
            frames[selected_frame].width,
        ):
            _clear_background_floating_selection(prefix)
            return False
        delta_x = int(event.get("deltaX", 0))
        delta_y = int(event.get("deltaY", 0))
        operations = {
            int(index): [dict(item) for item in items]
            for index, items in st.session_state[f"{prefix}:background_manual_ops"].items()
        }
        operations.setdefault(selected_frame, []).append(
            {
                "kind": "move_mask",
                **encode_mask(mask),
                "offset_x": delta_x,
                "offset_y": delta_y,
            }
        )
        st.session_state[f"{prefix}:background_manual_ops"] = operations
        selections = list(st.session_state[f"{prefix}:background_selection_masks"])
        selections[selected_frame] = None
        st.session_state[f"{prefix}:background_selection_masks"] = selections
        next_tool = _normalize_background_tool(floating.get("tool", "wand"))
        _clear_background_floating_selection(prefix)
        st.session_state[f"{prefix}:background_tool"] = next_tool
        st.session_state[f"{prefix}:background_tool_widget_sync"] = next_tool
        return True
    if event_type == "edit-batch":
        raw_sample = event.get("sample")
        if isinstance(raw_sample, (list, tuple)) and len(raw_sample) == 4:
            st.session_state[f"{prefix}:background_sampled_color"] = tuple(
                int(channel) for channel in raw_sample
            )
        edits = event.get("edits")
        if not isinstance(edits, (list, tuple)):
            return False
        operations = {
            int(index): [dict(item) for item in items]
            for index, items in st.session_state[f"{prefix}:background_manual_ops"].items()
        }
        applied = False
        for edit in edits:
            if not isinstance(edit, dict) or edit.get("tool") != "eraser":
                continue
            path = _editor_event_points(edit, offset_x=0, offset_y=0)
            if not path:
                continue
            operations.setdefault(selected_frame, []).append(
                {
                    "kind": "erase_brush",
                    "point": list(path[-1]),
                    "radius": max(1, int(edit.get("brushRadius", 1))),
                    "path": [list(point) for point in path],
                }
            )
            applied = True
        if applied:
            selections = list(st.session_state[f"{prefix}:background_selection_masks"])
            selections[selected_frame] = None
            st.session_state[f"{prefix}:background_manual_ops"] = operations
            st.session_state[f"{prefix}:background_selection_masks"] = selections
        return applied
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
    event_tolerance = max(0, min(255, int(event.get("wandTolerance", tolerance))))
    event_contiguous = bool(event.get("wandContiguous", contiguous))
    incoming = select_similar_pixels(
        frame,
        seed_point=(x, y),
        tolerance=event_tolerance,
        contiguous=event_contiguous,
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
    base_manual_offset: tuple[int, int] = (0, 0),
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
        offsets[selected_frame] = (
            int(base_manual_offset[0]) + offset_x - int(home_offset[0]),
            int(base_manual_offset[1]) + offset_y - int(home_offset[1]),
        )
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
    *,
    orientation: str = "horizontal",
    columns: int = 1,
    rows: int = 1,
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
    if orientation == "grid":
        cuts_x = event.get("cutPositionsX")
        cuts_y = event.get("cutPositionsY")
        if not isinstance(cuts_x, (list, tuple)) or not isinstance(cuts_y, (list, tuple)):
            return False
        normalized_x = [int(value) for value in cuts_x]
        normalized_y = [int(value) for value in cuts_y]
        if len(normalized_x) != max(0, columns - 1) or len(normalized_y) != max(0, rows - 1):
            return False
        st.session_state[f"{prefix}:segmentation_cut_positions_x"] = normalized_x
        st.session_state[f"{prefix}:segmentation_cut_positions_y"] = normalized_y
        st.session_state[f"{prefix}:segmentation_cut_positions"] = []
        return True
    cuts = event.get("cutPositions")
    if not isinstance(cuts, (list, tuple)):
        return False
    normalized = [int(value) for value in cuts]
    if len(normalized) != max(0, count - 1):
        return False
    st.session_state[f"{prefix}:segmentation_cut_positions"] = normalized
    if orientation == "horizontal":
        st.session_state[f"{prefix}:segmentation_cut_positions_x"] = normalized
    elif orientation == "vertical":
        st.session_state[f"{prefix}:segmentation_cut_positions_y"] = normalized
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


def _sync_center_lock(prefix: str, frame_index: int) -> None:
    locks_key = f"{prefix}:locks"
    widget_key = f"{prefix}:locked:{frame_index}"
    locks = list(st.session_state.get(locks_key, ()))
    if not 0 <= frame_index < len(locks):
        return
    locks[frame_index] = bool(st.session_state.get(widget_key, False))
    st.session_state[locks_key] = locks


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


def _export_preview_columns(
    layout: str,
    frame_count: int,
    grid_columns: int | None,
) -> int:
    """Match the contact preview geometry to the actual exported sheet."""

    count = max(1, int(frame_count))
    if layout == "vertical":
        return 1
    if layout == "grid":
        return max(1, min(count, int(grid_columns or 1)))
    return count


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


def _center_analysis_signature(
    frames: Sequence[Image.Image],
    config: AutoCenterConfig,
    *,
    frames_signature: str | None = None,
) -> str:
    digest = hashlib.sha256()
    digest.update(config.method.encode("utf-8"))
    digest.update(str(len(frames)).encode("ascii"))
    if frames_signature:
        digest.update(frames_signature.encode("utf-8"))
        return digest.hexdigest()
    for frame in frames:
        rgba = frame.convert("RGBA")
        digest.update(f"{rgba.width}x{rgba.height}".encode("ascii"))
        digest.update(rgba.tobytes())
    return digest.hexdigest()


def _ensure_center_analysis(
    session: Any,
    frames: Sequence[Image.Image],
    config: AutoCenterConfig,
    *,
    frames_signature: str | None = None,
) -> CenteringAnalysis:
    prefix = session.session_id
    cache_key = f"{prefix}:center_analysis_cache"
    signature = _center_analysis_signature(
        frames,
        config,
        frames_signature=frames_signature,
    )
    cached = st.session_state.get(cache_key)
    if isinstance(cached, dict) and cached.get("signature") == signature:
        analysis = cached.get("analysis")
        if isinstance(analysis, CenteringAnalysis):
            return analysis
    analysis = analyze_center_frames(frames, config)
    st.session_state[cache_key] = {
        "signature": signature,
        "analysis": analysis,
    }
    return analysis


def _stable_ui_signature(value: Any) -> str:
    """Return a compact deterministic key for already-verified UI inputs."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ensure_sheet_processing(
    session: Any,
    source: Image.Image,
    background_config: BackgroundRemovalConfig,
    segmentation_config: SegmentationConfig,
    manual_operations: dict[int, list[dict[str, Any]]],
) -> tuple[Image.Image, Any, str]:
    """Reuse background removal and segmentation across component reruns.

    The source is verified by ``SheetSessionStore.load`` at the beginning of every
    Streamlit run.  Manual operations and both configs are part of the key, so an
    edit invalidates only this derived in-memory result.
    """

    signature = _stable_ui_signature(
        {
            "source_sha256": session.source_sha256,
            "background": background_config.to_dict(),
            "segmentation": segmentation_config.to_dict(),
            "manual_operations": manual_operations,
        }
    )
    cache_key = f"{session.session_id}:sheet_processing_cache"
    cached = st.session_state.get(cache_key)
    if isinstance(cached, dict) and cached.get("signature") == signature:
        cached_background = cached.get("background_source")
        cached_segmentation = cached.get("segmentation")
        if isinstance(cached_background, Image.Image) and cached_segmentation is not None:
            return cached_background, cached_segmentation, signature

    background_source = apply_background_removal((source,), background_config)[0]
    background_source = apply_manual_background_edits(
        (background_source,),
        manual_operations,
    )[0]
    segmentation = segment_sheet(
        background_source,
        segmentation_config,
        background_rgb=background_config.color,
    )
    st.session_state[cache_key] = {
        "signature": signature,
        "background_source": background_source,
        "segmentation": segmentation,
    }
    return background_source, segmentation, signature


def _ensure_center_result(
    session: Any,
    frames: Sequence[Image.Image],
    config: AutoCenterConfig,
    analysis: CenteringAnalysis,
    *,
    frames_signature: str,
    manual_offsets: Sequence[tuple[int, int]],
    locked: Sequence[bool],
    notes: Sequence[str],
) -> CenteringResult:
    """Cache Auto Center output while preserving frame-local invalidation."""

    signature = _stable_ui_signature(
        {
            "frames": frames_signature,
            "auto_center": config.to_dict(),
            "manual_offsets": [list(map(int, value)) for value in manual_offsets],
            "locked": [bool(value) for value in locked],
            "notes": [str(value) for value in notes],
        }
    )
    cache_key = f"{session.session_id}:center_result_cache"
    cached = st.session_state.get(cache_key)
    if isinstance(cached, dict) and cached.get("signature") == signature:
        result = cached.get("result")
        if isinstance(result, CenteringResult):
            return result
    result = auto_center_frames(
        frames,
        config,
        manual_offsets=manual_offsets,
        locked=locked,
        notes=notes,
        overflow_strategy="clamp",
        analysis=analysis,
        target_anchor=config.canonical_anchor,
    )
    st.session_state[cache_key] = {"signature": signature, "result": result}
    return result


def _ensure_segmentation_guide_overlay(
    session: Any,
    background_source: Image.Image,
    segmentation: Any,
    *,
    processing_signature: str,
) -> Image.Image:
    cache_key = f"{session.session_id}:segmentation_guide_overlay_cache"
    cached = st.session_state.get(cache_key)
    if isinstance(cached, dict) and cached.get("signature") == processing_signature:
        overlay = cached.get("overlay")
        if isinstance(overlay, Image.Image):
            return overlay
    overlay = render_segmentation_guides(background_source, segmentation)
    st.session_state[cache_key] = {
        "signature": processing_signature,
        "overlay": overlay,
    }
    return overlay


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


@st.fragment
def _render_export_preview_fragment(
    *,
    prefix: str,
    frames: Sequence[Image.Image],
    adjustments: Sequence[FrameAdjustment],
    columns: int,
    origin_offset: tuple[int, int],
) -> None:
    """Refresh guide toggles without rerunning every editor tab."""

    guide_col, axis_col, anchor_col = st.columns(3)
    show_cell_guides = guide_col.checkbox(
        "Cortes",
        value=True,
        key=f"{prefix}:export_preview_cell_guides",
    )
    show_axes = axis_col.checkbox(
        "Ejes XY",
        value=True,
        key=f"{prefix}:export_preview_axes",
    )
    show_anchors = anchor_col.checkbox(
        "Anchors",
        value=True,
        key=f"{prefix}:export_preview_anchors",
    )
    _show_pixel(
        render_contact_sheet(
            frames,
            adjustments=adjustments,
            columns=columns,
            origin_offset=origin_offset,
            show_cell_guides=show_cell_guides,
            show_center_axes=show_axes,
            show_anchor_guides=show_anchors,
            show_bbox=False,
            guide_padding=8 if (show_cell_guides or show_axes or show_anchors) else 0,
            guide_display_width=820,
        ),
        "Preview final con anchors y recorte",
        max_height=640,
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

    with st.sidebar.expander("Crear sprite desde cero"):
        new_col1, new_col2 = st.columns(2)
        new_width = int(
            new_col1.number_input(
                "Ancho",
                min_value=1,
                max_value=2048,
                value=64,
                key="new_sprite_width",
            )
        )
        new_height = int(
            new_col2.number_input(
                "Alto",
                min_value=1,
                max_value=2048,
                value=64,
                key="new_sprite_height",
            )
        )
        new_frames = int(
            st.number_input(
                "Frames iniciales",
                min_value=1,
                max_value=64,
                value=4,
                key="new_sprite_frames",
            )
        )
        if st.button("Crear lienzo transparente", width="stretch", key="new_sprite_create"):
            session = store.create_blank_sprite(
                canvas_width=new_width,
                canvas_height=new_height,
                frame_count=new_frames,
            )
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
    page = _render_header_navigation()
    st.sidebar.markdown("# sprite-builder")
    st.sidebar.caption("Godot-ready pixel sprite pipeline")
    if page == "tilesets":
        _render_tileset_builder()
        st.sidebar.markdown("---")
        st.sidebar.caption(f"Workspace: {workspace}")
        st.sidebar.caption("Procesamiento local · sin APIs externas")
        return

    store = SheetSessionStore(workspace)
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
    if orientation == "grid":
        requested_frame_count = session.segmentation_config.frame_count
        frame_count = _effective_segmentation_frame_count(
            orientation,
            requested_frame_count,
            rows,
            columns,
        )
        st.sidebar.metric("Número de frames", frame_count)
        st.sidebar.caption(
            f"Grid completo: {rows} filas × {columns} columnas = {frame_count} frames"
        )
    else:
        requested_frame_count = int(
            st.sidebar.number_input(
                "Número de frames",
                min_value=1,
                max_value=512,
                value=session.segmentation_config.frame_count,
                step=1,
                key=f"{session.session_id}:frame_count",
            )
        )
        frame_count = _effective_segmentation_frame_count(
            orientation,
            requested_frame_count,
            rows,
            columns,
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
    current_cut_positions = (
        ()
        if segmentation_config.orientation == "grid"
        else _normalized_segmentation_cut_positions(
            source.size,
            segmentation_config,
            st.session_state.get(
                f"{session.session_id}:segmentation_cut_positions",
                session.segmentation_config.manual_cut_positions,
            ),
        )
    )
    current_cut_positions_x, current_cut_positions_y = (
        _normalized_grid_cut_positions(
            source.size,
            segmentation_config,
            st.session_state.get(
                f"{session.session_id}:segmentation_cut_positions_x",
                session.segmentation_config.manual_cut_positions_x,
            ),
            st.session_state.get(
                f"{session.session_id}:segmentation_cut_positions_y",
                session.segmentation_config.manual_cut_positions_y,
            ),
        )
        if segmentation_config.orientation == "grid"
        else ((), ())
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
        manual_cut_positions_x=current_cut_positions_x,
        manual_cut_positions_y=current_cut_positions_y,
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
        manual_cut_positions_x=tuple(
            int(value)
            for value in st.session_state.get(
                f"{session.session_id}:segmentation_cut_positions_x",
                segmentation_config.manual_cut_positions_x,
            )
        ),
        manual_cut_positions_y=tuple(
            int(value)
            for value in st.session_state.get(
                f"{session.session_id}:segmentation_cut_positions_y",
                segmentation_config.manual_cut_positions_y,
            )
        ),
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
    working_frames: tuple[Image.Image, ...] = ()
    centered = None
    center_analysis: CenteringAnalysis | None = None
    center_error: str | None = None
    processing_error: str | None = None
    try:
        _ensure_manual_background_state(store, session, 1)
        _ensure_background_editor_state(
            session,
            1,
            default_tolerance=background_config.tolerance,
        )
        prefix = session.session_id
        background_source, segmentation, processing_signature = _ensure_sheet_processing(
            session,
            source,
            background_config,
            segmentation_config,
            st.session_state[f"{prefix}:background_manual_ops"],
        )
        background_frames = segmentation.frames
        working_frames = background_frames
        working_frames_signature = processing_signature
        if "artwork" in session.stages:
            try:
                artwork_frames = _load_stage_frames(store, session, "artwork")
                if len(artwork_frames) == len(background_frames):
                    working_frames = artwork_frames
                    working_frames_signature = _stable_ui_signature(
                        {
                            "processing": processing_signature,
                            "artwork": session.stages.get("artwork", {}),
                        }
                    )
            except ArtifactIntegrityError:
                pass
        _ensure_adjustment_state(session, len(working_frames))
        center_analysis = _ensure_center_analysis(
            session,
            working_frames,
            center_config,
            frames_signature=working_frames_signature,
        )
        try:
            centered = _ensure_center_result(
                session,
                working_frames,
                center_config,
                center_analysis,
                frames_signature=working_frames_signature,
                manual_offsets=st.session_state[f"{prefix}:offsets"],
                locked=st.session_state[f"{prefix}:locks"],
                notes=st.session_state[f"{prefix}:notes"],
            )
        except (OverflowError, IndexError) as exc:
            center_error = str(exc)
            centered = _fallback_centering(working_frames, center_config)
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

    global_history = _history_controls(session)
    history_col1, history_col2, history_status = st.columns((0.8, 0.8, 4.4), gap="small")
    with history_col1:
        if st.button(
            "↶ Deshacer",
            disabled=not global_history["can_undo"],
            help=(
                f"Deshacer {global_history['undo_label']}"
                if global_history["undo_label"]
                else "No hay acciones para deshacer"
            ),
            key=f"{session.session_id}:global_undo",
            width="stretch",
        ):
            if _handle_editor_history_event(
                store,
                session,
                {"eventId": uuid.uuid4().hex, "type": "history", "action": "undo"},
            ):
                st.rerun()
    with history_col2:
        if st.button(
            "↷ Rehacer",
            disabled=not global_history["can_redo"],
            help=(
                f"Rehacer {global_history['redo_label']}"
                if global_history["redo_label"]
                else "No hay acciones para rehacer"
            ),
            key=f"{session.session_id}:global_redo",
            width="stretch",
        ):
            if _handle_editor_history_event(
                store,
                session,
                {"eventId": uuid.uuid4().hex, "type": "history", "action": "redo"},
            ):
                st.rerun()
    with history_status:
        if global_history["undo_label"]:
            st.caption(
                f"Historial · última acción: **{global_history['undo_label']}** · "
                f"máximo {_EDITOR_HISTORY_LIMIT} acciones"
            )
        else:
            st.caption("Historial listo · cada pincelada o drag cuenta como una acción")

    sheet_tab, background_tab, studio_tab, align_tab, export_tab = st.tabs(
        (
            "Sheet",
            "Background",
            "Studio",
            "Segmentación + Auto Center",
            "Export",
        )
    )
    history_notice_key = f"{session.session_id}:editor_history_notice"
    if history_notice_key in st.session_state:
        st.toast(str(st.session_state.pop(history_notice_key)))

    with sheet_tab:
        st.subheader("Carga y segmentación")
        if segmentation:
            prefix = session.session_id
            _ensure_segmentation_cut_controls_state(session)
            free_adjust_enabled = bool(
                st.session_state.get(
                    f"{prefix}:segmentation_free_adjust_widget",
                    st.session_state[f"{prefix}:segmentation_free_adjust"],
                )
            )
            guide_overlay = _ensure_segmentation_guide_overlay(
                session,
                background_source,
                segmentation,
                processing_signature=processing_signature,
            )
            with st.container(border=True):
                st.markdown("#### Lienzo de segmentación · preview 1:1 / pixelated")
                st.caption(
                    "Arrastra los cortes directamente en el lienzo; la información queda "
                    "debajo para no reducir el área de trabajo."
                )
                history_controls = _history_controls(session)
                event = pixel_editor(
                    background_source,
                    overlay=guide_overlay,
                    sample=None,
                    tool="drag",
                    mode="segmentation-cut",
                    zoom=int(st.session_state[f"{prefix}:segmentation_cut_zoom"]),
                    cut_positions=st.session_state[f"{prefix}:segmentation_cut_positions"],
                    cut_positions_x=st.session_state.get(
                        f"{prefix}:segmentation_cut_positions_x", ()
                    ),
                    cut_positions_y=st.session_state.get(
                        f"{prefix}:segmentation_cut_positions_y", ()
                    ),
                    allow_cut_drag=free_adjust_enabled,
                    fit_on_load=True,
                    frame_token=(
                        f"{prefix}:segmentation-cut:{background_source.width}x"
                        f"{background_source.height}:{segmentation_config.frame_count}:"
                        f"{segmentation_config.orientation}"
                    ),
                    **history_controls,
                    key=f"{prefix}:segmentation_cut_editor",
                )
                if _handle_editor_history_event(store, session, event):
                    st.rerun()
                history_before = _cut_history_snapshot(prefix)
                changed = _handle_segmentation_cut_event(
                    session,
                    segmentation.resolved_config.frame_count,
                    event,
                    orientation=segmentation_config.orientation,
                    columns=segmentation_config.columns,
                    rows=segmentation_config.rows,
                )
                if changed and event:
                    _record_editor_history(
                        session,
                        scope="cuts",
                        label=_history_label("cuts", event),
                        before=history_before,
                        after=_cut_history_snapshot(prefix),
                    )
                if (
                    changed
                    and event
                    and event.get("type") == "cut"
                    and event.get("action") == "end"
                ):
                    # The component-triggered run was built with the previous cuts.
                    # Stop it before rendering the expensive downstream tabs and
                    # immediately acknowledge the optimistic local position.
                    st.rerun()
        else:
            with st.container(border=True):
                _show_pixel(source, "Sprite sheet original")

        inspection_col, cuts_col = st.columns((1.2, 1), gap="large")
        with inspection_col, st.container(border=True):
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
            with cuts_col, st.container(border=True):
                st.markdown("#### Cortes")
                if st.button(
                    "Cortes automáticos",
                    width="stretch",
                    key=f"{session.session_id}:segmentation_auto_cut",
                ):
                    history_before = _cut_history_snapshot(session.session_id)
                    auto_cuts = _set_auto_segmentation_cuts(
                        session,
                        background_source,
                        segmentation_config,
                        center_config,
                    )
                    _record_editor_history(
                        session,
                        scope="cuts",
                        label="Cortes automáticos",
                        before=history_before,
                        after=_cut_history_snapshot(session.session_id),
                    )
                    st.rerun()
                free_adjust = st.toggle(
                    "Ajuste manual",
                    value=bool(st.session_state[f"{session.session_id}:segmentation_free_adjust"]),
                    key=f"{session.session_id}:segmentation_free_adjust_widget",
                    help="Actívalo para arrastrar las líneas verticales de corte.",
                )
                st.session_state[
                    f"{session.session_id}:segmentation_free_adjust"
                ] = bool(free_adjust)
                st.caption(
                    "El zoom y el encuadre viven directamente en la barra del lienzo."
                )
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
                "Lienzo amplio",
                value=bool(st.session_state.get(f"{prefix}:background_wide_mode", True)),
                key=f"{prefix}:background_wide_mode",
                help="Amplía el área de trabajo sin ocultar la navegación ni los ajustes globales.",
            )
            _set_editor_width_mode(wide_mode)
            tool_key = f"{prefix}:background_tool"
            brush_key = f"{prefix}:background_brush_radius"
            selected_bg = 0
            sampled_rgba = st.session_state[f"{prefix}:background_sampled_color"]
            manual_tolerance = float(
                st.session_state[f"{prefix}:background_wand_tolerance"]
            )
            contiguous = bool(st.session_state[f"{prefix}:background_wand_contiguous"])
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
            floating = st.session_state.get(f"{prefix}:background_floating_selection")
            floating_piece: Image.Image | None = None
            floating_highlight: Image.Image | None = None
            floating_bounds: tuple[int, int, int, int] | None = None
            editor_background = background_source
            if (
                isinstance(floating, dict)
                and int(floating.get("frame_index", -1)) == selected_bg
                and isinstance(floating.get("piece"), Image.Image)
                and isinstance(floating.get("remainder"), Image.Image)
                and isinstance(floating.get("mask"), np.ndarray)
                and floating["mask"].shape == (background_source.height, background_source.width)
            ):
                floating_piece = floating["piece"]
                editor_background = floating["remainder"]
                floating_highlight = _floating_selection_highlight(floating["mask"])
                raw_bounds = floating.get("bounds")
                if isinstance(raw_bounds, tuple) and len(raw_bounds) == 4:
                    floating_bounds = tuple(int(value) for value in raw_bounds)
            elif floating is not None:
                _clear_background_floating_selection(prefix)
            overlay = render_selection_overlay(
                background_source.size,
                (
                    selection_mask
                    if isinstance(selection_mask, np.ndarray) and floating_piece is None
                    else None
                ),
            )
            tool_zoom = int(st.session_state[f"{prefix}:background_zoom"])
            editor_box = st.container(border=True)
            with editor_box:
                st.markdown(
                    """
                    <div class="editor-heading">
                      <div>
                        <span class="editor-kicker">Editor de pixels</span>
                        <h4>Trabaja directamente sobre el sprite sheet</h4>
                      </div>
                      <span class="editor-hint">Atajos y herramientas en la barra del lienzo</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                history_controls = _history_controls(session)
                event = pixel_editor(
                    editor_background,
                    overlay=overlay,
                    sample=st.session_state[f"{prefix}:background_sampled_color"],
                    tool=st.session_state[tool_key],
                    brush_radius=int(st.session_state[brush_key]),
                    wand_tolerance=int(manual_tolerance),
                    wand_contiguous=contiguous,
                    floating_selection=floating_piece,
                    floating_highlight=floating_highlight,
                    floating_selection_x=0,
                    floating_selection_y=0,
                    floating_selection_bounds=floating_bounds,
                    zoom=tool_zoom,
                    frame_token=(
                        f"{prefix}:background:"
                        f"{_stable_ui_signature(st.session_state[f'{prefix}:background_manual_ops'])}"
                    ),
                    **history_controls,
                    key=f"{prefix}:pixel_editor:{selected_bg}",
                )
                if _handle_editor_history_event(store, session, event):
                    st.rerun()
                history_before = _background_history_snapshot(prefix)
                changed = _handle_background_editor_event(
                    session,
                    (background_source,),
                    selected_bg,
                    event,
                    tolerance=manual_tolerance,
                    contiguous=contiguous,
                )
                if changed and event:
                    _record_editor_history(
                        session,
                        scope="background",
                        label=_history_label("background", event),
                        before=history_before,
                        after=_background_history_snapshot(prefix),
                    )
                if changed and event:
                    event_type = str(event.get("type", ""))
                    key_action = str(event.get("key", "")).lower()
                    tool = _normalize_background_tool(
                        event.get("tool", st.session_state[tool_key])
                    )
                    changes_visible_state = (
                        event_type == "edit-batch"
                        or event_type == "crop"
                        or event_type in {"floating-transform", "floating-selection"}
                        or (
                            event_type == "toolbar"
                            and str(event.get("action", "")) == "wand-settings"
                        )
                        or (
                            event_type in {"pointer", "pointerdown", "pointermove"}
                            and tool in {"wand", "eraser", "eyedropper"}
                        )
                        or (
                            event_type == "key"
                            and key_action in {"escape", "delete", "backspace"}
                        )
                    )
                    if changes_visible_state:
                        # This run was built from the pre-edit pixels. Abort before
                        # the selection overlay, sampled swatch, or downstream tabs
                        # render stale state. The next run reuses unaffected caches.
                        st.rerun()
            left_col, right_col = st.columns((1.15, 0.85), gap="large")
            with left_col:
                preview_col1, preview_col2 = st.columns(2, gap="large")
                with preview_col1:
                    _show_pixel(source, "Sprite sheet original")
                with preview_col2:
                    _show_pixel(
                        background_source,
                        "Resultado de trabajo",
                    )
            with right_col, st.container(border=True):
                st.markdown("#### Selección y acciones")
                st.markdown(
                    f"Color muestreado: `{_rgb_to_hex(sampled_rgba[:3])}` · Alpha `{sampled_rgba[3]}`"
                )
                selection_pixels = (
                    int(selection_mask.sum())
                    if isinstance(selection_mask, np.ndarray) and selection_mask.size
                    else 0
                )
                st.write(
                    f"Herramienta activa: `{_background_tool_label(st.session_state[f'{prefix}:background_tool'])}`"
                )
                st.write(f"Pixels seleccionados: `{selection_pixels}`")
                st.caption(
                    f"Varita: tolerancia {int(manual_tolerance)} · "
                    f"{'contigua' if contiguous else 'global'}"
                )
                action_col1, action_col2 = st.columns(2)
                if action_col1.button(
                    "Borrar selección",
                    width="stretch",
                    disabled=selection_pixels == 0 or floating_piece is not None,
                    key=f"{prefix}:bg_delete_selection:{selected_bg}",
                ):
                    history_before = _background_history_snapshot(prefix)
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
                        _record_editor_history(
                            session,
                            scope="background",
                            label="Borrar selección",
                            before=history_before,
                            after=_background_history_snapshot(prefix),
                        )
                        st.rerun()
                if action_col2.button(
                    "Limpiar selección",
                    width="stretch",
                    disabled=selection_pixels == 0 or floating_piece is not None,
                    key=f"{prefix}:bg_clear_selection:{selected_bg}",
                ):
                    history_before = _background_history_snapshot(prefix)
                    selection_masks[selected_bg] = None
                    st.session_state[f"{prefix}:background_selection_masks"] = selection_masks
                    _record_editor_history(
                        session,
                        scope="background",
                        label="Limpiar selección",
                        before=history_before,
                        after=_background_history_snapshot(prefix),
                    )
                    st.rerun()
                operations = st.session_state[f"{prefix}:background_manual_ops"]
                frame_ops = operations.get(selected_bg, [])
                with st.expander(
                    f"Historial del frame · {len(frame_ops)} operaciones",
                    expanded=bool(frame_ops),
                ):
                    if frame_ops:
                        history_rows = [
                            {
                                "paso": str(index + 1),
                                "tipo": {
                                    "erase_similar": "varita",
                                    "erase_brush": "borrador",
                                    "erase_mask": "selección",
                                    "move_mask": "mover selección",
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
                        st.caption("Todavía no hay ediciones manuales en este frame.")
                    clear_col, clear_all_col = st.columns(2)
                    if clear_col.button(
                        "Restablecer frame",
                        width="stretch",
                        key=f"{prefix}:bg_clear_frame:{selected_bg}",
                    ):
                        history_before = _background_history_snapshot(prefix)
                        updated = {
                            int(index): [dict(item) for item in items]
                            for index, items in operations.items()
                            if int(index) != selected_bg and items
                        }
                        st.session_state[f"{prefix}:background_manual_ops"] = updated
                        _clear_background_floating_selection(prefix)
                        _record_editor_history(
                            session,
                            scope="background",
                            label="Restablecer frame",
                            before=history_before,
                            after=_background_history_snapshot(prefix),
                        )
                        st.rerun()
                    if clear_all_col.button(
                        "Restablecer todo",
                        width="stretch",
                        key=f"{prefix}:bg_clear_all",
                    ):
                        history_before = _background_history_snapshot(prefix)
                        st.session_state[f"{prefix}:background_manual_ops"] = {}
                        st.session_state[f"{prefix}:background_selection_masks"] = [
                            None
                        ]
                        _clear_background_floating_selection(prefix)
                        _record_editor_history(
                            session,
                            scope="background",
                            label="Restablecer fondo",
                            before=history_before,
                            after=_background_history_snapshot(prefix),
                        )
                        st.rerun()
            if st.button(
                "Guardar remoción de fondo",
                type="primary",
                disabled=floating_piece is not None,
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

    with studio_tab:
        st.subheader("Sprite Studio · capas y cels")
        if not background_frames:
            st.info("Configura la segmentación para crear el documento de capas.")
        else:
            document: LayeredSpriteDocument | None = None
            layer_images: dict[tuple[str, int], Image.Image] = {}
            if session.layer_document:
                try:
                    document, layer_images = store.load_layer_document(session)
                except (ArtifactIntegrityError, FileNotFoundError, ValueError) as exc:
                    st.warning(f"No se pudo abrir el documento de capas: {exc}")
            if document is None:
                st.markdown(
                    "Crea un documento no destructivo: la capa **Fuente IA** queda bloqueada y "
                    "se puede mover con M; los retoques se pintan sobre capas independientes."
                )
                if st.button(
                    "Crear documento de capas",
                    type="primary",
                    key=f"{session.session_id}:create_layer_document",
                ):
                    store.create_layer_document(session, background_frames)
                    st.rerun()
            else:
                prefix = session.session_id
                active_layer_key = f"{prefix}:layer_editor_active_layer"
                if active_layer_key not in st.session_state or all(
                    layer.layer_id != st.session_state[active_layer_key]
                    for layer in document.layers
                ):
                    st.session_state[active_layer_key] = document.layers[-1].layer_id
                active_layer_id = str(st.session_state[active_layer_key])
                active_layer = document.layer(active_layer_id)
                active_frame_key = f"{prefix}:layer_editor_active_frame"
                if active_frame_key not in st.session_state:
                    st.session_state[active_frame_key] = 0
                active_frame = max(
                    0,
                    min(document.frame_count - 1, int(st.session_state[active_frame_key])),
                )
                st.session_state[active_frame_key] = active_frame
                color_key = f"{prefix}:layer_editor_color"
                if color_key not in st.session_state:
                    st.session_state[color_key] = (255, 255, 255, 255)
                tool_key = f"{prefix}:layer_editor_tool"
                if tool_key not in st.session_state:
                    st.session_state[tool_key] = "pencil"
                scope_key = f"{prefix}:layer_editor_scope"
                scope_for_canvas = str(
                    st.session_state.get(scope_key, "Frame actual")
                )
                if scope_for_canvas == "Toda la animación":
                    selected_frames = tuple(range(document.frame_count))
                elif scope_for_canvas == "Frames elegidos":
                    raw_selected_frames = st.session_state.get(
                        f"{prefix}:layer_editor_selected_frames",
                        (active_frame,),
                    )
                    selected_frames = tuple(
                        sorted(
                            {
                                int(frame_index)
                                for frame_index in raw_selected_frames
                                if 0 <= int(frame_index) < document.frame_count
                            }
                        )
                    ) or (active_frame,)
                else:
                    selected_frames = (active_frame,)
                studio_layers = [
                    {
                        "id": layer.layer_id,
                        "name": layer.name,
                        "visible": layer.visible,
                        "locked": layer.locked,
                        "frames": [
                            document.cel(layer.layer_id, frame_index) is not None
                            for frame_index in range(document.frame_count)
                        ],
                    }
                    for layer in reversed(document.layers)
                ]
                artwork_manifest = _load_stage_manifest(store, session, "artwork") or {}
                artwork_layer_document = artwork_manifest.get("metadata", {}).get(
                    "layer_document", {}
                )
                published_cache_key = (
                    str(artwork_layer_document.get("cache_key", ""))
                    if isinstance(artwork_layer_document, dict)
                    else ""
                )
                current_cache_key = str((session.layer_document or {}).get("cache_key", ""))
                artwork_is_current = bool(
                    current_cache_key and current_cache_key == published_cache_key
                )
                pipeline_state = (
                    "publicada para Auto Center"
                    if artwork_is_current
                    else "pendiente de publicar a Auto Center"
                )
                st.markdown(
                    f"""
                    <div class="studio-toolbar">
                      <div>
                        <div class="studio-toolbar-title">Área de trabajo de sprites</div>
                        <div class="studio-toolbar-copy">La revisión de capas se guarda al editar. Publica cuando quieras que Auto Center use esta revisión.</div>
                      </div>
                      <div class="studio-summary">
                        <span>{document.canvas_width} × {document.canvas_height}px</span>
                        <span>{document.frame_count} frames</span>
                        <span>{len(document.layers)} capas</span>
                        <span>capas r{document.revision}</span>
                        <span>{pipeline_state}</span>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                publish_col, canvas_col = st.columns((1.05, 4.95), gap="large")
                with publish_col:
                    with st.container(border=True):
                        st.markdown("#### Capas")
                        st.caption(
                            "La primera fila se ve arriba. Usa el ojo y el candado "
                            "sin cambiar de capa."
                        )
                        st.markdown(
                            "<div class=\"studio-dock-label\"><span>Ver</span>"
                            "<span>Bloq.</span><span>Nombre · rol</span></div>",
                            unsafe_allow_html=True,
                        )
                        for layer in reversed(document.layers):
                            eye_col, lock_col, name_col = st.columns(
                                (0.48, 0.58, 2.45),
                                gap="small",
                            )
                            if eye_col.button(
                                "👁" if layer.visible else "◌",
                                help=("Ocultar capa" if layer.visible else "Mostrar capa"),
                                key=f"{prefix}:layer_visibility_toggle:{layer.layer_id}",
                            ):
                                _save_layer_document_with_history(
                                    store,
                                    session,
                                    document.with_layer_properties(
                                        layer.layer_id,
                                        visible=not layer.visible,
                                    ),
                                    layer_images,
                                    reason="layer-visibility",
                                    label="Cambiar visibilidad de capa",
                                )
                                st.rerun()
                            if lock_col.button(
                                "🔒" if layer.locked else "🔓",
                                help=("Desbloquear capa" if layer.locked else "Bloquear capa"),
                                key=f"{prefix}:layer_lock_toggle:{layer.layer_id}",
                            ):
                                _save_layer_document_with_history(
                                    store,
                                    session,
                                    document.with_layer_properties(
                                        layer.layer_id,
                                        locked=not layer.locked,
                                    ),
                                    layer_images,
                                    reason="layer-lock",
                                    label="Cambiar bloqueo de capa",
                                )
                                st.rerun()
                            if name_col.button(
                                f"{layer.name} · {layer.role}",
                                width="stretch",
                                type=(
                                    "primary"
                                    if layer.layer_id == active_layer_id
                                    else "secondary"
                                ),
                                key=f"{prefix}:layer_select:{layer.layer_id}",
                            ):
                                st.session_state[active_layer_key] = layer.layer_id
                                st.rerun()

                        st.caption("Orden: arriba se pinta encima de abajo.")
                        add_col, up_col, down_col = st.columns((1.4, 1, 1))
                        if add_col.button("+ Capa", width="stretch", key=f"{prefix}:layer_add"):
                            new_layer = SpriteLayer(
                                layer_id=f"layer-{uuid.uuid4().hex[:8]}",
                                name=f"Capa {len(document.layers) + 1}",
                            )
                            created = document.with_layer(
                                new_layer,
                                above_layer_id=active_layer_id,
                            )
                            _save_layer_document_with_history(
                                store,
                                session,
                                created,
                                layer_images,
                                reason="add-layer",
                                label="Añadir capa",
                            )
                            st.session_state[active_layer_key] = new_layer.layer_id
                            st.rerun()
                        layer_ids = [layer.layer_id for layer in document.layers]
                        layer_index = layer_ids.index(active_layer_id)
                        if up_col.button(
                            "Subir",
                            width="stretch",
                            disabled=layer_index == len(document.layers) - 1,
                            key=f"{prefix}:layer_up",
                        ):
                            _save_layer_document_with_history(
                                store,
                                session,
                                document.reordered(active_layer_id, layer_index + 1),
                                layer_images,
                                reason="reorder-layer",
                                label="Reordenar capa",
                            )
                            st.rerun()
                        if down_col.button(
                            "Bajar",
                            width="stretch",
                            disabled=layer_index == 0,
                            key=f"{prefix}:layer_down",
                        ):
                            _save_layer_document_with_history(
                                store,
                                session,
                                document.reordered(active_layer_id, layer_index - 1),
                                layer_images,
                                reason="reorder-layer",
                                label="Reordenar capa",
                            )
                            st.rerun()

                    with st.expander(f"Propiedades · {active_layer.name}", expanded=True):
                        property_form_key = f"{prefix}:layer_properties:{active_layer_id}"
                        with st.form(property_form_key):
                            layer_name = st.text_input(
                                "Nombre",
                                value=active_layer.name,
                                key=f"{prefix}:layer_name:{active_layer_id}",
                            )
                            role_options = (
                                "source",
                                "body",
                                "retouch",
                                "shadow",
                                "vfx",
                                "reference",
                            )
                            role = st.selectbox(
                                "Rol para Auto Center",
                                role_options,
                                index=role_options.index(active_layer.role),
                                key=f"{prefix}:layer_role:{active_layer_id}",
                            )
                            opacity = float(
                                st.slider(
                                    "Opacidad",
                                    0.0,
                                    1.0,
                                    value=active_layer.opacity,
                                    step=0.05,
                                    key=f"{prefix}:layer_opacity:{active_layer_id}",
                                )
                            )
                            visible = st.checkbox(
                                "Visible",
                                value=active_layer.visible,
                                key=f"{prefix}:layer_visible:{active_layer_id}",
                            )
                            locked = st.checkbox(
                                "Bloquear edición",
                                value=active_layer.locked,
                                key=f"{prefix}:layer_locked:{active_layer_id}",
                            )
                            alpha_locked = st.checkbox(
                                "Bloquear transparencia",
                                value=active_layer.alpha_locked,
                                key=f"{prefix}:layer_alpha_locked:{active_layer_id}",
                                help="El lápiz y los rellenos solo modifican píxeles ya opacos.",
                            )
                            save_properties = st.form_submit_button(
                                "Guardar propiedades",
                                width="stretch",
                            )
                        if save_properties:
                            clean_name = layer_name.strip() or "Capa"
                            _save_layer_document_with_history(
                                store,
                                session,
                                document.with_layer_properties(
                                    active_layer_id,
                                    name=clean_name,
                                    role=role,
                                    opacity=opacity,
                                    visible=visible,
                                    locked=locked,
                                    alpha_locked=alpha_locked,
                                ),
                                layer_images,
                                reason="layer-properties",
                                label="Editar propiedades de capa",
                            )
                            st.rerun()

                    st.markdown("#### Herramientas")
                    color_picker_key = f"{prefix}:layer_editor_color_picker"
                    color_picker_sync_key = f"{prefix}:layer_editor_color_picker_sync"
                    if color_picker_sync_key in st.session_state:
                        st.session_state[color_picker_key] = st.session_state.pop(
                            color_picker_sync_key
                        )
                    color = tuple(st.session_state[color_key])
                    color_hex = st.color_picker(
                        "Color de dibujo",
                        value=_rgb_to_hex(color[:3]),
                        key=color_picker_key,
                    )
                    next_color = _hex_to_rgba(color_hex)
                    if next_color != color:
                        st.session_state[color_key] = next_color
                    brush_radius = int(
                        st.slider(
                            "Tamaño de pincel",
                            min_value=1,
                            max_value=24,
                            value=int(
                                st.session_state.get(
                                    f"{prefix}:layer_editor_brush_radius",
                                    1,
                                )
                            ),
                            key=f"{prefix}:layer_editor_brush_radius",
                        )
                    )
                    symmetry_col1, symmetry_col2 = st.columns(2)
                    symmetry_col1.checkbox(
                        "Simetría horizontal",
                        key=f"{prefix}:layer_symmetry_horizontal",
                    )
                    symmetry_col2.checkbox(
                        "Simetría vertical",
                        key=f"{prefix}:layer_symmetry_vertical",
                    )

                with canvas_col:
                    st.markdown('<div class="studio-canvas-shell">', unsafe_allow_html=True)
                    active_cel = document.cel(active_layer_id, active_frame)
                    if active_cel is None:
                        st.error("La capa activa no tiene un cel para este frame.")
                    else:
                        floating = _floating_selection_for_frame(
                            prefix,
                            layer_id=active_layer_id,
                            frame_index=active_frame,
                        )
                        preview_images = layer_images
                        floating_piece: Image.Image | None = None
                        floating_highlight: Image.Image | None = None
                        floating_bounds: tuple[int, int, int, int] | None = None
                        if floating is not None:
                            image = layer_images.get((active_layer_id, active_frame))
                            piece = floating.get("piece")
                            if (
                                isinstance(image, Image.Image)
                                and isinstance(piece, Image.Image)
                            ):
                                floating_piece = piece
                                mask = floating.get("mask")
                                if isinstance(mask, np.ndarray):
                                    floating_highlight = _floating_selection_highlight(mask)
                                raw_bounds = floating.get("bounds")
                                if isinstance(raw_bounds, tuple) and len(raw_bounds) == 4:
                                    floating_bounds = tuple(int(value) for value in raw_bounds)
                        composite = composite_document_frame(
                            document,
                            preview_images,
                            active_frame,
                        )
                        selection_mask = _layer_selection_mask(
                            prefix,
                            active_layer_id,
                            active_frame,
                        )
                        active_image_for_selection = layer_images.get(
                            (active_layer_id, active_frame)
                        )
                        if (
                            isinstance(selection_mask, np.ndarray)
                            and isinstance(active_image_for_selection, Image.Image)
                            and selection_mask.shape
                            == (
                                active_image_for_selection.height,
                                active_image_for_selection.width,
                            )
                        ):
                            composite = composite.copy()
                            composite.alpha_composite(
                                render_selection_overlay(
                                    active_image_for_selection.size,
                                    selection_mask,
                                ),
                                dest=(active_cel.offset_x, active_cel.offset_y),
                            )
                        move_base: Image.Image | None = None
                        move_overlay: Image.Image | None = None
                        if active_layer.visible:
                            hidden_document = document.with_layer_properties(
                                active_layer_id,
                                visible=False,
                            )
                            move_base = composite_document_frame(
                                hidden_document,
                                preview_images,
                                active_frame,
                            )
                            active_image = layer_images.get((active_layer_id, active_frame))
                            if active_image is not None:
                                move_overlay = active_image.convert("RGBA")
                                if active_layer.opacity < 1:
                                    move_overlay = move_overlay.copy()
                                    move_overlay.putalpha(
                                        move_overlay.getchannel("A").point(
                                            lambda value: round(value * active_layer.opacity)
                                        )
                                    )
                        with st.container(border=True):
                            st.markdown("#### Lienzo")
                            studio_defaults = {
                                f"{prefix}:studio_onion_skin": False,
                                f"{prefix}:studio_onion_opacity": 0.28,
                                f"{prefix}:studio_playback_fps": 8,
                            }
                            for option_key, default_value in studio_defaults.items():
                                if option_key not in st.session_state:
                                    st.session_state[option_key] = default_value
                            duration_key = f"{prefix}:studio_frame_durations"
                            durations = list(st.session_state.get(duration_key, []))
                            if len(durations) != document.frame_count:
                                durations = [
                                    int(durations[index]) if index < len(durations) else 125
                                    for index in range(document.frame_count)
                                ]
                                st.session_state[duration_key] = durations
                            frame_tool_cols = st.columns((1, 1, 1, 1, 1.3), gap="small")
                            if frame_tool_cols[0].button(
                                "Duplicar",
                                key=f"{prefix}:duplicate_frame:{active_frame}",
                                width="stretch",
                            ):
                                updated_document, updated_images = duplicate_document_frame(
                                    document,
                                    layer_images,
                                    active_frame,
                                )
                                _save_layer_document_with_history(
                                    store,
                                    session,
                                    updated_document,
                                    updated_images,
                                    reason="duplicate-frame",
                                    label="Duplicar frame",
                                )
                                st.session_state[active_frame_key] = active_frame + 1
                                durations.insert(active_frame + 1, durations[active_frame])
                                st.session_state[duration_key] = durations
                                st.rerun()
                            if frame_tool_cols[1].button(
                                "Eliminar",
                                disabled=document.frame_count <= 1,
                                key=f"{prefix}:delete_frame:{active_frame}",
                                width="stretch",
                            ):
                                updated_document, updated_images = delete_document_frame(
                                    document,
                                    layer_images,
                                    active_frame,
                                )
                                _save_layer_document_with_history(
                                    store,
                                    session,
                                    updated_document,
                                    updated_images,
                                    reason="delete-frame",
                                    label="Eliminar frame",
                                )
                                st.session_state[active_frame_key] = min(
                                    active_frame,
                                    updated_document.frame_count - 1,
                                )
                                durations.pop(active_frame)
                                st.session_state[duration_key] = durations
                                st.session_state[f"{prefix}:layer_editor_selection_masks"] = {}
                                st.rerun()
                            if frame_tool_cols[2].button(
                                "← Frame",
                                disabled=active_frame <= 0,
                                key=f"{prefix}:frame_left:{active_frame}",
                                width="stretch",
                            ):
                                updated_document, updated_images = move_document_frame(
                                    document,
                                    layer_images,
                                    active_frame,
                                    active_frame - 1,
                                )
                                _save_layer_document_with_history(
                                    store,
                                    session,
                                    updated_document,
                                    updated_images,
                                    reason="move-frame",
                                    label="Reordenar frame",
                                )
                                st.session_state[active_frame_key] = active_frame - 1
                                durations[active_frame - 1], durations[active_frame] = (
                                    durations[active_frame],
                                    durations[active_frame - 1],
                                )
                                st.session_state[duration_key] = durations
                                st.rerun()
                            if frame_tool_cols[3].button(
                                "Frame →",
                                disabled=active_frame >= document.frame_count - 1,
                                key=f"{prefix}:frame_right:{active_frame}",
                                width="stretch",
                            ):
                                updated_document, updated_images = move_document_frame(
                                    document,
                                    layer_images,
                                    active_frame,
                                    active_frame + 1,
                                )
                                _save_layer_document_with_history(
                                    store,
                                    session,
                                    updated_document,
                                    updated_images,
                                    reason="move-frame",
                                    label="Reordenar frame",
                                )
                                st.session_state[active_frame_key] = active_frame + 1
                                durations[active_frame + 1], durations[active_frame] = (
                                    durations[active_frame],
                                    durations[active_frame + 1],
                                )
                                st.session_state[duration_key] = durations
                                st.rerun()
                            onion_enabled = frame_tool_cols[4].toggle(
                                "Onion skin",
                                key=f"{prefix}:studio_onion_skin",
                            )
                            option_cols = st.columns(3, gap="small")
                            if onion_enabled:
                                option_cols[0].slider(
                                    "Opacidad onion skin",
                                    min_value=0.05,
                                    max_value=0.8,
                                    step=0.05,
                                    key=f"{prefix}:studio_onion_opacity",
                                )
                            playback_fps = int(
                                option_cols[1].slider(
                                    "FPS reproducción",
                                    min_value=1,
                                    max_value=30,
                                    key=f"{prefix}:studio_playback_fps",
                                    help=(
                                        "Cambiar FPS aplica la duración equivalente "
                                        "a todos los frames."
                                    ),
                                )
                            )
                            applied_fps_key = f"{prefix}:studio_playback_applied_fps"
                            previous_fps = int(
                                st.session_state.get(applied_fps_key, playback_fps)
                            )
                            if playback_fps != previous_fps:
                                frame_duration_from_fps = max(
                                    16,
                                    round(1000 / playback_fps),
                                )
                                durations = [
                                    frame_duration_from_fps
                                    for _ in range(document.frame_count)
                                ]
                                st.session_state[duration_key] = durations
                                for frame_index in range(document.frame_count):
                                    frame_widget_key = (
                                        f"{prefix}:studio_frame_duration:{frame_index}"
                                    )
                                    if frame_widget_key in st.session_state:
                                        st.session_state[frame_widget_key] = (
                                            frame_duration_from_fps
                                        )
                            st.session_state[applied_fps_key] = playback_fps
                            duration_widget_key = (
                                f"{prefix}:studio_frame_duration:{active_frame}"
                            )
                            if duration_widget_key not in st.session_state:
                                st.session_state[duration_widget_key] = int(
                                    durations[active_frame]
                                )
                            frame_duration = int(
                                option_cols[2].number_input(
                                    "Duración frame (ms)",
                                    min_value=16,
                                    max_value=5000,
                                    step=10,
                                    key=duration_widget_key,
                                )
                            )
                            if frame_duration != durations[active_frame]:
                                durations[active_frame] = frame_duration
                                st.session_state[duration_key] = durations
                            st.caption(
                                f"Frame {active_frame + 1}/{document.frame_count} · "
                                f"capa activa: {active_layer.name} · "
                                "herramienta: "
                                f"{_layer_tool_label(_normalize_layer_tool(st.session_state[tool_key]))}"
                            )
                            if onion_enabled:
                                onion_opacity = float(
                                    st.session_state.get(
                                        f"{prefix}:studio_onion_opacity",
                                        0.28,
                                    )
                                )
                                onion_canvas = Image.new("RGBA", composite.size)
                                if active_frame > 0:
                                    onion_canvas.alpha_composite(
                                        _onion_skin_tint(
                                            composite_document_frame(
                                                document,
                                                preview_images,
                                                active_frame - 1,
                                            ),
                                            (255, 88, 110),
                                            onion_opacity,
                                        )
                                    )
                                if active_frame + 1 < document.frame_count:
                                    onion_canvas.alpha_composite(
                                        _onion_skin_tint(
                                            composite_document_frame(
                                                document,
                                                preview_images,
                                                active_frame + 1,
                                            ),
                                            (72, 190, 255),
                                            onion_opacity,
                                        )
                                    )
                                onion_canvas.alpha_composite(composite)
                                composite = onion_canvas
                            animation_frames = tuple(
                                composite_document_frame(document, preview_images, index)
                                for index in range(document.frame_count)
                            )
                            history_controls = _history_controls(session)
                            event = pixel_editor(
                                composite,
                                overlay=move_overlay,
                                move_base=move_base,
                                sample=tuple(st.session_state[color_key]),
                                paint_color=tuple(st.session_state[color_key]),
                                tool=_normalize_layer_tool(st.session_state[tool_key]),
                                mode="layer-edit",
                                brush_radius=brush_radius,
                                zoom=int(st.session_state.get(f"{prefix}:layer_editor_zoom", 12)),
                                offset_x=active_cel.offset_x,
                                offset_y=active_cel.offset_y,
                                home_offset_x=active_cel.offset_x,
                                home_offset_y=active_cel.offset_y,
                                allow_drag=True,
                                fit_on_load=True,
                                fit_token=(
                                    f"{prefix}:layers:{document.document_id}:"
                                    f"{document.canvas_width}x{document.canvas_height}:"
                                    f"{active_layer_id}:{active_frame}"
                                ),
                                frame_token=(
                                    f"{prefix}:layers:{document.document_id}:{active_layer_id}:"
                                    f"{active_frame}"
                                ),
                                studio_layers=studio_layers,
                                active_layer_id=active_layer_id,
                                active_frame=active_frame,
                                frame_count=document.frame_count,
                                selected_frames=selected_frames,
                                floating_selection=floating_piece,
                                floating_highlight=floating_highlight,
                                floating_selection_x=active_cel.offset_x,
                                floating_selection_y=active_cel.offset_y,
                                floating_selection_bounds=floating_bounds,
                                animation_frames=animation_frames,
                                animation_fps=int(
                                    st.session_state.get(f"{prefix}:studio_playback_fps", 8)
                                ),
                                animation_durations=durations,
                                **history_controls,
                                key=f"{prefix}:layer_pixel_editor",
                            )
                            if _handle_editor_history_event(store, session, event):
                                st.rerun()
                            history_before = _layer_history_snapshot(session)
                            changed = _handle_layer_editor_event(
                                store,
                                session,
                                document,
                                layer_images,
                                event,
                                active_layer_id=active_layer_id,
                                active_frame=active_frame,
                                target_frames=selected_frames,
                                composite=composite,
                            )
                            if changed and event:
                                _record_editor_history(
                                    session,
                                    scope="studio",
                                    label=_history_label("studio", event),
                                    before=history_before,
                                    after=_layer_history_snapshot(session),
                                )
                            # The current run loaded the previous immutable layer
                            # revision. Stop before downstream previews can publish
                            # stale pixels or offsets. The component keeps its local
                            # optimistic frame visible while this confirmation runs.
                            if changed and event and (
                                event.get("type") in {
                                    "studio",
                                    "crop",
                                    "selection",
                                    "selection-command",
                                    "clipboard",
                                    "pixel-action",
                                    "floating-selection",
                                }
                                or event.get("type") in {
                                    "floating-transform",
                                    "edit-batch",
                                    "paint",
                                    "transform",
                                }
                                or (
                                    event.get("type") in {"pointer", "pointerdown"}
                                    and event.get("tool") in {"fill", "replace_color"}
                                )
                            ):
                                st.rerun()
                        notice_key = f"{prefix}:layer_editor_notice"
                        if notice_key in st.session_state:
                            st.info(str(st.session_state.pop(notice_key)))
                    st.markdown("</div>", unsafe_allow_html=True)

                with st.container(border=True):
                    st.markdown("#### Alcance de edición")
                    scope = st.radio(
                        "Aplicar trazos a",
                        ("Frame actual", "Frames elegidos", "Toda la animación"),
                        horizontal=True,
                        key=scope_key,
                    )
                    if scope == "Toda la animación":
                        selected_frames = tuple(range(document.frame_count))
                    elif scope == "Frames elegidos":
                        chosen = st.multiselect(
                            "Frames objetivo",
                            tuple(range(document.frame_count)),
                            default=(active_frame,),
                            key=f"{prefix}:layer_editor_selected_frames",
                        )
                        selected_frames = tuple(int(value) for value in chosen) or (active_frame,)
                    else:
                        selected_frames = (active_frame,)
                    st.caption(
                        "La timeline visual queda debajo del lienzo. Selecciona un frame "
                        "aquí para editarlo; el punto indica que el cel existe en la capa activa."
                    )
                    timeline = st.columns(min(10, document.frame_count))
                    for frame_index in range(document.frame_count):
                        with timeline[frame_index % len(timeline)]:
                            active = frame_index == active_frame
                            cel = document.cel(active_layer_id, frame_index)
                            state = "●" if cel is not None else "○"
                            if st.button(
                                f"{state} F{frame_index + 1}",
                                width="stretch",
                                type="primary" if active else "secondary",
                                key=f"{prefix}:layer_frame:{frame_index}",
                            ):
                                st.session_state[active_frame_key] = frame_index
                                st.rerun()

                st.markdown("#### Canvas y pipeline")
                canvas_tools, publish_tools = st.columns((1, 1.25), gap="large")
                with canvas_tools, st.container(border=True):
                    st.caption(
                        "Amplía todas las celdas con transparencia; nunca escala "
                        "pixels individuales."
                    )
                    padding = int(
                        st.number_input(
                            "Padding transparente",
                            min_value=0,
                            max_value=512,
                            value=0,
                            key=f"{prefix}:layer_editor_padding",
                        )
                    )
                    if st.button(
                        "Ajustar canvas al contenido",
                        width="stretch",
                        key=f"{prefix}:layer_expand_canvas",
                    ):
                        expanded = document.expanded_to_content(layer_images, padding=padding)
                        previous = document.cel(document.layers[0].layer_id, 0)
                        moved = expanded.cel(document.layers[0].layer_id, 0)
                        shift_x = moved.offset_x - previous.offset_x if moved and previous else 0
                        shift_y = moved.offset_y - previous.offset_y if moved and previous else 0
                        old_center = session.auto_center_config
                        session.auto_center_config = AutoCenterConfig(
                            method=old_center.method,
                            canvas_width=expanded.canvas_width,
                            canvas_height=expanded.canvas_height,
                            canonical_anchor=(
                                old_center.canonical_anchor[0] + shift_x,
                                old_center.canonical_anchor[1] + shift_y,
                            ),
                            confidence_threshold=old_center.confidence_threshold,
                            ignore_outliers=old_center.ignore_outliers,
                            anchor_strategy=old_center.anchor_strategy,
                        )
                        _save_layer_document_with_history(
                            store,
                            session,
                            expanded,
                            layer_images,
                            reason="expand-canvas",
                            label="Expandir canvas",
                        )
                        st.rerun()
                with publish_tools, st.container(border=True):
                    st.markdown("**Publicación para Auto Center**")
                    if artwork_is_current:
                        st.success("Auto Center ya usa esta revisión de capas.")
                    else:
                        st.warning(
                            "Auto Center sigue usando la última versión publicada. "
                            "Publica esta revisión cuando el retoque esté listo."
                        )
                    if st.button(
                        "Publicar capas para Auto Center",
                        type="primary",
                        width="stretch",
                        key=f"{prefix}:publish_layer_document",
                    ):
                        store.publish_layer_document(
                            session,
                            document,
                            layer_images,
                            reason="publish-to-pipeline",
                        )
                        st.success(
                            "Capas publicadas: Auto Center usará esta revisión "
                            "en el siguiente cálculo."
                        )
                        st.rerun()

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
            review_count = sum(item.manual_review for item in centered.adjustments)
            if review_count:
                st.warning(
                    f"Hay {review_count} anchor(s) de baja confianza. "
                    "Revísalos y apruébalos antes de exportar."
                )
            selected = st.selectbox(
                "Frame",
                tuple(range(len(preview_crop.frames))),
                key=f"{prefix}:selected_frame",
            )
            sheet_columns = _export_preview_columns(
                segmentation_config.orientation,
                len(preview_crop.frames),
                segmentation_config.columns,
            )
            selected_frame = preview_crop.frames[selected]
            selected_home = _alignment_frame_position(preview_crop.frames, selected, sheet_columns)
            selected_offset = st.session_state[f"{prefix}:offsets"][selected]
            selected_position = selected_home
            _ensure_center_guide_state(
                session,
                default_ground_line_y=max(0, selected_frame.height - 1),
                max_ground_line_y=max(0, selected_frame.height - 1),
            )
            preview_adjustment = preview_source.adjustments[selected]
            crop_origin_x, crop_origin_y = preview_crop.bbox[:2]
            current_anchor_x = (
                selected_home[0]
                + preview_adjustment.final_anchor[0]
                - crop_origin_x
            )
            current_anchor_y = (
                selected_home[1]
                + preview_adjustment.final_anchor[1]
                - crop_origin_y
            )
            target_anchor_x = (
                selected_home[0]
                + preview_adjustment.final_anchor[0]
                - preview_adjustment.manual_offset_x
                - crop_origin_x
            )
            target_anchor_y = (
                selected_home[1]
                + preview_adjustment.final_anchor[1]
                - preview_adjustment.manual_offset_y
                - crop_origin_y
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
            history_controls = _history_controls(session)
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
                    f"{selected_frame.width}x{selected_frame.height}:"
                    f"offset:{selected_offset[0]}:{selected_offset[1]}"
                ),
                **history_controls,
                key=f"{prefix}:center_pixel_editor",
            )
            if _handle_editor_history_event(store, session, event):
                st.rerun()
            history_before = _center_history_snapshot(prefix)
            changed = _handle_center_editor_event(
                session,
                len(centered.frames),
                selected,
                event,
                home_offset=selected_home,
                base_manual_offset=selected_offset,
            )
            if changed and event:
                _record_editor_history(
                    session,
                    scope="center",
                    label=_history_label("center", event),
                    before=history_before,
                    after=_center_history_snapshot(prefix),
                )
            if changed and event and (
                event.get("type") == "transform"
                or (
                    event.get("type") == "toolbar"
                    and event.get("action") in {"autocenter", "reset-transform"}
                )
            ):
                # Auto Center was computed before the component event. Confirm the
                # optimistic transform immediately so every preview and numeric
                # control receives the same offset without requiring a second drag.
                st.rerun()
            if st.button(
                "Fijar frame",
                type="primary",
                key=f"{session.session_id}:save_center",
            ):
                _ensure_adjustment_state(session, len(working_frames))
                final_result = auto_center_frames(
                    working_frames,
                    center_config,
                    manual_offsets=st.session_state[f"{prefix}:offsets"],
                    locked=st.session_state[f"{prefix}:locks"],
                    notes=st.session_state[f"{prefix}:notes"],
                    overflow_strategy="clamp",
                    analysis=center_analysis,
                    target_anchor=center_config.canonical_anchor,
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
                st.markdown("#### Ajuste fino")
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
                lock_key = f"{prefix}:locked:{selected}"
                if lock_key not in st.session_state:
                    st.session_state[lock_key] = bool(locks[selected])
                st.checkbox(
                    "Anchor revisado y aprobado",
                    key=lock_key,
                    on_change=_sync_center_lock,
                    args=(prefix, selected),
                    help=(
                        "Aprueba manualmente este anchor después de comprobar torso, "
                        "suelo y estabilidad con los frames vecinos."
                    ),
                )
                st.caption("Arrastra en el lienzo para el ajuste rápido; usa estos valores para precisión de 1 px.")
                with st.expander("Guías avanzadas", expanded=False):
                    guides_enabled = bool(st.session_state[f"{prefix}:center_guides"])
                    st.checkbox(
                        "Mostrar guías",
                        key=f"{prefix}:center_guides_widget",
                        help="También disponible con el icono de capas en el lienzo.",
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
                        history_before = _center_history_snapshot(prefix)
                        offsets = list(offsets)
                        offsets[selected] = widget_offset
                        st.session_state[f"{prefix}:offsets"] = offsets
                        _record_editor_history(
                            session,
                            scope="center",
                            label="Ajustar offset",
                            before=history_before,
                            after=_center_history_snapshot(prefix),
                        )
                        st.rerun()
                reset_col, copy_col = st.columns(2)
                if reset_col.button(
                    "Reset frame",
                    width="stretch",
                    key=f"{prefix}:reset:{selected}",
                ):
                    history_before = _center_history_snapshot(prefix)
                    values = list(st.session_state[f"{prefix}:offsets"])
                    values[selected] = (0, 0)
                    st.session_state[f"{prefix}:offsets"] = values
                    for key in (
                        x_widget_key,
                        y_widget_key,
                    ):
                        st.session_state.pop(key, None)
                    _record_editor_history(
                        session,
                        scope="center",
                        label="Restablecer frame",
                        before=history_before,
                        after=_center_history_snapshot(prefix),
                    )
                    st.rerun()
                if copy_col.button(
                    "Copiar a todos",
                    width="stretch",
                    key=f"{prefix}:copy:{selected}",
                ):
                    history_before = _center_history_snapshot(prefix)
                    value = tuple(st.session_state[f"{prefix}:offsets"][selected])
                    st.session_state[f"{prefix}:offsets"] = [
                        value for _ in centered.frames
                    ]
                    for index in range(len(centered.frames)):
                        st.session_state.pop(f"{prefix}:offset_x_widget:{index}", None)
                        st.session_state.pop(f"{prefix}:offset_y_widget:{index}", None)
                    _record_editor_history(
                        session,
                        scope="center",
                        label="Copiar offset a todos",
                        before=history_before,
                        after=_center_history_snapshot(prefix),
                    )
                    st.rerun()
            if st.button(
                "Guardar overrides",
                type="primary",
                key=f"{prefix}:save_overrides",
            ):
                _ensure_adjustment_state(session, len(working_frames))
                requested_offsets = list(st.session_state[f"{prefix}:offsets"])
                final_result = auto_center_frames(
                    working_frames,
                    center_config,
                    manual_offsets=requested_offsets,
                    locked=st.session_state[f"{prefix}:locks"],
                    notes=st.session_state[f"{prefix}:notes"],
                    overflow_strategy="clamp",
                    analysis=center_analysis,
                    target_anchor=center_config.canonical_anchor,
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
            alignment_manifest = _load_stage_manifest(store, session, "alignment")
            export_ready, export_block_reason = _alignment_export_readiness(
                alignment_manifest,
                segmentation_config=segmentation_config,
                background_config=background_config,
                center_config=center_config,
                manual_offsets=st.session_state[f"{prefix}:offsets"],
                locks=st.session_state[f"{prefix}:locks"],
                frame_count=len(centered.frames),
            )
            try:
                persisted_alignment_frames = _load_stage_frames(
                    store,
                    session,
                    "alignment",
                )
            except ArtifactIntegrityError as exc:
                st.warning(f"Alignment guardado inválido: {exc}")
                persisted_alignment_frames = ()
                export_ready = False
                export_block_reason = "La integridad de la alineación guardada falló."
            if export_ready and len(persisted_alignment_frames) == len(centered.frames):
                export_frames_source = persisted_alignment_frames
            elif export_ready:
                export_ready = False
                export_block_reason = "La alineación guardada no coincide con los frames actuales."
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
                st.session_state[f"{session.session_id}:export_columns"] = min(
                    max(1, segmentation_config.columns),
                    len(centered.frames),
                )
            inherit_layout_key = f"{prefix}:export_inherit_segmentation_layout"
            if inherit_layout_key not in st.session_state:
                st.session_state[inherit_layout_key] = True
            export_col, preview_col = st.columns((1, 1.45), gap="large")
            with export_col, st.container(border=True):
                inherit_segmentation_layout = st.checkbox(
                    "Mantener layout de segmentación",
                    key=inherit_layout_key,
                    help=(
                        "Export y preview conservan la orientación, filas y columnas "
                        "elegidas al cortar la sprite sheet."
                    ),
                )
                if inherit_segmentation_layout:
                    layout = segmentation_config.orientation
                    export_columns = (
                        min(
                            max(1, segmentation_config.columns),
                            len(centered.frames),
                        )
                        if layout == "grid"
                        else None
                    )
                    if layout == "grid":
                        st.caption(
                            "Layout heredado: "
                            f"grid {segmentation_config.columns} × {segmentation_config.rows} "
                            "(columnas × filas)"
                        )
                    else:
                        st.caption(f"Layout heredado: {layout}")
                else:
                    layout = st.selectbox(
                        "Layout de salida",
                        ("horizontal", "vertical", "grid"),
                        key=f"{session.session_id}:export_layout",
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
                    st.warning(
                        f"{review_count} frame(s) siguen marcados como revisión. "
                        "Puedes exportar bajo tu criterio; el manifest conservará esta alerta."
                    )
                if not export_ready:
                    st.warning(
                        f"Validación de emergencia: {export_block_reason} "
                        "La exportación está permitida y quedará marcada como manual_review."
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
                    (
                        "Exportar PNG por frame"
                        if include_frames and export_ready
                        else "Exportar sprite-sheet PNG"
                        if export_ready
                        else "Exportar con advertencias"
                    ),
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
                        export_sheet_png=not include_frames,
                        export_contact_sheet=include_contact,
                        export_gif=include_gif,
                        fps=fps,
                        allow_manual_review=True,
                    )
                    st.session_state[f"{session.session_id}:last_export"] = manifest
                    st.success("Exportación terminada y manifest guardado.")
                manifest = st.session_state.get(
                    f"{session.session_id}:last_export",
                    session.export_manifest,
                )
                if manifest:
                    output_png = manifest.get("output_png")
                    png_path = workspace / output_png if isinstance(output_png, str) else None
                    if png_path is not None and png_path.is_file():
                        st.download_button(
                            "Descargar sprite-sheet PNG",
                            data=png_path.read_bytes(),
                            file_name=png_path.name,
                            mime="image/png",
                            width="stretch",
                        )
                    frame_paths = [
                        workspace / value
                        for value in manifest.get("output_frames", [])
                        if isinstance(value, str) and (workspace / value).is_file()
                    ]
                    if frame_paths:
                        archive = io.BytesIO()
                        with zipfile.ZipFile(
                            archive,
                            mode="w",
                            compression=zipfile.ZIP_DEFLATED,
                        ) as bundle:
                            for frame_path in frame_paths:
                                bundle.write(frame_path, arcname=frame_path.name)
                        st.download_button(
                            f"Descargar {len(frame_paths)} frames PNG (.zip)",
                            data=archive.getvalue(),
                            file_name="sprite-frames.zip",
                            mime="application/zip",
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
                preview_columns = _export_preview_columns(
                    layout,
                    len(preview_crop.frames),
                    export_columns,
                )
                _render_export_preview_fragment(
                    prefix=prefix,
                    frames=preview_crop.frames,
                    adjustments=centered.adjustments,
                    columns=preview_columns,
                    origin_offset=(preview_crop.bbox[0], preview_crop.bbox[1]),
                )
        else:
            st.info("No hay frames centrados para exportar.")

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Workspace: {workspace}")
    st.sidebar.caption("Procesamiento local · sin APIs externas")


if __name__ == "__main__":
    main()
