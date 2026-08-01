"""Adversarial contract checks for the TileSetter Set View bridge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from sprite_builder.ui import components

STUDIO_HTML = Path(components.__file__).parent / "terrain_pattern_studio_component" / "index.html"
UI_APP = Path(components.__file__).parent / "app.py"


def test_component_bridge_preserves_complete_v3_blob_and_wang_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_component(**kwargs: Any) -> None:
        captured.update(kwargs)
        return None

    project = {
        "version": 3,
        "sources": [
            {"id": source_id, "x": index * 5, "y": 0, "width": 5, "height": 5}
            for index, source_id in enumerate(
                ("base-a", "base-b", "top", "right", "bottom", "left", "corner")
            )
        ],
        "tiles": [{"id": "tile-a", "sourceId": "base-a", "x": 0, "y": 0}],
        "sets": [
            {
                "id": "blob",
                "kind": "blob_47",
                "baseSource": "base-a",
                "secondarySource": None,
                "edges": {direction: direction for direction in ("top", "right", "bottom", "left")},
                "edgeCutoffs": {"top": 1, "right": 2, "bottom": 3, "left": 4},
                "edgeTransforms": {"right": {"rotation": 1, "flipX": True, "flipY": False}},
                "corners": {"outer_top_left": "corner"},
                "customCorners": {"outer_top_left": True},
                "cornerTransforms": {"outer_top_left": {"rotation": 3, "flipY": True}},
                "compositeCorners": True,
                "overrides": {"0": "corner"},
                "futureField": {"must": "survive"},
            },
            {
                "id": "wang",
                "kind": "wang_16",
                "baseSource": "base-a",
                "secondarySource": "base-b",
                "edges": {direction: direction for direction in ("top", "right", "bottom", "left")},
                "edgeCutoffs": {"left": -2},
            },
        ],
        "activeSetId": "blob",
        "ui": {"selectedTileIds": ["tile-a"], "selectedMask": 0},
        "extensionData": {"roundTrip": True},
    }
    monkeypatch.setattr(components, "_TERRAIN_PATTERN_STUDIO", fake_component)

    components.terrain_pattern_studio(
        Image.new("RGBA", (35, 5)),
        pattern_image=Image.new("RGBA", (60, 20)),
        image_token="v3-roundtrip",
        tile_size=(5, 5),
        kind="blob_47",
        roles=[],
        project=project,
        key="adversarial-v3",
    )

    assert captured["project"] == project
    assert captured["project"]["sets"][0]["futureField"] == {"must": "survive"}
    assert captured["project"]["sets"][1]["secondarySource"] == "base-b"
    assert captured["project"]["sets"][0]["edgeCutoffs"] == {
        "top": 1,
        "right": 2,
        "bottom": 3,
        "left": 4,
    }


def test_studio_contract_requires_one_blob_base_two_wang_bases_and_four_edges() -> None:
    source = STUDIO_HTML.read_text(encoding="utf-8")

    assert 'const tiles=selectedTiles(),required=kind==="wang_16"?2:1' in source
    assert "if(tiles.length!==required)return" in source
    assert '$("#buildBlob").disabled=selectedTiles().length!==1' in source
    assert '$("#buildWang").disabled=selectedTiles().length!==2' in source
    assert 'secondarySource:kind==="wang_16"?tiles[1].sourceId:null' in source
    assert "edges:{top:null,right:null,bottom:null,left:null}" in source
    assert "edgeDirections.every(direction=>Boolean(set.edges?.[direction]))" in source


def test_studio_exposes_directional_cutoff_composite_and_custom_corner_state() -> None:
    source = STUDIO_HTML.read_text(encoding="utf-8")

    for direction in ("top", "right", "bottom", "left"):
        assert direction in source
    assert "set.edgeCutoffs[direction]=Number(event.target.value)||0" in source
    assert "set.edgeCutoffs[direction]=set.cutoff" in source
    assert 'set.kind==="wang_16"?-Math.floor(axis/2):0' in source
    assert 'const features=["outer","inner"].flatMap' in source
    assert "<option value='composite'>Composite</option>" in source
    assert "<option value='custom'>Custom</option>" in source
    assert "set.customCorners?.[feature.key]===true" in source
    assert "delete set.corners[feature.key];delete set.customCorners[feature.key]" in source
    assert "Las esquinas internas y externas se empalman desde los dos bordes" in source


def test_ui_normalization_and_python_ingest_keep_payload_version_three() -> None:
    studio = STUDIO_HTML.read_text(encoding="utf-8")
    app = UI_APP.read_text(encoding="utf-8")

    assert 'const project={...(raw&&typeof raw==="object"?raw:{}),version:3' in studio
    assert "return{...item,kind:" in studio
    assert "edges,edgeTransforms,edgeCutoffs" in studio
    assert "corners:{...(item.corners||{})},customCorners:{...(item.customCorners||{})}" in studio
    assert "overrides:{...(item.overrides||{})}" in studio
    assert 'value:{type:"project-change",project:state.project' in studio
    assert 'if int(project.get("version", 0)) < 3:' in app
    assert 'if int(revised.get("version", 0)) == 3:' in app
    assert '"schema_version": "3.0"' in app
