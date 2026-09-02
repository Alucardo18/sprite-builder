"""Adversarial contract checks for the TileSetter Set View bridge."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from sprite_builder.ui import app, components

STUDIO_HTML = Path(components.__file__).parent / "terrain_pattern_studio_component" / "index.html"
UI_APP = Path(components.__file__).parent / "app.py"
README_UI = Path(__file__).resolve().parents[1] / "README_UI.md"
GODOT_EXPORT_DOC = Path(__file__).resolve().parents[1] / "docs" / "godot-export.md"
DUAL_EDGE_PROFILE_DOC = Path(__file__).resolve().parents[1] / "docs" / "dual-grid-edge-profiles.md"
PATTERNS = (
    Path(__file__).resolve().parents[1] / "src" / "sprite_builder" / "tilesets" / "patterns.py"
)


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


def test_studio_contract_scopes_border_sources_to_blob_and_wang() -> None:
    source = STUDIO_HTML.read_text(encoding="utf-8")

    assert "const tiles=selectedTiles(),required=baseRequirement(kind);" in source
    assert "function baseRequirement(kind){return requiresTwoBases(kind)?2:1}" in source
    assert "if(tiles.length!==required)return" in source
    assert '$("#buildBlob").disabled=selectedTiles().length!==1' in source
    assert '$("#buildWang").disabled=selectedTiles().length!==2' in source
    assert (
        '$("#buildDual").disabled=selectedTiles().length!==2||!dualGridTileSizeValid()'
    ) in source
    assert "secondarySource:requiresTwoBases(kind)?tiles[1].sourceId:null" in source
    assert "edges:{top:null,right:null,bottom:null,left:null}" in source
    assert "edgeDirections.every(direction=>Boolean(set.edges?.[direction]))" in source
    assert "function requiresEdges(set){return !isDualGrid(set)}" in source


def test_component_bridge_preserves_dual_grid_project_and_atlas_metadata(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_component(**kwargs: Any) -> None:
        captured.update(kwargs)
        return None

    roles = [
        {
            "index": mask,
            "mask": mask,
            "neighbors": [],
            "previewColumn": mask % 4,
            "previewRow": mask // 4,
            "setColumn": mask % 4,
            "setRow": mask // 4,
        }
        for mask in range(16)
    ]
    project = {
        "version": 3,
        "sources": [
            {"id": "terrain-a", "x": 0, "y": 0, "width": 8, "height": 8},
            {"id": "terrain-b", "x": 8, "y": 0, "width": 8, "height": 8},
        ],
        "tiles": [
            {"id": "tile-a", "sourceId": "terrain-a", "x": 0, "y": 0},
            {"id": "tile-b", "sourceId": "terrain-b", "x": 1, "y": 0},
        ],
        "sets": [
            {
                "id": "dual",
                "kind": "dual_grid_15",
                "baseSource": "terrain-a",
                "secondarySource": "terrain-b",
                "terrainProfile": "dirt_over_water",
                "edgeVariation": 2,
                "edgeSeed": 314,
                "futureDualMetadata": {"logical_grid": "terrain_cells"},
            }
        ],
        "activeSetId": "dual",
    }
    monkeypatch.setattr(components, "_TERRAIN_PATTERN_STUDIO", fake_component)

    components.terrain_pattern_studio(
        Image.new("RGBA", (16, 8)),
        pattern_image=Image.new("RGBA", (32, 32)),
        image_token="dual-grid-atlas",
        tile_size=(8, 8),
        kind="dual_grid_15",
        roles=roles,
        project=project,
        set_previews=[
            {
                "id": "dual",
                "kind": "dual_grid_15",
                "image": Image.new("RGBA", (32, 32)),
                "roles": roles,
            }
        ],
        key="dual-grid-contract",
    )

    assert captured["kind"] == "dual_grid_15"
    assert [role["mask"] for role in captured["roles"]] == list(range(16))
    assert captured["project"] == project
    assert captured["project"]["sets"][0]["futureDualMetadata"] == {"logical_grid": "terrain_cells"}
    assert captured["setPreviews"][0]["kind"] == "dual_grid_15"
    assert captured["setPreviews"][0]["image"].startswith("data:image/png;base64,")


def test_dual_grid_studio_contract_has_15_roles_and_a_runtime_background_slot() -> None:
    source = STUDIO_HTML.read_text(encoding="utf-8")
    app = UI_APP.read_text(encoding="utf-8")

    for control in (
        'id="buildDual"',
        'id="contextDual"',
        'id="buildDualInspector"',
        "Build Dual Grid · 15",
        "Dual Grid 15",
        "Selecciona exactamente 2 tiles base completos.",
    ):
        assert control in source
    assert 'const PATTERN_KINDS=["blob_47","wang_16","sides_16","dual_grid_15"]' in source
    assert "const DUAL_GRID_TRANSITION_MASKS=Array.from({length:15},(_,index)=>index+1)" in source
    assert 'const DUAL_GRID_NEIGHBOR_ORDER=["NW","NE","SE","SW"]' in source
    assert (
        'function variantCount(kind){return kind==="blob_47"?47:kind==="dual_grid_15"?15:16}'
        in source
    )
    assert (
        'function requiresTwoBases(kind){return kind==="wang_16"||kind==="dual_grid_15"}' in source
    )
    assert "const neighboringCells=[[x-1,y-1],[x,y-1],[x,y],[x-1,y]]" in source
    assert "if(mask===0)return state.roles.find(role=>Number(role.mask)===0)||null;" in source
    assert "state.roles.find(role=>dualGridRole(role)&&Number(role.mask)===mask)||null" in source
    assert (
        "function sandboxDisplayWidth(set){return state.mapWidth+(isDualGrid(set)?1:0)}"
    ) in source
    assert (
        "function sandboxDisplayHeight(set){return state.mapHeight+(isDualGrid(set)?1:0)}"
    ) in source
    assert (
        "const set=activeSet(),displayWidth=sandboxDisplayWidth(set),"
        "displayHeight=sandboxDisplayHeight(set);"
    ) in source
    assert "logicalOffset=isDualGrid(activeSet())?.5:0" in source
    assert '"Dual Grid · fondo lógico (mask 0)"' in source
    assert (
        '_UI_PATTERN_KINDS = frozenset({"blob_47", "wang_16", "sides_16", "dual_grid_15"})' in app
    )
    assert '"dual_grid_15"' in app
    assert "item_result, item_error = _build_terrain_pattern_safely(" in app
    assert "kind=item_kind," in app
    assert "set_layout = terrain_pattern_set_layout(cast(TerrainPatternKind, item_kind))" in app
    assert "result, active_set_error = _build_terrain_pattern_safely(" in app
    assert "kind=kind," in app
    assert "active_layout = terrain_pattern_set_layout(cast(TerrainPatternKind, kind))" in app
    assert (
        "render_terrain_bitmask_template(\n                        cast(TerrainPatternKind, kind)"
        in app
    )
    assert 'render_terrain_bitmask_template("wang_16"' not in app
    assert 'kind="wang_16"' not in app
    assert "_build_ui_terrain_pattern" not in app
    assert "_render_ui_bitmask_template" not in app
    assert "_DUAL_GRID_SET_LAYOUT" not in app
    assert "_ui_pattern_layout" not in app
    assert "from dataclasses import replace" not in app


def test_app_exposes_dual_grid_background_slot_without_counting_a_transition() -> None:
    transition = SimpleNamespace(
        index=0,
        mask=1,
        neighbors=("top_left",),
        column=3,
        row=3,
        generated=True,
        source_index=0,
    )

    roles = app._terrain_pattern_studio_roles(
        SimpleNamespace(tiles=(transition,)),
        set_positions={1: (3, 3)},
        kind="dual_grid_15",
    )
    legacy_roles = app._terrain_pattern_studio_roles(
        SimpleNamespace(tiles=(transition,)),
        set_positions={1: (3, 3)},
        kind="wang_16",
    )

    assert [(role["mask"], role["setColumn"], role["setRow"]) for role in roles] == [
        (0, 0, 3),
        (1, 3, 3),
    ]
    assert roles[0]["runtimeRole"] == "background"
    assert [role["mask"] for role in legacy_roles] == [1]


def test_dual_grid_project_normalization_keeps_only_two_terrain_inputs() -> None:
    project = {
        "version": 3,
        "futureProjectMetadata": {"keep": True},
        "sets": [
            {
                "id": "dual",
                "kind": "dual_grid_15",
                "baseSource": "terrain-a",
                "secondarySource": "terrain-b",
                "terrainProfile": "dirt_over_water",
                "edgeVariation": 2,
                "edgeSeed": 314,
                "overrides": {"0": "forbidden", "7": "allowed"},
                "autoOrientEdges": True,
                "edges": {"top": "old-border"},
                "edgeTransforms": {"top": {"rotation": 1}},
                "edgeCutoffs": {"top": 2},
                "cutoff": 2,
                "corners": {"outer_top_left": "old-corner"},
                "customCorners": {"outer_top_left": True},
                "cornerTransforms": {"outer_top_left": {"rotation": 1}},
                "compositeCorners": True,
                "futureSetMetadata": {"keep": True},
            },
            {
                "id": "wang",
                "kind": "wang_16",
                "overrides": {"0": "wang-override"},
            },
        ],
    }

    normalized = app._strip_dual_grid_background_overrides(project)
    dual = normalized["sets"][0]

    assert project["sets"][0]["overrides"]["0"] == "forbidden"
    assert dual["baseSource"] == "terrain-a"
    assert dual["secondarySource"] == "terrain-b"
    assert dual["terrainProfile"] == "dirt_over_water"
    assert dual["edgeVariation"] == 2
    assert dual["edgeSeed"] == 314
    assert dual["overrides"] == {"7": "allowed"}
    assert dual["futureSetMetadata"] == {"keep": True}
    assert normalized["futureProjectMetadata"] == {"keep": True}
    for field in (
        "autoOrientEdges",
        "edges",
        "edgeTransforms",
        "edgeCutoffs",
        "cutoff",
        "corners",
        "customCorners",
        "cornerTransforms",
        "compositeCorners",
    ):
        assert field not in dual
    assert normalized["sets"][1] == project["sets"][1]


def test_dual_grid_background_reference_cannot_be_overridden_in_the_component() -> None:
    source = STUDIO_HTML.read_text(encoding="utf-8")

    assert 'if(kind==="dual_grid_15"){delete overrides["0"]' in source
    assert (
        "function dualGridBackgroundReference(set,mask){return isDualGrid(set)&&Number(mask)===0}"
    ) in source
    assert 'type==="override"&&dualGridBackgroundReference(set,key)' in source
    assert (
        'assignment.type==="override"&&!dualGridBackgroundReference(set,assignment.key)'
    ) in source
    assert '$("#variantOverrideSection").hidden=!role||backgroundReference' in source
    assert "dualGridBackgroundReference(set,role.mask))return;" in source
    assert "se deriva exclusivamente de Terreno B" in source


def test_dual_grid_material_pair_selector_has_bounded_deterministic_variation() -> None:
    source = STUDIO_HTML.read_text(encoding="utf-8")

    for control in (
        'id="dualProfileSection"',
        'id="dualTerrainProfile"',
        'value="grass_over_dirt">Pasto sobre tierra',
        'value="dirt_over_water">Tierra sobre agua',
        'value="grass_over_water">Pasto sobre agua',
        'id="dualEdgeVariation" type="range" min="0" max="3"',
        'id="dualEdgeSeed" type="number" min="0" max="999999"',
        'id="shuffleDualEdgeSeed"',
    ):
        assert control in source
    assert 'const DUAL_GRID_TERRAIN_PROFILES=["clean","grass_over_dirt",' in source
    assert "edgeVariation:clampInteger(item.edgeVariation,0,3,0)" in source
    assert "edgeSeed:clampInteger(item.edgeSeed,0,999999,0)" in source
    assert (
        'Object.assign(set,{terrainProfile:"grass_over_dirt",edgeVariation:1,edgeSeed:0})' in source
    )
    assert '$("#dualProfileSection").hidden=!isDualGrid(set)' in source
    assert (
        '$("#dualProfileCopy").textContent=`Aplicado · '
        "${DUAL_GRID_PROFILE_LABELS[profile]}" in source
    )
    assert "function dualProfileStatus(set)" in source
    assert "`Dual Grid listo · ${dualProfileStatus(set)}`" in source
    assert "Detalle del borde" in source
    assert "bandas duras de 1–4 px" in source
    assert "Sombra acuática, ribete claro y banco terroso irregular" in source


def test_degenerate_dual_grid_project_is_skipped_without_losing_it() -> None:
    project = {
        "version": 3,
        "sets": [
            {
                "id": "invalid-dual",
                "kind": "dual_grid_15",
                "baseSource": "terrain-a",
                "secondarySource": "terrain-b",
            }
        ],
        "activeSetId": "invalid-dual",
    }
    sources = [
        {"id": "terrain-a", "x": 0, "y": 0, "width": 2, "height": 2},
        {"id": "terrain-b", "x": 0, "y": 0, "width": 2, "height": 2},
    ]

    normalized = app._strip_dual_grid_background_overrides(project)
    assert normalized == project
    for tile_size in ((1, 2), (2, 1)):
        result, error = app._build_terrain_pattern_safely(
            Image.new("RGBA", (2, 2)),
            tile_size=tile_size,
            sources=sources,
            set_config=normalized["sets"][0],
            kind="dual_grid_15",
        )

        assert result is None
        assert error == "Dual Grid requiere tiles de al menos 2×2 px (ancho y alto)."

    app_source = UI_APP.read_text(encoding="utf-8")
    assert "invalid_set_errors: dict[str, str] = {}" in app_source
    assert "pattern_image=result.image if result is not None else image" in app_source
    assert "st.error(error)" in app_source


def test_set_view_project_import_restores_valid_square_tile_size_atomically() -> None:
    project_key = "tileset_builder:patterns:set_view_project"
    upload_digest_key = "tileset_builder:patterns:project_upload_sha256"
    session_state: dict[str, Any] = {
        project_key: {"version": 3, "sets": [{"id": "old"}]},
        "tileset_builder:tile_size": 1,
        "tileset_builder:offset_x": 5,
        "tileset_builder:offset_y": 6,
        "tileset_builder:spacing_x": 2,
        "tileset_builder:spacing_y": 3,
    }
    saved_project = {
        "kind": "tilesetter_set_project",
        "atlas_sha256": "atlas-digest",
        "tile_size": [8, 8],
        "studio": {
            "version": 3,
            "sets": [{"id": "dual", "kind": "dual_grid_15"}],
        },
    }

    assert app._validated_tilesetter_project_tile_size((8, 8)) == 8

    app._restore_tilesetter_project_import(
        session_state,
        incoming_project=saved_project,
        atlas_sha256="atlas-digest",
        project_key=project_key,
        upload_digest_key=upload_digest_key,
        upload_sha256="project-digest",
    )

    assert session_state[project_key] == saved_project["studio"]
    assert session_state["tileset_builder:tile_size"] == 8
    assert session_state[upload_digest_key] == "project-digest"
    assert session_state["tileset_builder:offset_x"] == 5
    assert session_state["tileset_builder:offset_y"] == 6
    assert session_state["tileset_builder:spacing_x"] == 2
    assert session_state["tileset_builder:spacing_y"] == 3

    state_after_first_restore = dict(session_state)
    assert not app._tilesetter_project_upload_is_new(
        session_state,
        upload_digest_key=upload_digest_key,
        upload_sha256="project-digest",
    )
    assert session_state == state_after_first_restore


@pytest.mark.parametrize(
    "tile_size",
    (None, [8], [8, "8"], [0, 0], [129, 129], [8, 16], [True, True]),
)
def test_set_view_project_import_rejects_invalid_tile_size_without_mutation(
    tile_size: object,
) -> None:
    project_key = "tileset_builder:patterns:set_view_project"
    upload_digest_key = "tileset_builder:patterns:project_upload_sha256"
    session_state: dict[str, Any] = {
        project_key: {"version": 3, "sets": [{"id": "current"}]},
        "tileset_builder:tile_size": 16,
        upload_digest_key: "previous-digest",
    }
    before = dict(session_state)
    malformed_project = {
        "kind": "tilesetter_set_project",
        "atlas_sha256": "atlas-digest",
        "tile_size": tile_size,
        "studio": {"version": 3, "sets": []},
    }

    with pytest.raises(ValueError, match="tile_size"):
        app._restore_tilesetter_project_import(
            session_state,
            incoming_project=malformed_project,
            atlas_sha256="atlas-digest",
            project_key=project_key,
            upload_digest_key=upload_digest_key,
            upload_sha256="bad-project-digest",
        )

    assert session_state == before


def test_set_view_import_caller_and_restore_share_the_scoped_digest_key() -> None:
    source = UI_APP.read_text(encoding="utf-8")

    assert 'upload_digest_key = f"{prefix}:project_upload_sha256"' in source
    assert "upload_digest_key=upload_digest_key," in source
    assert "session_state[upload_digest_key] = upload_sha256" in source


def test_component_blocks_dual_grid_for_any_sub_two_pixel_axis() -> None:
    source = STUDIO_HTML.read_text(encoding="utf-8")

    assert (
        "function dualGridTileSizeValid(){return state.tileWidth>=2&&state.tileHeight>=2}"
    ) in source
    assert (
        'function dualGridTileSizeMessage(){return "Dual Grid requiere tiles '
        'de al menos 2×2 px (ancho y alto)."}'
    ) in source
    assert '$("#buildDual").disabled=selectedTiles().length!==2||!dualGridTileSizeValid()' in source
    assert '$("#buildDualInspector").disabled=!dualGridTileSizeValid()' in source
    assert (
        '$("#contextDual").disabled=selectedTiles().length!==2||!dualGridTileSizeValid()'
    ) in source
    assert 'if(kind==="dual_grid_15"&&!dualGridTileSizeValid())' in source


def test_dual_grid_needs_two_terrains_not_four_border_sources() -> None:
    source = STUDIO_HTML.read_text(encoding="utf-8")
    app = UI_APP.read_text(encoding="utf-8")

    assert "function requiresEdges(set){return !isDualGrid(set)}" in source
    assert 'const showEdges=requiresEdges(set);$("#edgeSection").hidden=!showEdges;' in source
    assert (
        '"Dual Grid cuadrado genera 15 transiciones con Terreno A y Terreno B. '
        'Los Border Sources no son necesarios."'
    ) in source
    assert (
        "(!requiresEdges(set)||edgeDirections.every(direction=>Boolean(set.edges?.[direction])) )"
    ) in source
    assert "`Dual Grid listo · ${dualProfileStatus(set)}`" in source
    assert '"Grid requiere exactamente dos terrenos y no necesita Border "' in app
    assert '"terrenos y su fondo lógico están listos para exportar. El "' in app


def test_dual_grid_documentation_distinguishes_atlas_from_runtime() -> None:
    readme = README_UI.read_text(encoding="utf-8")
    godot_export = GODOT_EXPORT_DOC.read_text(encoding="utf-8")
    profile_doc = DUAL_EDGE_PROFILE_DOC.read_text(encoding="utf-8")
    godot_export_one_line = " ".join(godot_export.split())

    assert "15 transiciones desde ambas texturas" in readme
    assert "TileMapDual" in readme
    assert "cuadrícula **Square** de cuatro esquinas" in readme
    assert "Para **Blob/Wang**, configure **Tile Properties**" in readme
    assert "Dual Grid sólo expone Terreno A y Terreno B." in readme
    assert "Custom corners son exclusivos de Blob" in readme
    assert "Tile Size** cuadrado de 1 a 64 px" in readme
    assert "bounds absolutos en píxeles" in readme
    assert "El export traduce ese orden al contrato de" in " ".join(readme.split())
    assert "No instala ni reemplaza ese plugin/nodo." in " ".join(readme.split())
    assert "**Pasto sobre tierra**" in readme
    assert "**Tierra sobre agua**" in readme
    assert "**Pasto sobre agua**" in readme
    assert "no convierte un `TileMapLayer` nativo en un runtime dual-grid" in godot_export_one_line
    assert (
        "sprite-builder no lo incluye en el ZIP ni genera su nodo runtime" in godot_export_one_line
    )
    assert "orden de peers NW, NE, SW, SE" in godot_export_one_line
    assert "El perfil Dual Grid exportado aquí es únicamente **Square**" in godot_export
    assert "topologías isométricas, hexagonales y triangulares" in godot_export_one_line
    assert "En Blob y Wang, Tile Properties muestra el tile base" in godot_export
    assert "Dual Grid sólo mantiene Terreno A, Terreno B" in godot_export_one_line
    assert "Custom corners son overrides opcionales exclusivos de Blob" in godot_export_one_line
    assert "No llame `set_cells_terrain_connect()` como sustituto" in godot_export_one_line
    assert (
        "los cuatro peering bits de cada una de sus 16 celdas físicas siempre "
        "son `0` o `1`" in godot_export_one_line
    )
    assert "sólo `tile_data.terrain` vale `-1` para las transiciones 1–14" in godot_export_one_line
    assert "### Perfiles de borde Dual Grid" in godot_export
    assert "`terrain_profile`" in godot_export
    assert "LPC Terrains" in profile_doc
    assert "Grassy Top-down Tileset" in profile_doc
    assert "South Hyrule Field" in profile_doc
    assert "Descomposición de la referencia aportada" in profile_doc
    assert "1–2 px de sombra turquesa" in profile_doc
    assert "3–5 px de banco terroso" in profile_doc
    assert "deterministic_palette_bands" in PATTERNS.read_text(encoding="utf-8")
    assert "no se incorpora ni se redistribuye arte" in profile_doc


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
    assert "return{...item,kind," in studio
    assert "edges,edgeTransforms,edgeCutoffs" in studio
    assert "corners:{...(item.corners||{})},customCorners:{...(item.customCorners||{})}" in studio
    assert (
        'const kind=PATTERN_KINDS.includes(item.kind)?item.kind:"blob_47",'
        "overrides={...(item.overrides||{})};"
    ) in studio
    assert 'if int(project.get("version", 0)) < 3:' in app
    assert 'if int(revised.get("version", 0)) == 3:' in app
    assert '"schema_version": "3.0"' in app


def test_studio_component_supports_rounded_profiles_and_source_bounds() -> None:
    studio = STUDIO_HTML.read_text(encoding="utf-8")

    assert '"rounded_clean"' in studio
    assert '"rounded_grass_tufts"' in studio
    assert '"rounded_dither"' in studio
    assert "source.x!==undefined?source.x:(Array.isArray(source.rect)" in studio
    assert "const sb=sourceBounds(source);copy.querySelector(\"span\").textContent=" in studio

