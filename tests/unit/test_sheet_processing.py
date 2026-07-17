from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from sprite_builder.sheets import (
    AutoCenterConfig,
    BackgroundRemovalConfig,
    auto_cut_positions,
    analyze_center_frames,
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
    pad_frames_to_common_canvas,
    render_contact_sheet,
    render_frame_overlay,
    render_selection_overlay,
    select_similar_pixels,
    segment_sheet,
    render_segmentation_region_guides,
    trim_transparent_frames,
)
from sprite_builder.ui.app import _clamp_manual_offsets_to_canvas
from sprite_builder.ui.app import _normalized_segmentation_cut_positions
from sprite_builder.ui.app import _normalized_grid_cut_positions
from sprite_builder.ui.app import _effective_segmentation_frame_count
from sprite_builder.ui.app import _safe_trim_transparent_frames
from sprite_builder.ui.app import _handle_center_editor_event
from sprite_builder.ui.app import _handle_background_editor_event
from sprite_builder.ui.app import _export_preview_columns
from sprite_builder.ui.app import _alignment_export_readiness
from sprite_builder.ui.app import _center_history_snapshot
from sprite_builder.ui.app import _handle_editor_history_event
from sprite_builder.ui.app import _pack_selection_masks
from sprite_builder.ui.app import _record_editor_history
from sprite_builder.ui.app import _unpack_selection_masks


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


def test_export_preview_columns_match_the_output_layout() -> None:
    assert _export_preview_columns("horizontal", 16, None) == 16
    assert _export_preview_columns("vertical", 16, None) == 1
    assert _export_preview_columns("grid", 16, 4) == 4
    assert _export_preview_columns("grid", 3, 8) == 3


def test_grid_ui_uses_every_visible_cell_as_a_frame() -> None:
    assert _effective_segmentation_frame_count("grid", 16, 5, 4) == 20
    assert _effective_segmentation_frame_count("grid", 1, 4, 5) == 20
    assert _effective_segmentation_frame_count("horizontal", 16, 5, 4) == 16

    result = segment_sheet(
        Image.new("RGBA", (40, 50), (255, 0, 255, 255)),
        SegmentationConfig(
            frame_count=_effective_segmentation_frame_count("grid", 16, 5, 4),
            orientation="grid",
            rows=5,
            columns=4,
        ),
    )
    assert len(result.frames) == 20
    assert result.regions[-1] == (30, 40, 40, 50)


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


def test_horizontal_segmentation_honours_manual_cut_positions() -> None:
    result = segment_sheet(
        _sheet(),
        SegmentationConfig(
            frame_count=4,
            orientation="horizontal",
            manual_cut_positions=(14, 30, 47),
        ),
        background_rgb=(0, 255, 0),
    )
    assert result.regions == (
        (0, 0, 14, 20),
        (14, 0, 30, 20),
        (30, 0, 47, 20),
        (47, 0, 64, 20),
    )


def test_segmentation_guides_are_independent_from_export_guides() -> None:
    guide = np.asarray(
        render_segmentation_region_guides(
            (32, 20),
            ((2, 2, 14, 16), (14, 2, 30, 16)),
        )
    )
    assert tuple(guide[2, 2, :3]) == (76, 224, 255)
    assert tuple(guide[14, 5, :3]) == (8, 10, 18)
    assert guide[0, 0, 3] == 0


def test_mismatched_manual_cut_positions_fall_back_to_auto() -> None:
    config = SegmentationConfig(
        frame_count=4,
        orientation="horizontal",
        manual_cut_positions=(12, 24),
    )
    positions = _normalized_segmentation_cut_positions(_sheet().size, config, config.manual_cut_positions)
    assert positions == (16, 32, 48)


def test_grid_cut_normalization_ignores_linear_orientation() -> None:
    positions = _normalized_grid_cut_positions(
        _sheet().size,
        SegmentationConfig(frame_count=4, orientation="horizontal"),
        (),
        (),
    )
    assert positions == ((), ())


def test_grid_cut_normalization_ignores_incomplete_grid_capacity() -> None:
    positions = _normalized_grid_cut_positions(
        _sheet().size,
        SegmentationConfig(frame_count=4, orientation="grid", rows=1, columns=1),
        (),
        (),
    )
    assert positions == ((), ())


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


