from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from sprite_builder.sheets import (
    AutoCenterConfig,
    BackgroundRemovalConfig,
    ExportCropConfig,
    FrameAdjustment,
    SegmentationConfig,
    SheetSessionStore,
    apply_manual_background_edits,
    apply_background_removal,
    auto_center_frames,
    clear_selection,
    combine_selection_masks,
    decode_mask,
    encode_mask,
    erase_similar_pixels,
    erase_with_brush,
    render_selection_overlay,
    select_similar_pixels,
    segment_sheet,
    render_frame_overlay,
    trim_transparent_frames,
)
from sprite_builder.ui.app import _clamp_manual_offsets_to_canvas
from sprite_builder.ui.app import _handle_center_editor_event


def _sheet(count: int = 4, cell: tuple[int, int] = (16, 20)) -> Image.Image:
    image = Image.new("RGB", (cell[0] * count, cell[1]), (0, 255, 0))
    draw = ImageDraw.Draw(image)
    for index in range(count):
        x = index * cell[0]
        draw.rectangle((x + 5, 4, x + 10, 15), fill=(180, 90, 30))
        draw.rectangle((x + 6, 7, x + 9, 11), fill=(230, 160, 45))
    return image


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_horizontal_segmentation_and_empty_detection() -> None:
    result = segment_sheet(
        _sheet(),
        SegmentationConfig(frame_count=4, orientation="horizontal"),
        background_rgb=(0, 255, 0),
    )
    assert result.resolved_config.cell_width == 16
    assert result.resolved_config.cell_height == 20
    assert result.regions[2] == (32, 0, 48, 20)
    assert not result.empty_frames


def test_grid_segmentation_honours_offsets_and_spacing() -> None:
    image = Image.new("RGBA", (25, 19), (0, 0, 0, 0))
    result = segment_sheet(
        image,
        SegmentationConfig(
            frame_count=4,
            orientation="grid",
            rows=2,
            columns=2,
            cell_width=10,
            cell_height=7,
            offset_x=2,
            offset_y=3,
            spacing_x=1,
            spacing_y=2,
        ),
    )
    assert result.regions == (
        (2, 3, 12, 10),
        (13, 3, 23, 10),
        (2, 12, 12, 19),
        (13, 12, 23, 19),
    )
    assert result.empty_frames == (0, 1, 2, 3)


def test_rgb_background_removal_preserves_hard_pixels() -> None:
    frames = segment_sheet(
        _sheet(1),
        SegmentationConfig(frame_count=1),
    ).frames
    output = apply_background_removal(
        frames,
        BackgroundRemovalConfig(
            color=(0, 255, 0),
            tolerance=8,
            preserve_outline=True,
        ),
    )[0]
    array = np.asarray(output)
    assert array[0, 0, 3] == 0
    assert set(np.unique(array[:, :, 3])).issubset({0, 255})
    assert tuple(array[8, 7, :3]) == (230, 160, 45)


def test_manual_color_erase_can_be_contiguous_or_global() -> None:
    frame = Image.new("RGBA", (8, 6), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, 1, 5), fill=(0, 255, 0, 255))
    draw.rectangle((6, 0, 7, 5), fill=(0, 255, 0, 255))
    contiguous = erase_similar_pixels(
        frame,
        seed_point=(0, 0),
        tolerance=0,
        contiguous=True,
    )
    global_erase = erase_similar_pixels(
        frame,
        seed_point=(0, 0),
        tolerance=0,
        contiguous=False,
    )
    contiguous_array = np.asarray(contiguous)
    global_array = np.asarray(global_erase)
    assert contiguous_array[2, 0, 3] == 0
    assert contiguous_array[2, 7, 3] == 255
    assert global_array[2, 0, 3] == 0
    assert global_array[2, 7, 3] == 0


def test_manual_brush_erase_clears_local_circle() -> None:
    frame = Image.new("RGBA", (9, 9), (120, 60, 10, 255))
    erased = erase_with_brush(frame, center=(4, 4), radius=2)
    array = np.asarray(erased)
    assert array[4, 4, 3] == 0
    assert array[0, 0, 3] == 255


def test_manual_brush_erase_replays_drag_path_continuously() -> None:
    frame = Image.new("RGBA", (9, 9), (120, 60, 10, 255))
    erased = erase_with_brush(
        frame,
        center=(1, 4),
        radius=1,
        path=((1, 4), (7, 4)),
    )
    array = np.asarray(erased)
    assert array[4, 1, 3] == 0
    assert array[4, 4, 3] == 0
    assert array[4, 7, 3] == 0
    assert array[1, 1, 3] == 255


def test_manual_background_edits_replay_in_order() -> None:
    frame = Image.new("RGBA", (8, 8), (0, 255, 0, 255))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((2, 2, 5, 5), fill=(200, 80, 30, 255))
    edited = apply_manual_background_edits(
        (frame,),
        {
            0: [
                {"kind": "erase_similar", "point": [0, 0], "tolerance": 0, "contiguous": False},
                {
                    "kind": "erase_brush",
                    "point": [2, 3],
                    "radius": 1,
                    "path": [[2, 3], [4, 3]],
                },
            ]
        },
    )[0]
    array = np.asarray(edited)
    assert array[0, 0, 3] == 0
    assert array[3, 3, 3] == 0
    assert array[5, 5, 3] == 255


