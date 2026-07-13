from __future__ import annotations

import io
import json

from PIL import Image

from sprite_builder.orchestration import sha256_file
from sprite_builder.sheets import (
    LayeredSpriteDocument,
    SheetSessionStore,
    SpriteCel,
    SpriteLayer,
    composite_document_frame,
    composite_document_frames,
    delete_document_frame,
    duplicate_document_frame,
    fill_cel_selection,
    move_document_frame,
    outline_cel_pixels,
    paint_cel_stroke,
    remove_isolated_pixels,
    replace_cel_color,
    transform_cel_selection,
)


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_layered_document_composes_tracks_and_ignores_vfx_for_analysis() -> None:
    body = SpriteLayer("body", "Cuerpo", role="body")
    vfx = SpriteLayer("vfx", "Chispas", role="vfx")
    document = LayeredSpriteDocument(
        schema_version="1.0",
        document_id="doc-test",
        canvas_width=5,
        canvas_height=5,
        frame_count=1,
        layers=(body, vfx),
        cels=(
            SpriteCel("body", 0, "", "", offset_x=1, offset_y=1),
            SpriteCel("vfx", 0, "", "", offset_x=3, offset_y=0),
        ),
    )
    body_image = Image.new("RGBA", (2, 2), (255, 40, 20, 255))
    vfx_image = Image.new("RGBA", (2, 2), (40, 180, 255, 255))

    flattened = composite_document_frames(
        document,
        {("body", 0): body_image, ("vfx", 0): vfx_image},
    )[0]
    analysis = composite_document_frames(
        document,
        {("body", 0): body_image, ("vfx", 0): vfx_image},
        analysis_only=True,
    )[0]

    assert flattened.getpixel((3, 0)) == (40, 180, 255, 255)
    assert flattened.getpixel((1, 1)) == (255, 40, 20, 255)
    assert analysis.getpixel((3, 0)) == (0, 0, 0, 0)
    assert analysis.getpixel((1, 1)) == (255, 40, 20, 255)


def test_document_expansion_adds_transparent_space_without_rescaling() -> None:
    layer = SpriteLayer("source", "Fuente IA", role="source", locked=True)
    document = LayeredSpriteDocument(
        schema_version="1.0",
        document_id="expand-test",
        canvas_width=4,
        canvas_height=4,
        frame_count=1,
        layers=(layer,),
        cels=(SpriteCel("source", 0, "", "", offset_x=-2, offset_y=1),),
    )
    source = Image.new("RGBA", (4, 2), (220, 80, 30, 255))

    expanded = document.expanded_to_content({("source", 0): source}, padding=1)

    assert (expanded.canvas_width, expanded.canvas_height) == (8, 6)
    assert expanded.cel("source", 0) is not None
    assert expanded.cel("source", 0).offset_x == 1  # type: ignore[union-attr]
    assert expanded.cel("source", 0).offset_y == 2  # type: ignore[union-attr]
    assert source.size == (4, 2)


def test_pixel_tools_preserve_geometry_and_exact_colors() -> None:
    import numpy as np

    image = Image.new("RGBA", (7, 7), (0, 0, 0, 0))
    image.putpixel((2, 3), (100, 80, 60, 255))
    image.putpixel((3, 3), (100, 80, 60, 255))
    mask = np.zeros((7, 7), dtype=bool)
    mask[2:5, 1:5] = True

    filled = fill_cel_selection(image, mask, (10, 20, 30, 255))
    assert filled.size == image.size
    assert filled.getpixel((1, 2)) == (10, 20, 30, 255)
    replaced = replace_cel_color(
        filled,
        (10, 20, 30, 255),
        (220, 40, 90, 255),
        mask=mask,
    )
    assert replaced.getpixel((4, 4)) == (220, 40, 90, 255)

    transformed, transformed_mask = transform_cel_selection(
        replaced,
        mask,
        "flip-horizontal",
    )
    assert transformed.size == image.size
    assert transformed_mask.shape == mask.shape
    scaled, scaled_mask = transform_cel_selection(replaced, mask, "scale-2x")
    assert scaled.size == image.size
    assert scaled_mask.shape == mask.shape
    outlined = outline_cel_pixels(image, (255, 0, 0, 255), radius=1)
    assert outlined.getpixel((1, 3)) == (255, 0, 0, 255)
    isolated = Image.new("RGBA", (5, 5), (0, 0, 0, 0))
    isolated.putpixel((2, 2), (255, 255, 255, 255))
    cleaned = remove_isolated_pixels(isolated, minimum_neighbors=1)
    assert cleaned.getpixel((2, 2))[3] == 0