def test_grid_segmentation_honours_manual_cut_positions_on_both_axes() -> None:
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
            manual_cut_positions_x=(11,),
            manual_cut_positions_y=(8,),
        ),
    )
    assert result.regions == (
        (0, 0, 11, 8),
        (11, 0, 20, 8),
        (0, 8, 11, 14),
        (11, 8, 20, 14),
    )


def test_auto_sized_manual_grid_cuts_cover_the_full_source() -> None:
    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    result = segment_sheet(
        image,
        SegmentationConfig(
            frame_count=4,
            orientation="grid",
            rows=2,
            columns=2,
            manual_cut_positions_x=(4,),
            manual_cut_positions_y=(6,),
        ),
    )
    assert result.regions == (
        (0, 0, 4, 6),
        (4, 0, 10, 6),
        (0, 6, 4, 10),
        (4, 6, 10, 10),
    )
    assert not any("unused pixel" in warning for warning in result.warnings)


def test_auto_cut_positions_returns_torso_aware_grid_axes() -> None:
    image = Image.new("RGBA", (32, 40), (0, 255, 0, 255))
    draw = ImageDraw.Draw(image)
    for row in range(2):
        for column in range(2):
            x = column * 16
            y = row * 20
            draw.rectangle((x + 5, y + 4, x + 10, y + 15), fill=(180, 90, 30, 255))
    cuts_x, cuts_y = auto_cut_positions(
        image,
        SegmentationConfig(frame_count=4, orientation="grid", rows=2, columns=2),
        AutoCenterConfig(canvas_width=16, canvas_height=20, canonical_anchor=(8, 10)),
    )
    assert len(cuts_x) == 1
    assert len(cuts_y) == 1


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


def test_auto_center_respects_a_custom_target_anchor() -> None:
    frame = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((14, 10, 31, 34), fill=(180, 90, 30, 255))
    analysis = analyze_center_frames(
        [frame],
        AutoCenterConfig(
            canvas_width=64,
            canvas_height=64,
            canonical_anchor=(16, 16),
            confidence_threshold=0,
        ),
    )
    result = auto_center_frames(
        [frame],
        AutoCenterConfig(
            canvas_width=64,
            canvas_height=64,
            canonical_anchor=(16, 16),
            confidence_threshold=0,
        ),
        analysis=analysis,
        target_anchor=(28, 30),
    )
    assert result.adjustments[0].final_anchor == (28.0, 30.0)


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
    assert result.frames[0].size == (76, 50)
    alpha = np.asarray(result.frames[0])[:, :, 3]
    assert np.where(alpha > 0)[1].max() == 75
    assert result.adjustments[0].applied_translation[0] == 17
    assert result.status == "passed"
    assert result.adjustments[0].manual_review is False


def test_auto_center_clamp_expands_canvas_when_content_is_larger() -> None:
    frame = Image.new("RGBA", (96, 64), (0, 0, 0, 0))
    ImageDraw.Draw(frame).rectangle((10, 12, 79, 35), fill=(180, 90, 30, 255))
    result = auto_center_frames(
        [frame],
        AutoCenterConfig(
            method="bounding_box",
            canvas_width=64,
            canvas_height=48,
            canonical_anchor=(32, 24),
            confidence_threshold=0,
        ),
        overflow_strategy="clamp",
    )
    assert result.frames[0].size == (70, 48)
    alpha = np.asarray(result.frames[0])[:, :, 3]
    assert alpha.sum() > 0
    assert np.where(alpha > 0)[1].max() == 69


def test_auto_center_tolerates_mixed_frame_sizes_in_flow_prediction() -> None:
    small = Image.new("RGBA", (48, 40), (0, 0, 0, 0))
    large = Image.new("RGBA", (64, 56), (0, 0, 0, 0))
    draw_small = ImageDraw.Draw(small)
    draw_large = ImageDraw.Draw(large)
    draw_small.rectangle((12, 8, 28, 30), fill=(180, 90, 30, 255))
    draw_large.rectangle((18, 12, 40, 38), fill=(180, 90, 30, 255))
    result = auto_center_frames(
        [small, large],
        AutoCenterConfig(
            method="body",
            canvas_width=80,
            canvas_height=72,
            canonical_anchor=(40, 36),
            confidence_threshold=0,
        ),
        overflow_strategy="clamp",
    )
    assert len(result.adjustments) == 2
    assert all(frame.size == (80, 72) for frame in result.frames)


