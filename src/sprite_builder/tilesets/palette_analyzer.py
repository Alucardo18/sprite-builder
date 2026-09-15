"""Intelligent chromatic biome analyzer and multi-blob ecosystem generator.

Analyzes input reference images in HSV color space to extract representative
color palettes for biomes (grass, dirt, water, sand, stone) and automatically
generates a coordinated ecosystem of autotile sets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import uuid
from typing import Any, Mapping

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class TerrainColor:
    """Representative color profile for a single terrain layer."""

    name: str
    hex_color: str
    rgb: tuple[int, int, int]
    highlight_hex: str
    shadow_hex: str
    pixel_count: int = 0
    detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HarvestedTileSample:
    """A tile harvested directly from a reference image."""

    terrain: str
    bounds: tuple[int, int, int, int]  # (x, y, width, height)
    image: Image.Image
    purity: float
    texture_variance: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "terrain": self.terrain,
            "bounds": list(self.bounds),
            "purity": round(float(self.purity), 3),
            "texture_variance": round(float(self.texture_variance), 3),
        }


@dataclass(frozen=True)
class BiomePalette:
    """Full extracted or synthesized chromatic palette for a multi-terrain biome."""

    grass: TerrainColor
    dirt: TerrainColor
    water: TerrainColor
    sand: TerrainColor
    stone: TerrainColor
    dominant_terrain: str
    detected_terrains: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "grass": self.grass.to_dict(),
            "dirt": self.dirt.to_dict(),
            "water": self.water.to_dict(),
            "sand": self.sand.to_dict(),
            "stone": self.stone.to_dict(),
            "dominant_terrain": self.dominant_terrain,
            "detected_terrains": list(self.detected_terrains),
        }


_DEFAULT_TERRAIN_COLORS: dict[str, tuple[int, int, int]] = {
    "grass": (82, 135, 104),  # #528768
    "dirt": (123, 115, 95),   # #7b735f
    "water": (45, 104, 123),  # #2d687b
    "sand": (198, 168, 112),  # #c6a870
    "stone": (118, 122, 130), # #767a82
}


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(channel))) for channel in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _make_tint(rgb: tuple[int, int, int], factor: float) -> str:
    r, g, b = rgb
    return _rgb_to_hex((
        max(0, min(255, round(r * factor))),
        max(0, min(255, round(g * factor))),
        max(0, min(255, round(b * factor))),
    ))


def _build_terrain_color(
    name: str,
    rgb: tuple[int, int, int],
    pixel_count: int = 0,
    detected: bool = False,
) -> TerrainColor:
    hex_color = _rgb_to_hex(rgb)
    highlight_hex = _make_tint(rgb, 1.25)
    shadow_hex = _make_tint(rgb, 0.70)
    return TerrainColor(
        name=name,
        hex_color=hex_color,
        rgb=rgb,
        highlight_hex=highlight_hex,
        shadow_hex=shadow_hex,
        pixel_count=pixel_count,
        detected=detected,
    )


def analyze_image_biome_palette(image: Image.Image) -> BiomePalette:
    """Analyze a reference image in HSV space to extract grass, dirt, water, sand, and stone.

    If certain terrains are absent in the image, harmonic complementary fallbacks
    are synthesized to ensure a complete, playable 3-tier biome ecosystem.
    """
    rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
    opaque_mask = rgba[..., 3] >= 64
    if not np.any(opaque_mask):
        return _fallback_biome_palette()

    rgb = rgba[opaque_mask, :3]
    total_opaque = rgb.shape[0]

    r = rgb[:, 0].astype(np.float32) / 255.0
    g = rgb[:, 1].astype(np.float32) / 255.0
    b = rgb[:, 2].astype(np.float32) / 255.0

    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin

    # Calculate Hue [0, 360)
    h = np.zeros_like(r)
    mask_r = (delta > 1e-5) & (cmax == r)
    mask_g = (delta > 1e-5) & (cmax == g)
    mask_b = (delta > 1e-5) & (cmax == b)

    h[mask_r] = ((g[mask_r] - b[mask_r]) / delta[mask_r]) % 6.0
    h[mask_g] = ((b[mask_g] - r[mask_g]) / delta[mask_g]) + 2.0
    h[mask_b] = ((r[mask_b] - g[mask_b]) / delta[mask_b]) + 4.0
    h = h * 60.0

    # Saturation [0, 1]
    s = np.zeros_like(r)
    nz = cmax > 1e-5
    s[nz] = delta[nz] / cmax[nz]

    # Value [0, 1]
    v = cmax

    # Classification filters
    is_grass = (h >= 65.0) & (h <= 165.0) & (s >= 0.15) & (v >= 0.15)
    is_water = (h >= 170.0) & (h <= 260.0) & (s >= 0.15) & (v >= 0.15)
    is_sand = (h >= 30.0) & (h <= 55.0) & (s >= 0.12) & (s <= 0.65) & (v >= 0.65)
    is_dirt = (h >= 15.0) & (h <= 50.0) & (s >= 0.18) & (v >= 0.12) & (v < 0.65)
    is_stone = (s < 0.16) & (v >= 0.18) & (v <= 0.85)

    masks: dict[str, np.ndarray] = {
        "grass": is_grass,
        "dirt": is_dirt,
        "water": is_water,
        "sand": is_sand,
        "stone": is_stone,
    }

    colors: dict[str, TerrainColor] = {}
    detected_list: list[str] = []
    min_pixels = max(4, int(total_opaque * 0.005))

    for key, mask in masks.items():
        count = int(np.count_nonzero(mask))
        if count >= min_pixels:
            matched_rgb = rgb[mask]
            median_color = tuple(int(round(float(c))) for c in np.median(matched_rgb, axis=0))
            colors[key] = _build_terrain_color(key, median_color, pixel_count=count, detected=True)
            detected_list.append(key)

    # Stylized / Monochromatic fallback if standard hues were not detected
    if not any(k in colors for k in ("grass", "dirt", "water")):
        # Sort all pixels by luminance to create 3 high-contrast harmonized tiers
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        sorted_indices = np.argsort(luma)
        n = len(sorted_indices)
        cut1 = max(1, n // 3)
        cut2 = max(cut1 + 1, min(n - 1, 2 * n // 3))

        idx_low = sorted_indices[:cut1]
        idx_mid = sorted_indices[cut1:cut2]
        idx_high = sorted_indices[cut2:]
        if len(idx_high) == 0:
            idx_high = sorted_indices[-1:]
        if len(idx_mid) == 0:
            idx_mid = idx_high

        high_rgb = tuple(int(round(float(c))) for c in np.median(rgb[idx_high], axis=0))
        mid_rgb = tuple(int(round(float(c))) for c in np.median(rgb[idx_mid], axis=0))
        low_rgb = tuple(int(round(float(c))) for c in np.median(rgb[idx_low], axis=0))

        colors["grass"] = _build_terrain_color("grass", high_rgb, pixel_count=len(idx_high), detected=True)
        colors["dirt"] = _build_terrain_color("dirt", mid_rgb, pixel_count=len(idx_mid), detected=True)
        colors["water"] = _build_terrain_color("water", low_rgb, pixel_count=len(idx_low), detected=True)
        detected_list.extend(["grass", "dirt", "water"])

    # Provide pleasing defaults for any missing terrain
    for key, default_rgb in _DEFAULT_TERRAIN_COLORS.items():
        if key not in colors:
            colors[key] = _build_terrain_color(key, default_rgb, pixel_count=0, detected=False)

    dominant = max(colors.keys(), key=lambda k: colors[k].pixel_count) if detected_list else "grass"

    return BiomePalette(
        grass=colors["grass"],
        dirt=colors["dirt"],
        water=colors["water"],
        sand=colors["sand"],
        stone=colors["stone"],
        dominant_terrain=dominant,
        detected_terrains=tuple(detected_list),
    )


def _fallback_biome_palette() -> BiomePalette:
    """Default fallback palette when no image data is available."""
    colors = {
        key: _build_terrain_color(key, rgb, pixel_count=0, detected=False)
        for key, rgb in _DEFAULT_TERRAIN_COLORS.items()
    }
    return BiomePalette(
        grass=colors["grass"],
        dirt=colors["dirt"],
        water=colors["water"],
        sand=colors["sand"],
        stone=colors["stone"],
        dominant_terrain="grass",
        detected_terrains=(),
    )


def harvest_image_terrain_tiles(
    image: Image.Image,
    tile_size: tuple[int, int] = (16, 16),
    *,
    palette: BiomePalette | None = None,
    max_samples_per_biome: int = 5,
    min_purity: float = 0.70,
) -> dict[str, list[HarvestedTileSample]]:
    """Scan a reference image on tile_size grid to extract the purest terrain patches."""
    rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
    img_h, img_w, _ = rgba.shape
    tile_w, tile_h = tile_size
    cols = img_w // tile_w
    rows = img_h // tile_h

    if cols <= 0 or rows <= 0:
        return {}

    candidates: dict[str, list[HarvestedTileSample]] = {
        "grass": [],
        "dirt": [],
        "water": [],
        "sand": [],
        "stone": [],
    }

    for row in range(rows):
        for col in range(cols):
            x = col * tile_w
            y = row * tile_h
            cell = rgba[y : y + tile_h, x : x + tile_w]
            opaque = cell[..., 3] >= 64
            opaque_count = int(np.count_nonzero(opaque))
            total_cell = tile_w * tile_h
            if opaque_count < total_cell * 0.85:
                continue

            r = cell[opaque, 0].astype(np.float32) / 255.0
            g = cell[opaque, 1].astype(np.float32) / 255.0
            b = cell[opaque, 2].astype(np.float32) / 255.0

            cmax = np.maximum(np.maximum(r, g), b)
            cmin = np.minimum(np.minimum(r, g), b)
            delta = cmax - cmin

            h = np.zeros_like(r)
            mask_r = (delta > 1e-5) & (cmax == r)
            mask_g = (delta > 1e-5) & (cmax == g)
            mask_b = (delta > 1e-5) & (cmax == b)

            h[mask_r] = ((g[mask_r] - b[mask_r]) / delta[mask_r]) % 6.0
            h[mask_g] = ((b[mask_g] - r[mask_g]) / delta[mask_g]) + 2.0
            h[mask_b] = ((r[mask_b] - g[mask_b]) / delta[mask_b]) + 4.0
            h = h * 60.0

            s = np.zeros_like(r)
            nz = cmax > 1e-5
            s[nz] = delta[nz] / cmax[nz]
            v = cmax

            is_grass = (h >= 65.0) & (h <= 165.0) & (s >= 0.15) & (v >= 0.15)
            is_water = (h >= 170.0) & (h <= 260.0) & (s >= 0.15) & (v >= 0.15)
            is_sand = (h >= 30.0) & (h <= 55.0) & (s >= 0.12) & (s <= 0.65) & (v >= 0.65)
            is_dirt = (h >= 15.0) & (h <= 50.0) & (s >= 0.18) & (v >= 0.12) & (v < 0.65)
            is_stone = (s < 0.16) & (v >= 0.18) & (v <= 0.85)

            counts = {
                "grass": int(np.count_nonzero(is_grass)),
                "dirt": int(np.count_nonzero(is_dirt)),
                "water": int(np.count_nonzero(is_water)),
                "sand": int(np.count_nonzero(is_sand)),
                "stone": int(np.count_nonzero(is_stone)),
            }

            best_biome = max(counts.keys(), key=lambda k: counts[k])
            purity = counts[best_biome] / float(opaque_count)

            if purity >= min_purity:
                luma = 0.299 * r + 0.587 * g + 0.114 * b
                variance = float(np.std(luma))
                cropped = image.crop((x, y, x + tile_w, y + tile_h))
                sample = HarvestedTileSample(
                    terrain=best_biome,
                    bounds=(x, y, tile_w, tile_h),
                    image=cropped,
                    purity=purity,
                    texture_variance=variance,
                )
                candidates[best_biome].append(sample)

    results: dict[str, list[HarvestedTileSample]] = {}
    for key, items in candidates.items():
        if not items:
            continue
        sorted_items = sorted(
            items,
            key=lambda it: (it.purity * 0.70 + min(it.texture_variance * 3.0, 0.30)),
            reverse=True,
        )
        results[key] = sorted_items[:max_samples_per_biome]

    return results


def generate_biome_ecosystem_sets(
    palette: BiomePalette | Mapping[str, Any],
    *,
    kind: str = "blob_47",
    style_config: Mapping[str, Any] | None = None,
    start_y: int = 0,
    variant_count: int = 3,
    harvested_tiles: Mapping[str, Sequence[HarvestedTileSample]] | None = None,
    source_id_map: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Generate 3 fully coordinated autotile sets for a complete terrain ecosystem.

    The 3 generated sets are:
    1. Pasto sobre Tierra (grass over dirt)
    2. Tierra sobre Agua (dirt over water)
    3. Pasto sobre Agua (grass over water)

    Each set is assigned a non-overlapping originY on the grid.
    """
    if isinstance(palette, BiomePalette):
        pal_dict = palette.to_dict()
    else:
        pal_dict = dict(palette)

    grass_col = pal_dict.get("grass", {}).get("hex_color", "#528768")
    dirt_col = pal_dict.get("dirt", {}).get("hex_color", "#7b735f")
    water_col = pal_dict.get("water", {}).get("hex_color", "#2d687b")

    cfg = dict(style_config or {})
    corner_style = str(cfg.get("cornerStyle") or cfg.get("corner_style") or "chamfer")
    shadow_tint = str(cfg.get("shadowTint") or cfg.get("shadow_tint") or "cool")
    drop_shadow = int(cfg.get("dropShadow") if cfg.get("dropShadow") is not None else cfg.get("drop_shadow", 2))
    shadow_dir = str(cfg.get("shadowDirection") or cfg.get("shadow_direction") or "south")
    shadow_intensity = float(cfg.get("shadowIntensity") if cfg.get("shadowIntensity") is not None else cfg.get("shadow_intensity", 0.70))
    rim_light = bool(cfg.get("rimLight") if "rimLight" in cfg else cfg.get("rim_light", True))
    edge_variation = int(cfg.get("edgeVariation") if cfg.get("edgeVariation") is not None else cfg.get("edge_variation", 2))
    v_count = max(1, min(5, int(variant_count)))

    # Set layout geometry
    if kind == "blob_47":
        cols, rows, row_spacing = 11, 5, 7
    elif kind == "dual_grid_15":
        cols, rows, row_spacing = 4, 4, 5
    else:
        cols, rows, row_spacing = 4, 4, 5

    tiers = [
        {
            "id": f"ecosystem_grass_dirt_{uuid.uuid4().hex[:8]}",
            "name": "Pasto sobre Tierra (Ecosistema)",
            "profile": "grass_over_dirt",
            "edge_profile": "rounded_grass_tufts",
            "inside_material": "grass",
            "outside_material": "dirt",
            "primary_color": grass_col,
            "secondary_color": dirt_col,
            "grid_y": start_y,
        },
        {
            "id": f"ecosystem_dirt_water_{uuid.uuid4().hex[:8]}",
            "name": "Tierra sobre Agua (Ecosistema)",
            "profile": "dirt_over_water",
            "edge_profile": "rounded_chamfer",
            "inside_material": "dirt",
            "outside_material": "water",
            "primary_color": dirt_col,
            "secondary_color": water_col,
            "grid_y": start_y + row_spacing,
        },
        {
            "id": f"ecosystem_grass_water_{uuid.uuid4().hex[:8]}",
            "name": "Pasto sobre Agua (Ecosistema)",
            "profile": "grass_over_water",
            "edge_profile": "rounded_grass_tufts",
            "inside_material": "grass",
            "outside_material": "water",
            "primary_color": grass_col,
            "secondary_color": water_col,
            "grid_y": start_y + row_spacing * 2,
        },
    ]

    generated_sets: list[dict[str, Any]] = []
    for tier in tiers:
        base_src = source_id_map.get(tier["inside_material"]) if source_id_map else None
        sec_src = source_id_map.get(tier["outside_material"]) if source_id_map else None
        has_real_sources = bool(base_src or sec_src)

        set_data: dict[str, Any] = {
            "id": tier["id"],
            "name": tier["name"],
            "kind": kind,
            "baseSource": base_src,
            "secondarySource": sec_src,
            "blobMaterialMode": "synthesis" if has_real_sources else "procedural",
            "blobMode": "synthesis",
            "terrainProfile": tier["profile"],
            "edgeProfile": tier.get("edge_profile", "rounded_grass_tufts"),
            "insideMaterial": tier["inside_material"],
            "outsideMaterial": tier["outside_material"],
            "primaryColor": tier["primary_color"],
            "secondaryColor": tier["secondary_color"],
            "insideColor": tier["primary_color"],
            "outsideColor": tier["secondary_color"],
            "cornerStyle": corner_style,
            "shadowTint": shadow_tint,
            "shadowIntensity": shadow_intensity,
            "dropShadow": drop_shadow,
            "shadowDirection": shadow_dir,
            "rimLight": rim_light,
            "edgeVariation": edge_variation,
            "edgeSeed": 0,
            "variantCount": v_count if kind == "blob_47" else 1,
            "originX": 0,
            "originY": tier["grid_y"],
            "columns": cols,
            "rows": rows,
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
        generated_sets.append(set_data)

    return generated_sets