def test_single_frame_compositor_and_timeline_frame_operations() -> None:
    layer = SpriteLayer("body", "Body", role="body")
    document = LayeredSpriteDocument(
        schema_version="1.0",
        document_id="timeline-test",
        canvas_width=4,
        canvas_height=4,
        frame_count=2,
        layers=(layer,),
        cels=(SpriteCel("body", 0, "", ""), SpriteCel("body", 1, "", "")),
    )
    red = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    blue = Image.new("RGBA", (4, 4), (0, 0, 255, 255))
    images = {("body", 0): red, ("body", 1): blue}
    assert composite_document_frame(document, images, 1).tobytes() == (
        composite_document_frames(document, images)[1].tobytes()
    )

    duplicated, duplicate_images = duplicate_document_frame(document, images, 0)
    assert duplicated.frame_count == 3
    assert duplicate_images[("body", 1)].getpixel((0, 0)) == (255, 0, 0, 255)
    moved, moved_images = move_document_frame(duplicated, duplicate_images, 2, 0)
    assert moved_images[("body", 0)].getpixel((0, 0)) == (0, 0, 255, 255)
    deleted, deleted_images = delete_document_frame(moved, moved_images, 1)
    assert deleted.frame_count == 2
    assert set(deleted_images) == {("body", 0), ("body", 1)}


def test_layer_document_round_trip_publishes_flattened_artwork(tmp_path) -> None:
    source = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    source.putpixel((2, 3), (180, 90, 30, 255))
    store = SheetSessionStore(tmp_path)
    session = store.create(_png_bytes(source), source_name="hero.png")

    created = store.create_layer_document(session, [source])
    document, images = store.load_layer_document(session)
    assert created.document_id == document.document_id
    assert [layer.name for layer in document.layers] == ["Fuente IA", "Retoque"]
    images[("retouch", 0)].putpixel((4, 5), (70, 220, 130, 255))
    saved, outputs = store.publish_layer_document(
        session,
        document,
        images,
        reason="paint",
    )

    assert len(outputs) == 1
    assert saved.revision == document.revision
    reopened = store.load(session.session_id)
    assert reopened.layer_document is not None
    assert "artwork" in reopened.stages
    artwork = Image.open(store.stage_paths(reopened, "artwork")[0]).convert("RGBA")
    assert artwork.getpixel((2, 3)) == (180, 90, 30, 255)
    assert artwork.getpixel((4, 5)) == (70, 220, 130, 255)


def test_layer_history_restores_a_verified_immutable_attempt(tmp_path) -> None:
    source = Image.new("RGBA", (6, 6), (0, 0, 0, 0))
    store = SheetSessionStore(tmp_path)
    session = store.create(_png_bytes(source), source_name="hero.png")
    store.create_layer_document(session, [source])
    first_pointer = dict(session.layer_document or {})
    document, images = store.load_layer_document(session)

    images[("retouch", 0)].putpixel((3, 4), (255, 90, 40, 255))
    store.save_layer_document(session, document.revised(), images, reason="paint")
    assert session.layer_document != first_pointer

    restored = store.restore_layer_document_attempt(session, first_pointer)
    restored_document, restored_images = store.load_layer_document(session)
    assert restored.document_id == restored_document.document_id
    assert session.layer_document["cache_key"] == first_pointer["cache_key"]  # type: ignore[index]
    assert restored_images[("retouch", 0)].getpixel((3, 4)) == (0, 0, 0, 0)