def test_preview_crop_pads_smaller_frames_to_largest_canvas() -> None:
    a = Image.new("RGBA", (40, 30), (0, 0, 0, 0))
    b = Image.new("RGBA", (52, 36), (0, 0, 0, 0))
    ImageDraw.Draw(a).rectangle((4, 4, 12, 16), fill=(255, 128, 0, 255))
    ImageDraw.Draw(b).rectangle((6, 6, 20, 22), fill=(0, 200, 255, 255))
    result, warning = _safe_trim_transparent_frames(
        [a, b],
        ExportCropConfig(enabled=False, padding=2, alpha_threshold=8),
    )
    assert warning is None
    assert result.source_size == (52, 36)
    assert all(frame.size == (52, 36) for frame in result.frames)


def test_pad_frames_to_common_canvas_preserves_pixels_without_scaling() -> None:
    small = Image.new("RGBA", (10, 8), (0, 0, 0, 0))
    large = Image.new("RGBA", (14, 12), (0, 0, 0, 0))
    ImageDraw.Draw(small).rectangle((2, 1, 5, 5), fill=(255, 128, 0, 255))
    padded = pad_frames_to_common_canvas([small, large])
    assert all(frame.size == (14, 12) for frame in padded)
    arr = np.asarray(padded[0])
    assert tuple(arr[3, 3]) == (255, 128, 0, 255)
    assert tuple(arr[10, 12]) == (0, 0, 0, 0)


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


def test_background_rect_crop_tool_creates_a_pixel_selection() -> None:
    from streamlit import session_state as ss

    ss.clear()
    prefix = "sheet-background-crop"
    ss[f"{prefix}:background_last_event"] = None
    ss[f"{prefix}:background_tool"] = "wand"
    ss[f"{prefix}:background_selection_masks"] = [None]
    ss[f"{prefix}:background_manual_ops"] = {}
    frame = Image.new("RGBA", (8, 6), (0, 255, 0, 255))

    changed = _handle_background_editor_event(
        type("Session", (), {"session_id": prefix})(),
        (frame,),
        0,
        {
            "eventId": "crop-rect-1",
            "type": "crop",
            "tool": "crop_rect",
            "shape": "rect",
            "start": [2, 1],
            "end": [4, 3],
        },
        tolerance=0,
        contiguous=True,
    )

    assert changed is True
    assert ss[f"{prefix}:background_tool"] == "move"
    mask = ss[f"{prefix}:background_selection_masks"][0]
    assert isinstance(mask, np.ndarray)
    assert mask.shape == (6, 8)
    assert int(mask.sum()) == 9
    floating = ss[f"{prefix}:background_floating_selection"]
    assert floating["bounds"] == (2, 1, 5, 4)
    assert floating["piece"].size == frame.size
    assert floating["remainder"].getpixel((3, 2))[3] == 0

    moved = _handle_background_editor_event(
        type("Session", (), {"session_id": prefix})(),
        (frame,),
        0,
        {
            "eventId": "move-rect-1",
            "type": "floating-transform",
            "tool": "move",
            "deltaX": 2,
            "deltaY": 1,
        },
        tolerance=0,
        contiguous=True,
    )

    assert moved is True
    assert f"{prefix}:background_floating_selection" not in ss
    operation = ss[f"{prefix}:background_manual_ops"][0][-1]
    assert operation["kind"] == "move_mask"
    assert (operation["offset_x"], operation["offset_y"]) == (2, 1)


def test_manual_background_move_mask_preserves_canvas_and_moves_pixels() -> None:
    frame = Image.new("RGBA", (8, 6), (0, 0, 0, 0))
    ImageDraw.Draw(frame).rectangle((2, 1, 4, 3), fill=(220, 80, 40, 255))
    mask = np.zeros((6, 8), dtype=bool)
    mask[1:4, 2:5] = True

    moved = apply_manual_background_edits(
        (frame,),
        {
            0: [
                {
                    "kind": "move_mask",
                    **encode_mask(mask),
                    "offset_x": 2,
                    "offset_y": 1,
                }
            ]
        },
    )[0]

    assert moved.size == frame.size
    assert moved.getpixel((2, 1))[3] == 0
    assert moved.getpixel((4, 2)) == (220, 80, 40, 255)
    assert moved.getpixel((6, 4)) == (220, 80, 40, 255)


