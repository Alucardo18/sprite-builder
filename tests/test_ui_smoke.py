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
        "Segmentación + Auto Center",
        "Export",
    ]