def test_magic_wand_selection_mask_and_mask_encoding_round_trip() -> None:
    frame = Image.new("RGBA", (8, 6), (0, 255, 0, 255))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((2, 1, 5, 4), fill=(10, 10, 200, 255))
    mask = select_similar_pixels(
        frame,
        seed_point=(0, 0),
        tolerance=0,
        contiguous=False,
    )
    payload = encode_mask(mask)
    decoded = decode_mask(payload, frame.size)
    assert np.array_equal(mask, decoded)
    cleared = np.asarray(clear_selection(frame, decoded))
    assert cleared[0, 0, 3] == 0
    assert cleared[2, 3, 3] == 255


def test_selection_mask_encoding_handles_sparse_spans() -> None:
    mask = np.zeros((6, 7), dtype=bool)
    mask[1, 1:3] = True
    mask[1, 5:7] = True
    mask[4, 2:6] = True
    payload = encode_mask(mask)
    assert payload["bbox"] == [1, 1, 7, 5]
    decoded = decode_mask(payload, (7, 6))
    assert np.array_equal(mask, decoded)


def test_selection_mask_combine_and_overlay() -> None:
    base = np.zeros((5, 5), dtype=bool)
    a = np.zeros((5, 5), dtype=bool)
    b = np.zeros((5, 5), dtype=bool)
    a[1:3, 1:3] = True
    b[2:5, 2:5] = True
    added = combine_selection_masks(base, a, mode="add")
    merged = combine_selection_masks(added, b, mode="add")
    subtracted = combine_selection_masks(merged, a, mode="subtract")
    overlay = np.asarray(render_selection_overlay((5, 5), subtracted))
    assert merged.sum() > subtracted.sum()
    assert overlay[:, :, 3].max() > 0


def test_weapon_does_not_drag_body_anchor() -> None:
    frames: list[Image.Image] = []
    for weapon in (False, True):
        image = Image.new("RGBA", (64, 48), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 8, 35, 34), fill=(180, 90, 30, 255))
        draw.rectangle((23, 14, 32, 27), fill=(230, 160, 45, 255))
        if weapon:
            draw.rectangle((35, 19, 62, 20), fill=(100, 70, 20, 255))
        frames.append(image)
    result = auto_center_frames(
        frames,
        AutoCenterConfig(
            canvas_width=80,
            canvas_height=64,
            canonical_anchor=(36, 28),
            confidence_threshold=0,
        ),
    )
    first, second = result.adjustments
    assert abs(first.auto_anchor[0] - second.auto_anchor[0]) <= 3
    assert all(frame.size == (80, 64) for frame in result.frames)


def test_auto_center_can_clamp_overflowing_frames_without_crashing() -> None:
    frame = Image.new("RGBA", (60, 50), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((12, 8, 30, 35), fill=(180, 90, 30, 255))
    draw.rectangle((30, 18, 58, 20), fill=(100, 70, 20, 255))
    result = auto_center_frames(
        [frame],
        AutoCenterConfig(
            method="body",
            canvas_width=60,
            canvas_height=50,
            canonical_anchor=(30, 26),
            confidence_threshold=0,
        ),
        manual_offsets=[(8, 0)],
        overflow_strategy="clamp",
    )
    assert result.frames[0].size == (60, 50)
    assert result.adjustments[0].applied_translation[0] <= 2


def test_manual_offset_clamp_respects_canvas_bounds() -> None:
    adjustment = FrameAdjustment(
        frame_index=0,
        auto_anchor=(20, 20),
        applied_translation=(15, 15),
        body_bbox=(5, 4, 31, 30),
    )
    clamped, changed = _clamp_manual_offsets_to_canvas(
        [adjustment],
        [(999, -999)],
        (40, 40),
    )
    assert changed == [0]
    assert clamped == [(-6, -19)]


def test_center_drag_event_clears_widget_state_and_persists_offset() -> None:
    from streamlit import session_state as ss

    ss.clear()
    prefix = "sheet-test"
    ss[f"{prefix}:offsets"] = [(0, 0)]
    ss[f"{prefix}:center_last_event"] = None
    ss[f"{prefix}:offset_x_widget:0"] = 99
    ss[f"{prefix}:offset_y_widget:0"] = -99
    changed = _handle_center_editor_event(
        type("Session", (), {"session_id": prefix})(),
        1,
        0,
        {
            "eventId": "drag-1",
            "type": "transform",
            "offsetX": 12,
            "offsetY": -7,
            "zoom": 9,
        },
        home_offset=(10, -3),
    )
    assert changed is True
    assert ss[f"{prefix}:offsets"] == [(2, -4)]
    assert ss[f"{prefix}:offset_x_widget:0"] == 2
    assert ss[f"{prefix}:offset_y_widget:0"] == -4
    assert ss[f"{prefix}:center_widget_sync"] is True
    assert ss[f"{prefix}:center_zoom:0"] == 9


def test_center_zoom_event_persists_per_frame_and_clamps() -> None:
    from streamlit import session_state as ss

    ss.clear()
    prefix = "sheet-zoom-test"
    ss[f"{prefix}:offsets"] = [(0, 0), (0, 0)]
    ss[f"{prefix}:center_last_event"] = None

    changed = _handle_center_editor_event(
        type("Session", (), {"session_id": prefix})(),
        2,
        1,
        {
            "eventId": "zoom-1",
            "type": "toolbar",
            "action": "zoom",
            "zoom": 99,
        },
    )

    assert changed is True
    assert ss[f"{prefix}:center_zoom:1"] == 40
    assert f"{prefix}:center_zoom:0" not in ss


def test_export_crop_trims_shared_transparency_and_offsets_guides() -> None:
    frames: list[Image.Image] = []
    for x_shift in (0, 2):
        frame = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)
        draw.rectangle((3 + x_shift, 4, 5 + x_shift, 6), fill=(180, 90, 30, 255))
        frames.append(frame)
    crop = trim_transparent_frames(
        frames,
        ExportCropConfig(enabled=True, padding=1, alpha_threshold=8),
    )
    assert crop.source_size == (12, 12)
    assert crop.bbox == (2, 3, 9, 8)
    assert all(frame.size == (7, 5) for frame in crop.frames)

    adjustment = FrameAdjustment(
        frame_index=0,
        auto_anchor=(4, 5),
        applied_translation=(0, 0),
        body_bbox=(3, 4, 6, 7),
    )
    cropped_overlay = np.asarray(
        render_frame_overlay(
            crop.frames[0],
            adjustment,
            scale=1,
            origin_offset=(crop.bbox[0], crop.bbox[1]),
        )
    )
    assert tuple(cropped_overlay[2, 2, :3]) == (255, 76, 160)