def test_center_drag_adds_delta_to_the_existing_manual_offset() -> None:
    from streamlit import session_state as ss

    ss.clear()
    prefix = "sheet-drag-base-test"
    ss[f"{prefix}:offsets"] = [(5, -2)]
    changed = _handle_center_editor_event(
        type("Session", (), {"session_id": prefix})(),
        1,
        0,
        {
            "eventId": "drag-base-1",
            "type": "transform",
            "offsetX": 13,
            "offsetY": 8,
        },
        home_offset=(10, 10),
        base_manual_offset=(5, -2),
    )
    assert changed is True
    assert ss[f"{prefix}:offsets"] == [(8, -4)]


def test_history_undo_redo_restores_center_offsets() -> None:
    from streamlit import session_state as ss

    ss.clear()
    prefix = "sheet-history-center"
    session = type("Session", (), {"session_id": prefix})()
    ss[f"{prefix}:offsets"] = [(0, 0), (1, 2)]
    ss[f"{prefix}:center_ground_line_y"] = 15
    before = _center_history_snapshot(prefix)
    ss[f"{prefix}:offsets"] = [(8, -4), (1, 2)]
    after = _center_history_snapshot(prefix)
    assert _record_editor_history(
        session,
        scope="center",
        label="Mover frame",
        before=before,
        after=after,
    )

    store = type("Store", (), {})()
    assert _handle_editor_history_event(
        store,
        session,
        {"eventId": "undo-1", "type": "history", "action": "undo"},
    )
    assert ss[f"{prefix}:offsets"] == [(0, 0), (1, 2)]
    assert ss[f"{prefix}:offset_x_widget:0"] == 0

    assert _handle_editor_history_event(
        store,
        session,
        {"eventId": "redo-1", "type": "history", "action": "redo"},
    )
    assert ss[f"{prefix}:offsets"] == [(8, -4), (1, 2)]
    assert ss[f"{prefix}:offset_y_widget:0"] == -4


def test_history_selection_masks_are_compact_and_lossless() -> None:
    mask = np.zeros((19, 23), dtype=bool)
    mask[2:8, 4:17] = True
    packed = _pack_selection_masks([None, mask])

    assert packed[0] is None
    assert isinstance(packed[1]["data"], bytes)
    assert len(packed[1]["data"]) < mask.size
    restored = _unpack_selection_masks(packed)
    assert restored[0] is None
    assert np.array_equal(restored[1], mask)


def test_alignment_export_readiness_rejects_stale_or_review_manifests() -> None:
    segmentation = SegmentationConfig(frame_count=1)
    background = BackgroundRemovalConfig()
    center = AutoCenterConfig(
        canvas_width=16,
        canvas_height=16,
        canonical_anchor=(8, 8),
    )
    manifest = {
        "status": "passed",
        "config": {
            "segmentation": segmentation.to_dict(),
            "background": background.to_dict(),
            "auto_center": center.to_dict(),
            "manual_offsets": [[0, 0]],
        },
        "metadata": {
            "frames": [{"locked": False, "manual_review": False}],
        },
    }
    assert _alignment_export_readiness(
        manifest,
        segmentation_config=segmentation,
        background_config=background,
        center_config=center,
        manual_offsets=[(0, 0)],
        locks=[False],
        frame_count=1,
    ) == (True, "")

    review_manifest = dict(manifest)
    review_manifest["status"] = "manual_review"
    ready, reason = _alignment_export_readiness(
        review_manifest,
        segmentation_config=segmentation,
        background_config=background,
        center_config=center,
        manual_offsets=[(0, 0)],
        locks=[False],
        frame_count=1,
    )
    assert ready is False
    assert "revisión" in reason


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


