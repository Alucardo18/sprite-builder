"""Unified orchestrator for multi-format terrain autotile suites (Blob, Dual Grid, Wang)."""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import json
import uuid
import zipfile
from typing import Any, Mapping, Sequence

from PIL import Image

from .color import (
    TerrainPalette,
    get_curated_palette,
    hex_to_rgb,
    normalize_hex_color,
)
from .patterns import (
    TerrainPatternKind,
    TerrainPatternResult,
    build_tiled_bundle,
    build_tilesetter_terrain_pattern,
    build_terrain_pattern_bundle,
    build_unity_ruletile_bundle,
    generate_procedural_material,
    get_aesthetic_preset,
    render_terrain_bitmask_template,
)


@dataclass(frozen=True)
class TerrainSuiteResult:
    """Complete multi-format terrain autotile suite generated from a single palette and recipe."""

    name: str
    tile_size: tuple[int, int]
    primary_color: str
    secondary_color: str
    inside_material: str
    outside_material: str
    preset_id: str
    results_by_kind: dict[str, TerrainPatternResult] = field(default_factory=dict)
    combined_image: Image.Image | None = None
    project_sets: tuple[dict[str, Any], ...] = ()
    sources: tuple[dict[str, Any], ...] = ()
    source_atlas: Image.Image | None = None

    @property
    def blob_result(self) -> TerrainPatternResult | None:
        return self.results_by_kind.get("blob_47")

    @property
    def dual_grid_result(self) -> TerrainPatternResult | None:
        return self.results_by_kind.get("dual_grid_15")

    @property
    def wang_result(self) -> TerrainPatternResult | None:
        return self.results_by_kind.get("wang_16")

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(self.results_by_kind.keys())

    @property
    def sets(self) -> tuple[dict[str, Any], ...]:
        return self.project_sets


