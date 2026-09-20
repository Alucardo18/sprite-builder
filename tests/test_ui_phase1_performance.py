from __future__ import annotations

import ast
from pathlib import Path

from sprite_builder.ui import app


class _FakeTab:
    def __init__(self, label: str, *, open: bool) -> None:
        self.label = label
        self.open = open

    def __enter__(self) -> _FakeTab:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _FakeStreamlit:
    def __init__(self, selected: int) -> None:
        self.selected = selected
        self.tabs_calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def subheader(self, _label: str) -> None:
        return None

    def tabs(self, labels: tuple[str, ...], **kwargs: object) -> tuple[_FakeTab, ...]:
        self.tabs_calls.append((labels, kwargs))
        return tuple(
            _FakeTab(label, open=index == self.selected)
            for index, label in enumerate(labels)
        )


def test_tileset_builder_does_not_render_hidden_tabs(monkeypatch) -> None:
    fake_st = _FakeStreamlit(selected=2)
    calls: list[str] = []
    monkeypatch.setattr(app, "st", fake_st)
    monkeypatch.setattr(app, "_render_tile_builder_wizard_and_status", lambda: None)
    monkeypatch.setattr(app, "_render_tileset_atlas_editor", lambda: calls.append("atlas"))
    monkeypatch.setattr(app, "_render_terrain_patterns", lambda: calls.append("patterns"))
    monkeypatch.setattr(
        app,
        "_render_finishing_and_export_studio",
        lambda: calls.append("finishing"),
    )
    monkeypatch.setattr(app, "_render_tileset_map_tester", lambda: calls.append("map"))

    app._render_tileset_builder()

    assert calls == ["finishing"]
    assert fake_st.tabs_calls == [
        (
            ("Atlas", "Pattern Studio", "Estudio de Acabado y Materiales", "Map Tester"),
            {"key": "tileset_builder:tabs", "on_change": "rerun"},
        )
    ]


def test_phase1_sheet_tabs_are_dynamic_and_export_preview_is_one_effective_fragment() -> None:
    source_path = Path(app.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert source.count("def _render_export_preview_fragment(") == 1
    assert hasattr(app._render_export_preview_fragment, "__wrapped__")

    main = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    tab_calls = [
        node
        for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
        and node.func.attr == "tabs"
    ]
    assert len(tab_calls) == 1
    assert {
        keyword.arg: ast.literal_eval(keyword.value)
        for keyword in tab_calls[0].keywords
        if keyword.arg in {"key", "on_change"}
    } == {"key": "sheet_studio:workflow_tabs", "on_change": "rerun"}

    guarded_tabs = {
        node.test.value.id
        for node in ast.walk(main)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Attribute)
        and node.test.attr == "open"
        and isinstance(node.test.value, ast.Name)
    }
    assert {"background_tab", "prepare_align_tab", "final_tab"} <= guarded_tabs