def test_contact_sheet_can_show_cell_guides_and_axes() -> None:
    frame = Image.new("RGBA", (12, 10), (0, 0, 0, 0))
    adjustment = FrameAdjustment(
        frame_index=0,
        auto_anchor=(6, 5),
        applied_translation=(0, 0),
        body_bbox=(3, 3, 7, 7),
    )
    preview = np.asarray(
        render_contact_sheet(
            [frame],
            adjustments=[adjustment],
            columns=1,
            scale=1,
            show_cell_guides=True,
            show_center_axes=True,
            show_anchor_guides=True,
            show_bbox=False,
            guide_padding=2,
        )
    )
    assert preview.shape[:2] == (14, 16)
    assert tuple(preview[2, 3, :3]) == (91, 223, 255)
    assert tuple(preview[7, 3, :3]) == (255, 255, 255)
    assert tuple(preview[7, 8, :3]) == (255, 76, 160)
    axes_only = np.asarray(
        render_contact_sheet(
            [frame],
            adjustments=[adjustment],
            columns=1,
            scale=1,
            show_cell_guides=False,
            show_center_axes=True,
            show_anchor_guides=False,
            show_bbox=False,
            guide_padding=2,
        )
    )
    assert tuple(axes_only[3, 3, :3]) != (91, 223, 255)
    assert tuple(axes_only[7, 8, :3]) == (255, 255, 255)
    no_guides = np.asarray(
        render_contact_sheet(
            [frame],
            adjustments=[adjustment],
            columns=1,
            scale=1,
            show_cell_guides=False,
            show_center_axes=False,
            show_anchor_guides=False,
            show_bbox=False,
        )
    )
    assert tuple(no_guides[5, 6, :3]) != (255, 76, 160)


def test_contact_sheet_grid_and_x_axes_are_continuous_across_cells() -> None:
    frames = [Image.new("RGBA", (4, 4), (0, 0, 0, 0)) for _ in range(4)]
    preview = np.asarray(
        render_contact_sheet(
            frames,
            columns=2,
            scale=2,
            show_cell_guides=True,
            show_center_axes=True,
            show_anchor_guides=False,
            show_bbox=False,
        )
    )

    # Shared cuts span the complete sheet instead of leaving gaps between cells.
    assert tuple(preview[1, 8, :3]) == (91, 223, 255)
    assert tuple(preview[8, 1, :3]) == (91, 223, 255)
    # The X axis reaches the cut, while the cut itself remains visible on top.
    assert tuple(preview[4, 7, :3]) == (255, 255, 255)
    assert tuple(preview[4, 8, :3]) == (91, 223, 255)


def test_contact_sheet_5x4_shows_every_grid_boundary_and_y_axis() -> None:
    frames = [Image.new("RGBA", (4, 4), (0, 0, 0, 0)) for _ in range(20)]
    preview = np.asarray(
        render_contact_sheet(
            frames,
            columns=5,
            scale=1,
            show_cell_guides=True,
            show_center_axes=True,
            show_anchor_guides=False,
            show_bbox=False,
            guide_padding=2,
        )
    )

    cyan = (91, 223, 255)
    white = (255, 255, 255)
    for x in (2, 6, 10, 14, 18, 21):
        assert tuple(preview[2, x, :3]) == cyan
    for y in (2, 6, 10, 14, 17):
        assert tuple(preview[y, 3, :3]) == cyan
    for x in (4, 8, 12, 16, 20):
        assert tuple(preview[3, x, :3]) == white