def generate_terrain_suite(
    *,
    name: str = "Pradera",
    primary_color: str = "#48A832",
    secondary_color: str = "#8B5A2B",
    inside_material: str = "grass",
    outside_material: str = "dirt",
    preset_id: str = "zelda_topdown",
    kinds: Sequence[TerrainPatternKind] = ("blob_47", "dual_grid_15", "wang_16"),
    tile_size: tuple[int, int] = (16, 16),
    variant_count: int = 3,
    start_y: int = 0,
    seed: int = 0,
    style_overrides: Mapping[str, Any] | None = None,
) -> TerrainSuiteResult:
    """Deterministically synthesize a coordinated multi-format autotile suite.

    Generates Blob 47, Dual Grid 15, and Wang 16 sets simultaneously from the exact
    same chromatic palette and aesthetic recipe, placing each set cleanly without
    overlapping coordinates on the vertical grid axis.
    """
    clean_name = str(name).strip() or "Terreno"
    tw = max(1, int(tile_size[0]))
    th = max(1, int(tile_size[1]))
    size = (tw, th)
    p_col = normalize_hex_color(primary_color, fallback="#48A832")
    s_col = normalize_hex_color(secondary_color, fallback="#8B5A2B")
    v_count = max(1, min(5, int(variant_count)))

    # Synthesize deterministic procedural base and secondary material tiles
    tile_a = generate_procedural_material(size, inside_material, base_color=p_col, seed=seed)
    tile_b = generate_procedural_material(size, outside_material, base_color=s_col, seed=seed + 1)

    transport_atlas = Image.new("RGBA", (tw * 2, th), (0, 0, 0, 0))
    transport_atlas.paste(tile_a, (0, 0))
    transport_atlas.paste(tile_b, (tw, 0))

    src_a_id = f"suite_src_a_{uuid.uuid4().hex[:6]}"
    src_b_id = f"suite_src_b_{uuid.uuid4().hex[:6]}"
    suite_sources = [
        {
            "id": src_a_id,
            "name": f"{clean_name} (Base)",
            "x": 0,
            "y": 0,
            "width": tw,
            "height": th,
            "rect": [0, 0, tw, th],
            "crop": [0, 0, tw, th],
        },
        {
            "id": src_b_id,
            "name": f"{clean_name} (Fondo)",
            "x": tw,
            "y": 0,
            "width": tw,
            "height": th,
            "rect": [tw, 0, tw, th],
            "crop": [tw, 0, tw, th],
        },
    ]

    preset = get_aesthetic_preset(preset_id) or get_aesthetic_preset("zelda_topdown")

    results_by_kind: dict[str, TerrainPatternResult] = {}
    project_sets: list[dict[str, Any]] = []

    current_y = start_y

    kind_labels = {
        "blob_47": "Blob 47 (Orgánico)",
        "dual_grid_15": "Dual Grid 15",
        "wang_16": "Wang 16 (Caminos / Aristas)",
    }

    for kind in kinds:
        set_id = f"set_{kind}_{uuid.uuid4().hex[:6]}"
        is_blob = (kind == "blob_47")
        cols = (11 * v_count) if is_blob else 4
        rows = 5 if is_blob else 4
        row_spacing = 7 if is_blob else 5

        set_data: dict[str, Any] = {
            "id": set_id,
            "name": f"{clean_name} · {kind_labels.get(kind, kind)}",
            "kind": kind,
            "baseSource": src_a_id,
            "secondarySource": src_b_id,
            "blobMaterialMode": "procedural",
            "blobMode": "synthesis",
            "primaryColor": p_col,
            "secondaryColor": s_col,
            "insideColor": p_col,
            "outsideColor": s_col,
            "insideMaterial": inside_material,
            "outsideMaterial": outside_material,
            "primaryMaterial": inside_material,
            "secondaryMaterial": outside_material,
            "originX": 0,
            "originY": current_y,
            "columns": cols,
            "rows": rows,
            "variantCount": v_count if is_blob else 1,
            "edgeSeed": seed,
            "edges": {"top": None, "right": None, "bottom": None, "left": None},
            "edgeTransforms": {
                "top": {"rotation": 0, "flipX": False, "flipY": False},
                "right": {"rotation": 0, "flipX": False, "flipY": False},
                "bottom": {"rotation": 0, "flipX": False, "flipY": False},
                "left": {"rotation": 0, "flipX": False, "flipY": False},
            },
            "corners": {},
            "customCorners": {},
            "cornerTransforms": {},
            "compositeCorners": True,
            "overrides": {},
        }

        if preset is not None:
            set_data = preset.apply_to_set(set_data)

        # Dual Grid from colors strategy: use organic_neutral edge contour
        if kind == "dual_grid_15":
            set_data["terrainProfile"] = "organic_neutral"
            if int(set_data.get("edgeVariation", 0)) == 0:
                set_data["edgeVariation"] = 2

        if style_overrides:
            for k, v in style_overrides.items():
                if v is not None:
                    set_data[k] = v

        pattern_result = build_tilesetter_terrain_pattern(
            transport_atlas,
            tile_size=size,
            sources=suite_sources,
            set_config=set_data,
            kind=kind,
        )

        results_by_kind[kind] = pattern_result
        project_sets.append(set_data)
        current_y += row_spacing

    # Assemble combined collage image for all generated results
    combined_img: Image.Image | None = None
    if results_by_kind:
        max_w = max(res.image.width for res in results_by_kind.values())
        total_h = sum(res.image.height + th for res in results_by_kind.values())
        combined_img = Image.new("RGBA", (max_w, total_h), (0, 0, 0, 0))
        offset_y = 0
        for res in results_by_kind.values():
            combined_img.paste(res.image, (0, offset_y))
            offset_y += res.image.height + th

    return TerrainSuiteResult(
        name=clean_name,
        tile_size=size,
        primary_color=p_col,
        secondary_color=s_col,
        inside_material=inside_material,
        outside_material=outside_material,
        preset_id=preset_id,
        results_by_kind=results_by_kind,
        combined_image=combined_img,
        project_sets=tuple(project_sets),
        sources=tuple(suite_sources),
        source_atlas=transport_atlas,
    )


