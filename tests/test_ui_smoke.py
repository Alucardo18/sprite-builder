from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw
from streamlit.testing.v1 import AppTest

from sprite_builder.sheets import SheetSessionStore
from sprite_builder.ui import app


def test_manual_alignment_instruction_is_not_duplicated() -> None:
    source = Path(app.__file__).read_text(encoding="utf-8")

    assert source.count(
        "La previsualización y la edición viven en el mismo canvas."
    ) == 1
    assert source.count(
        "Arrastra el frame activo dentro de la grilla para reajustarlo."
    ) == 1


def test_streamlit_app_opens_with_all_workflow_tabs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image = Image.new("RGB", (32, 32), (0, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 5, 21, 26), fill=(180, 90, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    SheetSessionStore(tmp_path).create(buffer.getvalue(), source_name="hero.png")
    monkeypatch.setenv("SPRITE_BUILDER_WORKSPACE", str(tmp_path))

    test_app = AppTest.from_file(str(Path(app.__file__))).run(timeout=30)
    assert not test_app.exception
    assert test_app.title[0].value == "sprite-builder"
    assert [tab.label for tab in test_app.tabs] == [
        "Sheet",
        "Background",
        "Studio",
        "Segmentación + Auto Center",
        "Export",
    ]


def test_tileset_builder_is_available_without_a_sprite_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SPRITE_BUILDER_WORKSPACE", str(tmp_path))

    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.query_params["page"] = "tilesets"
    test_app.run(timeout=30)

    assert not test_app.exception
    assert not test_app.tabs
    assert any(
        uploader.label == "Cargar tileset PNG"
        for uploader in test_app.file_uploader
    )


def test_tileset_builder_is_a_page_not_a_sprite_workflow_tab() -> None:
    source = Path(app.__file__).read_text(encoding="utf-8")

    header_source = (
        Path(app.__file__).parent / "header_nav_component" / "index.html"
    ).read_text(encoding="utf-8")

    assert "header_navigation(page)" in source
    assert 'querySelector(\'[data-testid="stHeader"]\')' in header_source
    assert 'textContent.trim() === "Deploy"' in header_source
    assert "deployButton.parentElement.insertBefore(navigation, deployButton)" in header_source
    assert "with tileset_tab:" not in source
    assert "Tile Size" in (
        Path(app.__file__).parent / "tileset_editor_component" / "index.html"
    ).read_text(encoding="utf-8")


def test_studio_keeps_the_canvas_dominant_and_separates_publication() -> None:
    source = Path(app.__file__).read_text(encoding="utf-8")

    assert 'publish_col, canvas_col = st.columns((1.05, 4.95)' in source
    assert '"Publicar capas para Auto Center"' in source
    assert '"pendiente de publicar a Auto Center"' in source
    assert "studio_layers=studio_layers" in source
    assert "active_layer_id=active_layer_id" in source
    # Pixel edits revise the document, but must not force the component to fit
    # and remount just because the revision number changed.
    assert 'f"{prefix}:layers:{document.document_id}:{document.revision}:"' not in source


def test_export_allows_an_explicit_manual_review_override() -> None:
    source = Path(app.__file__).read_text(encoding="utf-8")

    assert "_alignment_export_readiness(" in source
    assert '"Exportar con advertencias"' in source
    assert "allow_manual_review=True" in source
    assert '"Anchor revisado y aprobado"' in source
    assert "if manifest:" in source
    assert "export_sheet_png=not include_frames" in source
    assert '"Exportar PNG por frame"' in source
    assert '"Exportar sprite-sheet PNG"' in source
    assert 'f"Descargar {len(frame_paths)} frames PNG (.zip)"' in source


def test_studio_component_events_select_and_reorder_the_layer_matrix() -> None:
    source = Path(app.__file__).read_text(encoding="utf-8")

    assert 'if event_type == "studio":' in source
    assert 'if action == "select-cel":' in source
    assert 'if action == "reorder-layer":' in source
    assert 'reason="reorder-layer-drag"' in source
    assert '"selection-command",' in source
    assert '"floating-selection",' in source
    assert '"edit-batch",' in source
    assert '"transform",' in source