def test_publishing_distinct_layer_attempts_replaces_artwork_lineage_and_invalidates_downstream(
    tmp_path,
) -> None:
    """Auto Center can only consume the current immutable layer revision."""

    source = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    source.putpixel((1, 1), (180, 90, 30, 255))
    store = SheetSessionStore(tmp_path)
    session = store.create(_png_bytes(source), source_name="hero.png")
    store.create_layer_document(session, [source])
    document, images = store.load_layer_document(session)

    _, first_artwork = store.publish_layer_document(
        session,
        document,
        images,
        reason="apply-to-autocenter",
    )
    first_artwork_path = first_artwork[0]
    first_artwork_key = session.stages["artwork"]["cache_key"]
    first_layer_key = session.layer_document["cache_key"]  # type: ignore[index]
    first_artwork_sha = sha256_file(first_artwork_path)

    # These mimic a saved Auto Center and export which must no longer be valid
    # once Studio publishes a different flattened document.
    store.commit_stage(
        session,
        "alignment",
        [Image.open(first_artwork_path).convert("RGBA")],
        config={"center": "body"},
    )
    store.commit_stage(
        session,
        "export",
        [Image.open(first_artwork_path).convert("RGBA")],
        config={"layout": "horizontal"},
    )
    assert {"alignment", "export"}.issubset(session.stages)

    images[("retouch", 0)].putpixel((6, 5), (70, 220, 130, 255))
    revised, second_artwork = store.publish_layer_document(
        session,
        document.revised(),
        images,
        reason="apply-to-autocenter",
    )

    assert revised.revision == document.revision + 1
    assert session.layer_document is not None
    assert session.layer_document["cache_key"] != first_layer_key
    assert session.stages["artwork"]["cache_key"] != first_artwork_key
    assert second_artwork[0] != first_artwork_path
    assert sha256_file(first_artwork_path) == first_artwork_sha
    assert "alignment" not in session.stages
    assert "export" not in session.stages

    # The active artwork stage is the exact layer attempt that was just saved;
    # its input manifest SHA creates a verifiable Studio -> Auto Center lineage.
    artwork_manifest_path = tmp_path / session.stages["artwork"]["manifest"]
    artwork_manifest = json.loads(artwork_manifest_path.read_text(encoding="utf-8"))
    layer_input = next(
        item
        for item in artwork_manifest["inputs"]
        if item["role"] == "layer_document_manifest"
    )
    assert layer_input["path"] == session.layer_document["manifest"]
    assert layer_input["sha256"] == session.layer_document["manifest_sha256"]
    assert sha256_file(tmp_path / layer_input["path"]) == layer_input["sha256"]
    assert artwork_manifest["metadata"]["layer_document"] == session.layer_document

    reopened = store.load(session.session_id)
    latest_artwork = Image.open(store.stage_paths(reopened, "artwork")[0]).convert("RGBA")
    assert latest_artwork.getpixel((1, 1)) == (180, 90, 30, 255)
    assert latest_artwork.getpixel((6, 5)) == (70, 220, 130, 255)


def test_stage_attempt_cache_key_includes_input_pixels(tmp_path) -> None:
    """Same settings must not restore an older alignment with different pixels."""

    source = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    store = SheetSessionStore(tmp_path)
    session = store.create(_png_bytes(source), source_name="hero.png")
    first = source.copy()
    first.putpixel((1, 1), (255, 20, 20, 255))
    first_output = store.commit_stage(
        session,
        "alignment",
        [first],
        config={"center": "body"},
    )
    first_key = session.stages["alignment"]["cache_key"]

    second = source.copy()
    second.putpixel((1, 1), (20, 255, 20, 255))
    second_output = store.commit_stage(
        session,
        "alignment",
        [second],
        config={"center": "body"},
    )

    assert first_output[0] != second_output[0]
    assert session.stages["alignment"]["cache_key"] != first_key
    assert Image.open(second_output[0]).convert("RGBA").getpixel((1, 1)) == (
        20,
        255,
        20,
        255,
    )


def test_pixel_stroke_stays_hard_edged_and_can_erase() -> None:
    canvas = Image.new("RGBA", (8, 8))
    painted = paint_cel_stroke(
        canvas,
        ((1, 1), (4, 1)),
        color=(240, 180, 60, 255),
    )
    erased = paint_cel_stroke(
        painted,
        ((2, 1),),
        color=(0, 0, 0, 0),
        erase=True,
    )

    assert painted.getpixel((3, 1)) == (240, 180, 60, 255)
    assert erased.getpixel((2, 1)) == (0, 0, 0, 0)
    assert erased.getpixel((3, 1)) == (240, 180, 60, 255)


def test_store_can_create_a_blank_multi_frame_sprite(tmp_path) -> None:
    store = SheetSessionStore(tmp_path)

    session = store.create_blank_sprite(
        canvas_width=16,
        canvas_height=20,
        frame_count=3,
    )

    assert store.source_path(session).is_file()
    assert Image.open(store.source_path(session)).size == (48, 20)
    assert session.segmentation_config.frame_count == 3
    assert session.segmentation_config.cell_width == 16
    assert session.auto_center_config.canonical_anchor == (8, 10)