def build_omnibundle_zip(
    suite: TerrainSuiteResult,
    *,
    bundle_name: str | None = None,
) -> bytes:
    """Package a multi-format suite into a comprehensive Omnibundle ZIP.

    Contains separate subdirectories for each autotile format with their native
    engines (Godot 4, Unity RuleTile, Tiled Map Editor) and palette metadata.
    """
    safe_base = (bundle_name or suite.name).lower().replace(" ", "_") or "terrain_suite"
    archive = io.BytesIO()

    readme_content = f"""# {suite.name} · Omnibundle de Terrenos Autotile
Generado con SpriteBuilder

## Especificaciones Técnicas
- Resolución de Tile: {suite.tile_size[0]}x{suite.tile_size[1]} px
- Color Primario (Relleno): {suite.primary_color} ({suite.inside_material})
- Color Secundario (Fondo): {suite.secondary_color} ({suite.outside_material})
- Receta Estética: {suite.preset_id}

## Formatos Incluidos
"""
    if "blob_47" in suite.results_by_kind:
        blob_res = suite.results_by_kind["blob_47"]
        readme_content += f"""
### 1. `blob_47/`
- Estándar orgánico para mapas 2D (47 combinaciones canónicas con variantes).
- Compatible con Godot 4 (TileMapLayer Terrains), Unity RuleTile y Tiled WangSets.
- {len(blob_res.tiles)} tiles generados ({blob_res.columns}x{blob_res.rows} en atlas).
"""

    if "dual_grid_15" in suite.results_by_kind:
        dual_res = suite.results_by_kind["dual_grid_15"]
        readme_content += f"""
### 2. `dual_grid_15/`
- Rejilla dual compacta de 15 esquinas + celda de fondo (atlas 4x4 de 16 tiles).
- Especialmente optimizado para el plugin `TileMapDual` en Godot 4.
"""

    if "wang_16" in suite.results_by_kind:
        wang_res = suite.results_by_kind["wang_16"]
        readme_content += f"""
### 3. `wang_16/`
- Transiciones ortogonales de 2 aristas (Edge-matching, 16 tiles en atlas 4x4).
- Compatible con Godot 4 (`TERRAIN_MODE_MATCH_SIDES`), Unity RuleTile y Tiled WangSets (`edge`).
- Diseñado para caminos, carreteras, senderos, vías y plataformas con empalmes predecibles en aristas.
"""

    palette_meta = {
        "schema_version": "1.0",
        "kind": "terrain_suite_palette",
        "name": suite.name,
        "tile_size": list(suite.tile_size),
        "primary_color": suite.primary_color,
        "secondary_color": suite.secondary_color,
        "inside_material": suite.inside_material,
        "outside_material": suite.outside_material,
        "preset_id": suite.preset_id,
        "formats_included": list(suite.kinds),
    }

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("README.md", readme_content)
        bundle.writestr("palette.json", json.dumps(palette_meta, indent=2, ensure_ascii=False) + "\n")

        if suite.combined_image is not None:
            comb_io = io.BytesIO()
            suite.combined_image.save(comb_io, format="PNG", optimize=False)
            bundle.writestr("all_terrains_overview.png", comb_io.getvalue())

        for kind, res in suite.results_by_kind.items():
            folder = kind
            # 1. Image and Bitmask Reference
            atlas_io = io.BytesIO()
            res.image.save(atlas_io, format="PNG", optimize=False)
            bundle.writestr(f"{folder}/terrain_tiles.png", atlas_io.getvalue())

            ref_io = io.BytesIO()
            render_terrain_bitmask_template(res.kind).save(ref_io, format="PNG", optimize=False)
            bundle.writestr(f"{folder}/terrain_bitmask_reference.png", ref_io.getvalue())

            # 2. Engine-specific bundles
            godot_zip_bytes = build_terrain_pattern_bundle(res, terrain_name=f"{suite.name}_{kind}")
            bundle.writestr(f"{folder}/godot_installer.zip", godot_zip_bytes)

            unity_zip_bytes = build_unity_ruletile_bundle(res, terrain_name=f"{suite.name}_{kind}")
            bundle.writestr(f"{folder}/unity_ruletile.zip", unity_zip_bytes)

            tiled_zip_bytes = build_tiled_bundle(res, terrain_name=f"{suite.name}_{kind}")
            bundle.writestr(f"{folder}/tiled_wangset.zip", tiled_zip_bytes)

    return archive.getvalue()