def test_session_round_trip_stage_and_export(tmp_path: Path) -> None:
    store = SheetSessionStore(tmp_path)
    session = store.create(_png_bytes(_sheet(2)), source_name="walk.png")
    loaded = store.load(session.session_id)
    segmented = segment_sheet(
        store.source_path(loaded),
        SegmentationConfig(frame_count=2),
        background_rgb=(0, 255, 0),
    )
    transparent = apply_background_removal(
        segmented.frames,
        BackgroundRemovalConfig(color=(0, 255, 0), tolerance=8),
    )
    store.commit_stage(
        loaded,
        "background",
        transparent,
        config={"background": {"color": [0, 255, 0], "tolerance": 8}},
        metadata={
            "manual_edit_operations": {
                "0": [{"kind": "erase_brush", "point": [1, 1], "radius": 1}]
            }
        },
    )
    centered = auto_center_frames(
        transparent,
        AutoCenterConfig(
            canvas_width=20,
            canvas_height=24,
            canonical_anchor=(10, 12),
            confidence_threshold=0,
        ),
    )
    store.commit_stage(
        loaded,
        "alignment",
        centered.frames,
        config={"test": True},
        metrics=centered.jitter_report,
    )
    store.save_adjustments(loaded, centered.adjustments)
    manifest = store.export(loaded, centered.frames, layout="vertical")
    assert (tmp_path / manifest["output_png"]).is_file()
    assert Image.open(tmp_path / manifest["output_png"]).size == (20, 48)
    reopened = store.load(session.session_id)
    assert reopened.export_manifest
    assert reopened.export_manifest["sha256"] == manifest["sha256"]
    exported_path = tmp_path / manifest["output_png"]
    background_manifest_path = tmp_path / reopened.stages["background"]["manifest"]
    background_manifest_text = background_manifest_path.read_text(encoding="utf-8")
    store.commit_stage(
        reopened,
        "segmentation",
        segmented.frames,
        config={"frame_count": 2, "revision": 2},
    )
    invalidated = store.load(session.session_id)
    assert invalidated.export_manifest is None
    assert "alignment" not in invalidated.stages
    assert exported_path.is_file()  # Immutable lineage remains on disk.
    assert background_manifest_path.is_file()
    assert "manual_edit_operations" in background_manifest_text


def test_background_stage_invalidates_segmentation_downstream(tmp_path: Path) -> None:
    store = SheetSessionStore(tmp_path)
    session = store.create(_png_bytes(_sheet(2)), source_name="walk.png")
    loaded = store.load(session.session_id)
    segmented = segment_sheet(
        store.source_path(loaded),
        SegmentationConfig(frame_count=2),
        background_rgb=(0, 255, 0),
    )
    store.commit_stage(
        loaded,
        "background",
        segmented.frames,
        config={"background": {"color": [0, 255, 0], "tolerance": 8}},
    )
    store.commit_stage(
        loaded,
        "segmentation",
        segmented.frames,
        config={"frame_count": 2},
    )
    store.commit_stage(
        loaded,
        "background",
        segmented.frames,
        config={"background": {"color": [0, 255, 0], "tolerance": 12}},
    )
    invalidated = store.load(session.session_id)
    assert "segmentation" not in invalidated.stages
    assert invalidated.export_manifest is None