def test_crop_padding_never_hides_5x4_y_axes() -> None:
    frames: list[Image.Image] = []
    adjustments: list[FrameAdjustment] = []
    for index in range(20):
        frame = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
        ImageDraw.Draw(frame).rectangle((7, 6, 16, 17), fill=(180, 90, 30, 255))
        frames.append(frame)
        adjustments.append(
            FrameAdjustment(
                frame_index=index,
                auto_anchor=(12, 12),
                applied_translation=(0, 0),
                body_bbox=(7, 6, 17, 18),
            )
        )

    for crop_padding in (0, 2, 5):
        crop = trim_transparent_frames(
            frames,
            ExportCropConfig(enabled=True, padding=crop_padding, alpha_threshold=8),
        )
        preview = np.asarray(
            render_contact_sheet(
                crop.frames,
                adjustments=adjustments,
                columns=5,
                scale=2,
                origin_offset=(crop.bbox[0], crop.bbox[1]),
                show_cell_guides=True,
                show_center_axes=True,
                show_anchor_guides=True,
                show_bbox=False,
                guide_padding=8,
            )
        )
        cell_width = crop.frames[0].width * 2
        axis_y = 8 * 2 + 3
        expected_axes = [
            8 * 2 + column * cell_width + (crop.frames[0].width // 2) * 2
            for column in range(5)
        ]
        assert all(tuple(preview[axis_y, x, :3]) == (255, 255, 255) for x in expected_axes)


def test_large_crop_preview_keeps_guides_visible_after_downscaling() -> None:
    frames: list[Image.Image] = []
    for _ in range(20):
        frame = Image.new("RGBA", (300, 240), (0, 0, 0, 0))
        ImageDraw.Draw(frame).rectangle((80, 50, 219, 189), fill=(180, 90, 30, 255))
        frames.append(frame)
    crop = trim_transparent_frames(
        frames,
        ExportCropConfig(enabled=True, padding=70, alpha_threshold=8),
    )
    preview = render_contact_sheet(
        crop.frames,
        columns=5,
        scale=2,
        show_cell_guides=True,
        show_center_axes=True,
        show_anchor_guides=False,
        show_bbox=False,
        guide_padding=8,
        guide_display_width=820,
    )

    source = np.asarray(preview)[:, :, :3]
    expected_width = (2 * preview.width + 819) // 820
    cell_width = crop.frames[0].width * 2
    sample_y = 8 * 2 + 12
    for column in range(5):
        axis_x = 8 * 2 + column * cell_width + (crop.frames[0].width // 2) * 2
        run_start = axis_x - expected_width // 2
        white_run = np.all(
            source[sample_y, run_start : run_start + expected_width, :]
            == (255, 255, 255),
            axis=1,
        )
        assert int(white_run.sum()) >= expected_width - 1


def test_export_can_preserve_manual_review_as_an_emergency_warning(tmp_path: Path) -> None:
    store = SheetSessionStore(tmp_path)
    session = store.create(_png_bytes(Image.new("RGBA", (4, 4), (0, 0, 0, 0))))
    session.stages["alignment"] = {"status": "manual_review"}
    session.frame_adjustments = [
        FrameAdjustment(
            frame_index=0,
            auto_anchor=(2, 2),
            applied_translation=(0, 0),
            body_bbox=(1, 1, 3, 3),
            manual_review=True,
        )
    ]
    store.save(session)

    manifest = store.export(
        session,
        [Image.new("RGBA", (4, 4), (0, 0, 0, 0))],
        allow_manual_review=True,
    )

    assert manifest["status"] == "manual_review"
    assert len(manifest["validation_warnings"]) == 2
    assert (tmp_path / manifest["output_png"]).is_file()
    assert session.stages["export"]["status"] == "manual_review"


def test_export_switches_between_individual_frames_and_single_sheet(tmp_path: Path) -> None:
    store = SheetSessionStore(tmp_path)
    session = store.create(_png_bytes(Image.new("RGBA", (8, 4), (0, 0, 0, 0))))
    session.stages["alignment"] = {"status": "passed"}
    session.frame_adjustments = [
        FrameAdjustment(
            frame_index=index,
            auto_anchor=(2, 2),
            applied_translation=(0, 0),
            body_bbox=(1, 1, 3, 3),
        )
        for index in range(2)
    ]
    store.save(session)
    frames = (
        Image.new("RGBA", (4, 4), (255, 0, 0, 255)),
        Image.new("RGBA", (4, 4), (0, 0, 255, 255)),
    )

    individual = store.export(
        session,
        frames,
        export_frames=True,
        export_sheet_png=False,
        export_contact_sheet=False,
    )

    assert individual["export_kind"] == "individual"
    assert individual["output_png"] is None
    assert len(individual["output_frames"]) == 2
    assert all((tmp_path / path).is_file() for path in individual["output_frames"])
    individual_dir = tmp_path / individual["output_frames_dir"]
    assert not (individual_dir.parent / "sprite-sheet.png").exists()

    spritesheet = store.export(
        session,
        frames,
        export_frames=False,
        export_sheet_png=True,
        export_contact_sheet=False,
    )

    assert spritesheet["export_kind"] == "spritesheet"
    assert spritesheet["output_frames"] == []
    assert spritesheet["output_frames_dir"] is None
    assert (tmp_path / spritesheet["output_png"]).is_file()
    assert not (tmp_path / spritesheet["output_png"]).parent.joinpath("frames").exists()


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
