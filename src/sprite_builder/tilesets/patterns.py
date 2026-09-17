"""Reusable terrain-pattern generation for Godot 4 TileSets."""

from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any, Literal, cast

import numpy as np
from PIL import Image, ImageDraw

try:
    from scipy.ndimage import distance_transform_cdt  # type: ignore[import-untyped]
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

from .core import TilesetGrid, slice_tileset

TerrainPatternKind = Literal["wang_16", "dual_grid_15", "blob_47", "sides_16"]
TerrainEdgeProfile = Literal[
    "clean",
    "organic_neutral",
    "grass_over_dirt",
    "dirt_over_water",
    "grass_over_water",
    "rounded_clean",
    "rounded_grass_tufts",
    "rounded_dither",
    "rounded_chamfer",
]
# Public compatibility alias retained for callers that adopted the original
# Dual Grid-only API. The same material grammars now apply to every pattern.
DualGridTerrainProfile = TerrainEdgeProfile

_DIRECTIONS = (
    "top",
    "top_right",
    "right",
    "bottom_right",
    "bottom",
    "bottom_left",
    "left",
    "top_left",
)
_DIRECTION_BITS = {name: 1 << index for index, name in enumerate(_DIRECTIONS)}
_GODOT_PEERING_BITS = {
    "right": 0,
    "bottom_right": 3,
    "bottom": 4,
    "bottom_left": 7,
    "left": 8,
    "top_left": 11,
    "top": 12,
    "top_right": 15,
}
_WANG_CORNERS = ("top_left", "top_right", "bottom_right", "bottom_left")
# The 15 artistic roles use the traditional Wang bit order. TileMapDual's
# terrain scanner reads Godot's corner peers in row order instead, so retain
# both orders explicitly rather than assuming that mask bits and peer order
# have the same third/fourth position.
_DUAL_GRID_TILEMAP_DUAL_PEERING_CORNERS = (
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
)
_DUAL_GRID_EMPTY_POSITION = (0, 3)
_DUAL_GRID_FOREGROUND_MASK = 15
_DUAL_GRID_TERRAIN_PROFILES: tuple[DualGridTerrainProfile, ...] = (
    "clean",
    "grass_over_dirt",
    "dirt_over_water",
    "grass_over_water",
)
_CORNER_MASK_PAIRS = {
    0b00000001: (0b00000010, 0b10000000),
    0b00000100: (0b00000010, 0b00001000),
    0b00010000: (0b00001000, 0b00100000),
    0b01000000: (0b00100000, 0b10000000),
}
_CORNER_MASKS = frozenset(_CORNER_MASK_PAIRS.keys())
_OPPOSITE_DIRECTIONS = {
    "top": "bottom",
    "top_right": "bottom_left",
    "right": "left",
    "bottom_right": "top_left",
    "bottom": "top",
    "bottom_left": "top_right",
    "left": "right",
    "top_left": "bottom_right",
}
_DIRECTION_DELTAS = {
    "top": (0, -1),
    "top_right": (1, -1),
    "right": (1, 0),
    "bottom_right": (1, 1),
    "bottom": (0, 1),
    "bottom_left": (-1, 1),
    "left": (-1, 0),
    "top_left": (-1, -1),
}
_TERRAIN_EDGE_PROFILES: tuple[TerrainEdgeProfile, ...] = (
    "clean",
    "organic_neutral",
    "grass_over_dirt",
    "dirt_over_water",
    "grass_over_water",
    "rounded_clean",
    "rounded_grass_tufts",
    "rounded_dither",
    "rounded_chamfer",
)
_DUAL_GRID_EDGE_VARIATION_MAX = 3
_DUAL_GRID_EDGE_SEED_MAX = 999_999
_BLOB_VARIANT_COUNT_MAX = 5


@dataclass(frozen=True, slots=True)
class TilesetAestheticPreset:
    """Curated visual recipe bundling edge profile, corner radius, style, and physical lighting."""

    id: str
    name: str
    icon: str
    description: str
    terrain_profile: TerrainEdgeProfile
    corner_radius: int
    corner_style: Literal["arc", "chamfer"]
    retro_outline: bool
    edge_variation: int
    drop_shadow: int
    shadow_direction: Literal["south", "south_east", "all_around"]
    shadow_tint: Literal["cool", "warm", "mystic", "neutral"]
    shadow_intensity: float
    rim_light: bool
    variant_count: int
    noise_style: str = "none"
    noise_intensity: float = 0.0

    def apply_to_set(self, set_config: Mapping[str, Any]) -> dict[str, Any]:
        """Return a copy of set_config with this aesthetic preset applied."""
        updated = dict(set_config)
        updated["terrainProfile"] = self.terrain_profile
        updated["cornerRadius"] = self.corner_radius
        updated["cornerStyle"] = self.corner_style
        updated["retroOutline"] = self.retro_outline
        updated["edgeVariation"] = self.edge_variation
        updated["dropShadow"] = self.drop_shadow
        updated["shadowDirection"] = self.shadow_direction
        updated["shadowTint"] = self.shadow_tint
        updated["shadowIntensity"] = self.shadow_intensity
        updated["rimLight"] = self.rim_light
        updated["variantCount"] = self.variant_count
        updated["aestheticPreset"] = self.id
        updated["noiseStyle"] = self.noise_style
        updated["noiseIntensity"] = self.noise_intensity
        return updated


TILESET_AESTHETIC_PRESETS: tuple[TilesetAestheticPreset, ...] = (
    TilesetAestheticPreset(
        id="zelda_topdown",
        name="Zelda Top-Down",
        icon="🗡️",
        description=(
            "Aventura SNES/GBA: silueta orgánica con mechones de césped, "
            "sombra inferior fría y cresta solar cenital."
        ),
        terrain_profile="rounded_grass_tufts",
        corner_radius=4,
        corner_style="arc",
        retro_outline=False,
        edge_variation=2,
        drop_shadow=2,
        shadow_direction="south",
        shadow_tint="cool",
        shadow_intensity=0.70,
        rim_light=True,
        variant_count=3,
        noise_style="simplex",
        noise_intensity=0.25,
    ),
    TilesetAestheticPreset(
        id="retro_16bit",
        name="Plataformas Retro 16-bit",
        icon="🍄",
        description=(
            "Consola clásica: bisel geométrico a 45°, contorno exterior de 1px "
            "y sombra diagonal marcada."
        ),
        terrain_profile="rounded_chamfer",
        corner_radius=3,
        corner_style="chamfer",
        retro_outline=True,
        edge_variation=1,
        drop_shadow=3,
        shadow_direction="south_east",
        shadow_tint="neutral",
        shadow_intensity=0.85,
        rim_light=False,
        variant_count=3,
        noise_style="dither",
        noise_intensity=0.25,
    ),
    TilesetAestheticPreset(
        id="gameboy_dither",
        name="Nostalgia Dither / 1-Bit",
        icon="🕹️",
        description=(
            "Tramado retro punteado y contorno 1px sin degradados de sombra; "
            "ideal para Game Boy o estética pixel-art 1-bit."
        ),
        terrain_profile="rounded_dither",
        corner_radius=4,
        corner_style="arc",
        retro_outline=True,
        edge_variation=1,
        drop_shadow=0,
        shadow_direction="south",
        shadow_tint="neutral",
        shadow_intensity=0.70,
        rim_light=False,
        variant_count=2,
        noise_style="dither",
        noise_intensity=0.45,
    ),
    TilesetAestheticPreset(
        id="neon_dungeon",
        name="Mazmorra Neón / Abisal",
        icon="🌌",
        description=(
            "Losas limpias con contorno nítido, sombra omnidireccional profunda "
            "con tinte místico púrpura y rim light."
        ),
        terrain_profile="rounded_clean",
        corner_radius=2,
        corner_style="chamfer",
        retro_outline=True,
        edge_variation=0,
        drop_shadow=3,
        shadow_direction="all_around",
        shadow_tint="mystic",
        shadow_intensity=0.90,
        rim_light=True,
        variant_count=3,
        noise_style="simplex",
        noise_intensity=0.20,
    ),
    TilesetAestheticPreset(
        id="coastal_organic",
        name="Costa Orgánica / Playa",
        icon="🏖️",
        description=(
            "Ribete irregular de orilla con contacto orgánico suave y sutil sombra acuática translúcida."
        ),
        terrain_profile="dirt_over_water",
        corner_radius=3,
        corner_style="arc",
        retro_outline=False,
        edge_variation=3,
        drop_shadow=1,
        shadow_direction="south",
        shadow_tint="cool",
        shadow_intensity=0.50,
        rim_light=False,
        variant_count=3,
        noise_style="gravel",
        noise_intensity=0.35,
    ),
    TilesetAestheticPreset(
        id="clean_pixel",
        name="Pixel Limpio / Minimal",
        icon="🧼",
        description=(
            "Geometría ortogonal pura sin alteración de silueta ni sombras proyectadas; "
            "ideal para prototipado rápido."
        ),
        terrain_profile="clean",
        corner_radius=0,
        corner_style="arc",
        retro_outline=False,
        edge_variation=0,
        drop_shadow=0,
        shadow_direction="south",
        shadow_tint="neutral",
        shadow_intensity=0.70,
        rim_light=False,
        variant_count=1,
        noise_style="none",
        noise_intensity=0.0,
    ),
)
_AESTHETIC_PRESETS_BY_ID = {preset.id: preset for preset in TILESET_AESTHETIC_PRESETS}


def list_aesthetic_presets() -> tuple[TilesetAestheticPreset, ...]:
    """Return all pre-curated aesthetic recipes for tilesets."""
    return TILESET_AESTHETIC_PRESETS


def get_aesthetic_preset(preset_id: str) -> TilesetAestheticPreset | None:
    """Look up an aesthetic preset by id."""
    return _AESTHETIC_PRESETS_BY_ID.get(preset_id)


def detect_matching_aesthetic_preset(set_config: Mapping[str, Any]) -> str | None:
    """Return the id of a matching preset if set_config matches all its key traits, else None."""
    explicit = set_config.get("aestheticPreset")
    if explicit and explicit in _AESTHETIC_PRESETS_BY_ID:
        return str(explicit)
    for preset in TILESET_AESTHETIC_PRESETS:
        if (
            set_config.get("terrainProfile") == preset.terrain_profile
            and int(set_config.get("cornerRadius", 0)) == preset.corner_radius
            and set_config.get("cornerStyle", "arc") == preset.corner_style
            and bool(set_config.get("retroOutline", False)) == preset.retro_outline
            and int(set_config.get("dropShadow", 0)) == preset.drop_shadow
            and bool(set_config.get("rimLight", False)) == preset.rim_light
        ):
            return preset.id
    return None


_WANG_PATTERN_KINDS = frozenset(("wang_16", "dual_grid_15"))
_PATTERN_MODES = {
    "wang_16": "match_sides",
    "dual_grid_15": "match_corners",
    "sides_16": "match_sides",
    "blob_47": "match_corners_and_sides",
}
_GODOT_PATTERN_LAYOUTS: dict[
    TerrainPatternKind,
    tuple[tuple[int | None, ...], ...],
] = {
    # Official Godot 3.x 3x3-minimal template. The empty slot at row 1,
    # column 10 is intentionally preserved so the exported PNG matches the
    # familiar 12x4 bitmap layout exactly.
    "blob_47": (
        (16, 20, 84, 80, 213, 92, 116, 87, 28, 125, 124, 112),
        (17, 21, 85, 81, 29, 127, 253, 113, 31, 119, None, 245),
        (1, 5, 69, 65, 23, 223, 247, 209, 95, 255, 221, 241),
        (0, 4, 68, 64, 117, 71, 197, 93, 7, 199, 215, 193),
    ),
    # Official Godot 3.x 3x3-minimal-16 arrangement for Wang 16 (matching
    # cardinal sides/edges for roads, paths, and pipes).
    "wang_16": (
        (4, 6, 14, 12),
        (5, 7, 15, 13),
        (1, 3, 11, 9),
        (0, 2, 10, 8),
    ),
    # TileMapDual's Standard preset is a full 4x4 atlas.  The 15 authored
    # foreground roles omit mask 0, while the builder fills this physical
    # slot from the secondary/background Source for runtime export.
    "dual_grid_15": (
        (8, 6, 13, 12),
        (5, 14, 15, 11),
        (2, 3, 7, 9),
        (None, 4, 10, 1),
    ),
    # Official Godot 3.x 3x3-minimal-16 arrangement, equivalent to matching
    # cardinal sides while corner cells are ignored.
    "sides_16": (
        (4, 6, 14, 12),
        (5, 7, 15, 13),
        (1, 3, 11, 9),
        (0, 2, 10, 8),
    ),
}

# Tilesetter presents Blob 47 as a readable 11x5 composition instead of the
# compact Godot 12x4 bitmap template used for export. Keep both layouts
# separate so the authoring view never changes the exported atlas order.
_TILESETTER_SET_LAYOUTS: dict[
    TerrainPatternKind,
    tuple[tuple[int | None, ...], ...],
] = {
    "blob_47": (
        (28, 124, 112, 16, 20, 116, 92, 80, 84, 221, None),
        (31, 255, 241, 17, 23, 247, 223, 209, 215, 119, None),
        (7, 199, 193, 1, 29, 253, 127, 113, 125, 93, 117),
        (4, 68, 64, 0, 5, 197, 71, 65, 69, 87, 213),
        (None, None, None, None, 21, 245, 95, 81, 85, None, None),
    ),
}


@dataclass(frozen=True, slots=True)
class TerrainPatternTile:
    """One deterministic tile role in a reusable terrain pattern."""

    index: int
    mask: int
    column: int
    row: int
    neighbors: tuple[str, ...]
    source_index: int | None = None
    generated: bool = False
    override_source_index: int | None = None
    variant: int = 0
    variant_seed: int = 0
    probability: float = 1.0


@dataclass(frozen=True, slots=True)
class TerrainPatternResult:
    """Rendered atlas plus the semantic roles needed by an engine exporter."""

    kind: TerrainPatternKind
    mode: str
    image: Image.Image
    tile_width: int
    tile_height: int
    columns: int
    rows: int
    tiles: tuple[TerrainPatternTile, ...]
    dual_grid_profile: DualGridTerrainProfile | None = None
    dual_grid_edge_variation: int = 0
    dual_grid_edge_seed: int = 0
    terrain_profile: TerrainEdgeProfile | None = None
    edge_variation: int = 0
    edge_seed: int = 0
    corner_radius: int = 0
    retro_outline: bool = False
    variant_count: int = 1
    blob_mode: str = "synthesis"
    drop_shadow: int = 0
    shadow_direction: str = "south"
    shadow_tint: str = "cool"
    shadow_intensity: float = 0.70
    rim_light: bool = False
    corner_style: str = "arc"
    is_animated: bool = False
    animation_frames: int = 1
    animation_fps: float = 8.0
    animation_style: str = "shore_ripples"
    animation_frames_images: tuple[Image.Image, ...] | None = None
    base_rows: int | None = None
    noise_style: str = "none"
    noise_intensity: float = 0.0
    inner_corner_rounding: float = 0.5

    @property
    def complete(self) -> bool:
        return all(tile.source_index is not None for tile in self.tiles)

    @property
    def unassigned_masks(self) -> tuple[int, ...]:
        return tuple(tile.mask for tile in self.tiles if tile.source_index is None)


def _normalize_blob_mask(mask: int) -> int:
    value = int(mask) & 0xFF
    requirements = {
        "top_right": ("top", "right"),
        "bottom_right": ("bottom", "right"),
        "bottom_left": ("bottom", "left"),
        "top_left": ("top", "left"),
    }
    for diagonal, (first, second) in requirements.items():
        if not value & _DIRECTION_BITS[first] or not value & _DIRECTION_BITS[second]:
            value &= ~_DIRECTION_BITS[diagonal]
    return value


def terrain_pattern_masks(kind: TerrainPatternKind) -> tuple[int, ...]:
    """Return canonical masks for a terrain pattern."""

    if kind == "wang_16":
        return tuple(range(16))
    if kind == "dual_grid_15":
        return tuple(range(1, 16))
    if kind == "sides_16":
        return tuple(range(16))
    if kind == "blob_47":
        masks = {_normalize_blob_mask(mask) for mask in range(256)}
        result = tuple(sorted(masks))
        if len(result) != 47:  # defensive guard around the canonical rule
            raise RuntimeError(f"Blob mask normalization produced {len(result)} roles")
        return result
    raise ValueError(f"Unsupported terrain pattern: {kind}")


def terrain_pattern_layout(
    kind: TerrainPatternKind,
) -> tuple[tuple[int | None, ...], ...]:
    """Return the canonical Godot bitmap-template layout for a pattern."""

    try:
        return _GODOT_PATTERN_LAYOUTS[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported terrain pattern: {kind}") from exc


def terrain_pattern_set_layout(
    kind: TerrainPatternKind,
) -> tuple[tuple[int | None, ...], ...]:
    """Return a readable authoring layout without changing the export atlas."""

    return _TILESETTER_SET_LAYOUTS.get(kind, terrain_pattern_layout(kind))


def _role_positions(
    kind: TerrainPatternKind,
    columns: int | None,
) -> tuple[dict[int, tuple[int, int]], int, int]:
    if kind == "dual_grid_15" and columns is not None:
        raise ValueError("Dual Grid uses TileMapDual's fixed 4x4 layout; omit columns")
    if columns is not None:
        column_count = int(columns)
        if column_count < 1:
            raise ValueError("Pattern atlas columns must be positive")
        masks = terrain_pattern_masks(kind)
        return (
            {
                mask: (index % column_count, index // column_count)
                for index, mask in enumerate(masks)
            },
            column_count,
            math.ceil(len(masks) / column_count),
        )
    layout = terrain_pattern_layout(kind)
    positions = {
        int(mask): (column, row)
        for row, layout_row in enumerate(layout)
        for column, mask in enumerate(layout_row)
        if mask is not None
    }
    expected = set(terrain_pattern_masks(kind))
    if set(positions) != expected:
        raise RuntimeError(f"Invalid canonical layout for {kind}")
    return positions, len(layout[0]), len(layout)


def _fit_source(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    rgba = image.convert("RGBA")
    if rgba.size == size:
        return rgba.copy()
    return rgba.resize(size, Image.Resampling.NEAREST)


def _validate_dual_grid_size(
    kind: TerrainPatternKind,
    size: tuple[int, int],
) -> None:
    """Reject geometries that cannot encode four distinct Dual Grid corners."""

    if kind == "dual_grid_15" and (size[0] < 2 or size[1] < 2):
        raise ValueError("Dual Grid tiles must be at least 2x2 pixels")


def _place_pattern_tile(
    atlas: Image.Image,
    tile: Image.Image,
    offset: tuple[int, int],
    *,
    kind: TerrainPatternKind,
) -> None:
    """Place a role while preserving raw transparent-pixel provenance for Dual Grid."""

    if kind == "dual_grid_15":
        # Dual roles never overlap.  Direct paste retains RGB under alpha 0,
        # which alpha_composite intentionally canonicalizes away.
        atlas.paste(tile, offset)
        return
    atlas.alpha_composite(tile, offset)


def _place_dual_grid_background(
    atlas: Image.Image,
    background: Image.Image,
    size: tuple[int, int],
) -> None:
    """Materialize TileMapDual's required physical mask-0 atlas cell."""

    column, row = _DUAL_GRID_EMPTY_POSITION
    atlas.paste(background, (column * size[0], row * size[1]))


def _is_wang_pattern(kind: TerrainPatternKind) -> bool:
    return kind in _WANG_PATTERN_KINDS


def _terrain_mode(kind: TerrainPatternKind) -> str:
    try:
        return _PATTERN_MODES[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported terrain pattern: {kind}") from exc


def terrain_edge_profiles() -> tuple[TerrainEdgeProfile, ...]:
    """Return the stable material-pair profile identifiers for every pattern."""

    return _TERRAIN_EDGE_PROFILES


def dual_grid_terrain_profiles() -> tuple[DualGridTerrainProfile, ...]:
    """Compatibility alias for the original Dual Grid profile API."""

    return _DUAL_GRID_TERRAIN_PROFILES


def _normalize_terrain_edge_style(
    profile: object = "clean",
    variation: object = 0,
    seed: object = 0,
) -> tuple[TerrainEdgeProfile, int, int]:
    profile_name = str(profile or "clean")
    if profile_name not in _TERRAIN_EDGE_PROFILES:
        raise ValueError(f"Unsupported terrain edge profile: {profile_name}")
    try:
        variation_level = int(cast(str | bytes | bytearray | int | float, variation))
    except (TypeError, ValueError) as exc:
        raise ValueError("Dual Grid edge variation must be an integer from 0 to 3") from exc
    if not 0 <= variation_level <= _DUAL_GRID_EDGE_VARIATION_MAX:
        raise ValueError("Dual Grid edge variation must be an integer from 0 to 3")
    try:
        seed_value = int(cast(str | bytes | bytearray | int | float, seed))
    except (TypeError, ValueError) as exc:
        raise ValueError("Dual Grid edge seed must be an integer from 0 to 999999") from exc
    if not 0 <= seed_value <= _DUAL_GRID_EDGE_SEED_MAX:
        raise ValueError("Dual Grid edge seed must be an integer from 0 to 999999")
    return profile_name, variation_level, seed_value


def _normalize_dual_grid_edge_style(
    profile: object = "clean",
    variation: object = 0,
    seed: object = 0,
) -> tuple[DualGridTerrainProfile, int, int]:
    """Compatibility wrapper retaining the old Dual Grid error contract."""

    try:
        return _normalize_terrain_edge_style(profile, variation, seed)
    except ValueError as exc:
        if str(exc).startswith("Unsupported terrain edge profile:"):
            message = str(exc).replace(
                "Unsupported terrain edge profile:",
                "Unsupported Dual Grid terrain profile:",
            )
            raise ValueError(message) from exc
        raise


def _normalize_pattern_edge_style(
    kind: TerrainPatternKind,
    profile: object = "clean",
    variation: object = 0,
    seed: object = 0,
) -> tuple[TerrainEdgeProfile, int, int]:
    normalizer = (
        _normalize_dual_grid_edge_style
        if kind == "dual_grid_15"
        else _normalize_terrain_edge_style
    )
    return normalizer(profile, variation, seed)


def _normalize_blob_variant_count(kind: TerrainPatternKind, value: object = 1) -> int:
    """Return the number of visual banks without changing non-Blob atlases."""

    if kind != "blob_47":
        return 1
    try:
        count = int(cast(str | bytes | bytearray | int | float, value))
    except (TypeError, ValueError) as exc:
        raise ValueError("Blob variant count must be an integer from 1 to 5") from exc
    if not 1 <= count <= _BLOB_VARIANT_COUNT_MAX:
        raise ValueError("Blob variant count must be an integer from 1 to 5")
    return count


def _wang_bitmap_coverage(mask: int, width: int, height: int) -> np.ndarray:
    nw, ne, se, sw = (1.0 if mask & (1 << index) else 0.0 for index in range(4))
    xs = (np.arange(width, dtype=np.float32) + 0.5) / width
    ys = (np.arange(height, dtype=np.float32) + 0.5) / height
    u, v = np.meshgrid(xs, ys)
    return nw * (1.0 - u) * (1.0 - v) + ne * u * (1.0 - v) + sw * (1.0 - u) * v + se * u * v


def _wang_bitmap_mask(mask: int, width: int, height: int) -> np.ndarray:
    return _wang_bitmap_coverage(mask, width, height) >= 0.5


def _wang_edge_path_coverage(
    mask: int,
    width: int,
    height: int,
    *,
    profile: TerrainEdgeProfile = "clean",
    variation: int = 0,
    seed: int = 0,
    path_width_ratio: float = 0.45,
) -> np.ndarray:
    """Return organic path/road coverage for 2-edge cardinal Wang 16 autotiles."""
    n = bool(mask & 1)
    e = bool(mask & 2)
    s = bool(mask & 4)
    w = bool(mask & 8)

    if not (n or e or s or w):
        return np.zeros((height, width), dtype=np.float32)

    yy, xx = np.indices((height, width), dtype=np.float32)
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    r0 = width * (path_width_ratio / 2.0)

    dist = np.full((height, width), 999.0, dtype=np.float32)
    dist = np.minimum(dist, np.hypot(xx - cx, yy - cy))

    if n:
        dist = np.minimum(dist, np.hypot(np.abs(xx - cx), np.maximum(0.0, yy - cy)))
    if s:
        dist = np.minimum(dist, np.hypot(np.abs(xx - cx), np.maximum(0.0, cy - yy)))
    if w:
        dist = np.minimum(dist, np.hypot(np.maximum(0.0, xx - cx), np.abs(yy - cy)))
    if e:
        dist = np.minimum(dist, np.hypot(np.maximum(0.0, cx - xx), np.abs(yy - cy)))

    if profile in {"clean", "rounded_clean"} or variation <= 0:
        cov = np.clip(0.5 - (dist - r0) / 0.8, 0.0, 1.0)
    else:
        digest = hashlib.sha256(f"wang-edge:{profile}:{seed}:{mask}".encode()).digest()
        p1 = (digest[0] / 255.0) * (2.0 * math.pi)
        p2 = (digest[1] / 255.0) * (2.0 * math.pi)
        p3 = (digest[2] / 255.0) * (2.0 * math.pi)
        p4 = (digest[3] / 255.0) * (2.0 * math.pi)

        x_norm = xx / max(1.0, width - 1.0)
        y_norm = yy / max(1.0, height - 1.0)

        w1 = np.sin(2.0 * math.pi * x_norm + p1) + np.cos(2.0 * math.pi * y_norm + p2)
        w2 = 0.50 * (np.sin(4.0 * math.pi * x_norm + p3) + np.cos(4.0 * math.pi * y_norm + p4))
        wave = (w1 + w2) / 1.5

        # Port envelope: keep exact road width at tile boundary seams
        border_dist = np.minimum.reduce((xx, width - 1.0 - xx, yy, height - 1.0 - yy))
        envelope = np.clip(border_dist / 1.5, 0.0, 1.0) ** 0.6

        size_scale = math.sqrt(max(2, min(width, height)) / 16.0)
        amp = (0.9, 1.5, 2.2)[variation - 1] * size_scale
        disp = amp * wave * envelope

        if profile == "rounded_grass_tufts":
            field = _dual_grid_texture_field(width, height, profile="rounded_grass_tufts", seed=seed)
            tufts = (field > 0.42).astype(np.float32) * 0.18
            cov = np.clip(0.5 - (dist - disp - r0) / 0.8 + tufts * envelope, 0.0, 1.0)
        elif profile == "rounded_dither":
            bayer = np.where((xx.astype(int) % 2 == 0) == (yy.astype(int) % 2 == 0), 0.12, -0.12).astype(np.float32)
            raw_cov = np.clip(0.5 - (dist - disp - r0) / 0.8, 0.0, 1.0)
            near_boundary = (raw_cov > 0.3) & (raw_cov < 0.7)
            cov = np.where(near_boundary, np.clip(raw_cov + bayer * envelope, 0.0, 1.0), raw_cov)
        else:
            cov = np.clip(0.5 - (dist - disp - r0) / 0.8, 0.0, 1.0)

    # Guarantee strict port boundary compatibility:
    port_mask_x = np.abs(xx - cx) <= r0
    port_mask_y = np.abs(yy - cy) <= r0

    if n:
        cov[0, :] = np.where(port_mask_x[0, :], 1.0, 0.0)
    else:
        cov[0, :] = 0.0

    if s:
        cov[-1, :] = np.where(port_mask_x[-1, :], 1.0, 0.0)
    else:
        cov[-1, :] = 0.0

    if w:
        cov[:, 0] = np.where(port_mask_y[:, 0], 1.0, 0.0)
    else:
        cov[:, 0] = 0.0

    if e:
        cov[:, -1] = np.where(port_mask_y[:, -1], 1.0, 0.0)
    else:
        cov[:, -1] = 0.0

    return np.asarray(cov, dtype=np.float32)


@lru_cache(maxsize=512)
def _cached_rounded_corner_coverage(
    mask: int,
    width: int,
    height: int,
    radius: int,
    kind: TerrainPatternKind,
    corner_style: str,
) -> np.ndarray:
    if radius <= 0:
        if kind == "dual_grid_15":
            return _wang_bitmap_coverage(mask, width, height)
        elif kind in ("sides_16", "wang_16"):
            return _wang_edge_path_coverage(mask, width, height)
        return _blob_bitmap_coverage(mask, width, height)

    max_r = max(1, min(width, height) // 2)
    r = min(max_r, max(0, int(radius)))

    if kind == "dual_grid_15":
        cov = _wang_bitmap_coverage(mask, width, height).copy()
        nw, ne, se, sw = (bool(mask & (1 << i)) for i in range(4))
        half_w = width / 2.0
        half_h = height / 2.0

        # Outer corner fillets (1 corner on, 3 off):
        if nw and not ne and not sw:
            for y in range(r):
                for x in range(r):
                    if (r - x) ** 2 + (r - y) ** 2 > r ** 2:
                        cov[y, x] = min(cov[y, x], 0.2)
        if ne and not nw and not se:
            for y in range(r):
                for dx in range(r):
                    x = width - 1 - dx
                    if (r - dx) ** 2 + (r - y) ** 2 > r ** 2:
                        cov[y, x] = min(cov[y, x], 0.2)
        if se and not ne and not sw:
            for dy in range(r):
                y = height - 1 - dy
                for dx in range(r):
                    x = width - 1 - dx
                    if (r - dx) ** 2 + (r - dy) ** 2 > r ** 2:
                        cov[y, x] = min(cov[y, x], 0.2)
        if sw and not nw and not se:
            for dy in range(r):
                y = height - 1 - dy
                for x in range(r):
                    if (r - x) ** 2 + (r - dy) ** 2 > r ** 2:
                        cov[y, x] = min(cov[y, x], 0.2)

        return cov
    elif kind in ("sides_16", "wang_16"):
        return _wang_edge_path_coverage(mask, width, height)
    else:
        blob_m = mask
        if blob_m in (0, 0xFF):
            return np.full(
                (height, width),
                1.0 if blob_m == 0xFF else 0.0,
                dtype=np.float32,
            )

        # Blob's bilinear rule is excellent for topology, but its diagonal
        # chord reads as a rigid square when it is used as the final pixel
        # contour.  Evaluate each quadrant as a signed quarter-circle instead.
        # The circle is centred on the tile midpoint, so it meets both exposed
        # ports at exactly their midpoints and remains seam-compatible.
        cov = _blob_bitmap_coverage(blob_m, width, height).copy()
        half_width = width / 2.0
        half_height = height / 2.0
        soft_width = max(0.35, min(width, height) / max(10.0, float(r) * 2.0))
        quadrants = (
            ("top_left", "top", "left", 0, width // 2, 0, height // 2, 1, 1),
            (
                "top_right",
                "top",
                "right",
                (width + 1) // 2,
                width,
                0,
                height // 2,
                -1,
                1,
            ),
            (
                "bottom_right",
                "bottom",
                "right",
                (width + 1) // 2,
                width,
                (height + 1) // 2,
                height,
                -1,
                -1,
            ),
            (
                "bottom_left",
                "bottom",
                "left",
                0,
                width // 2,
                (height + 1) // 2,
                height,
                1,
                -1,
            ),
        )
        for diagonal, first, second, x0, x1, y0, y1, step_x, step_y in quadrants:
            diagonal_on = bool(blob_m & _DIRECTION_BITS[diagonal])
            first_on = bool(blob_m & _DIRECTION_BITS[first])
            second_on = bool(blob_m & _DIRECTION_BITS[second])
            if diagonal_on:
                continue
            for y in range(y0, y1):
                for x in range(x0, x1):
                    # u/v run from the corner (0) to the shared tile centre
                    # (1), independent of the quadrant's screen orientation.
                    u = (
                        (x + 0.5) / half_width
                        if step_x > 0
                        else (width - x - 0.5) / half_width
                    )
                    v = (
                        (y + 0.5) / half_height
                        if step_y > 0
                        else (height - y - 0.5) / half_height
                    )
                    if not first_on and not second_on:
                        # Convex outer corner: land is inside the curve whose
                        # tangencies are the two side ports.
                        if corner_style == "chamfer":
                            signed = (u + v) - 1.0
                        else:
                            distance = math.sqrt((1.0 - u) ** 2 + (1.0 - v) ** 2)
                            signed = 1.0 - distance
                        cov[y, x] = float(
                            np.clip(0.5 + signed / (2.0 * soft_width), 0.0, 1.0)
                        )
                    elif first_on and second_on:
                        # Concave inner corner: gentle organic fillet without aggressive scoops
                        if corner_style == "chamfer":
                            signed = (u + v) - 0.65
                            cov[y, x] = float(
                                np.clip(0.5 + signed / (2.0 * soft_width), 0.0, 1.0)
                            )
                        else:
                            corner_env = max(0.0, 1.0 - u / 0.5) * max(0.0, 1.0 - v / 0.5)
                            cov[y, x] = float(
                                np.clip(u + v - u * v - 0.28 * corner_env, 0.0, 1.0)
                            )
                    else:
                        # A one-sided quadrant is a straight port transition;
                        # keep its midpoint tangent and let the organic pass
                        # introduce the small material-specific undulation.
                        signed = v - 0.5 if second_on else u - 0.5
                        cov[y, x] = float(
                            np.clip(0.5 + signed / (2.0 * soft_width), 0.0, 1.0)
                        )
        # The outer ring is the Blob port contract.  Pixel centres on a
        # quarter-circle can otherwise appear one row inside the mathematical
        # midpoint, making a role claim a neighbour's side at the seam.
        base_ring = _blob_bitmap_coverage(blob_m, width, height)
        cov[0, :] = base_ring[0, :]
        cov[-1, :] = base_ring[-1, :]
        cov[:, 0] = base_ring[:, 0]
        cov[:, -1] = base_ring[:, -1]
        cov[0, 0] = float(bool(blob_m & _DIRECTION_BITS["top_left"]))
        cov[0, -1] = float(bool(blob_m & _DIRECTION_BITS["top_right"]))
        cov[-1, -1] = float(bool(blob_m & _DIRECTION_BITS["bottom_right"]))
        cov[-1, 0] = float(bool(blob_m & _DIRECTION_BITS["bottom_left"]))
        return cov


def _rounded_corner_coverage(
    mask: int,
    width: int,
    height: int,
    *,
    radius: int = 0,
    kind: TerrainPatternKind = "blob_47",
    corner_style: str = "arc",
) -> np.ndarray:
    """Compute terrain coverage with analytical rounded corner fillets.

    Calculates quarter-circle fillet curves for outer corners and inner notches,
    replacing sharp 90-degree or 45-degree seams with smooth curved pixel profiles.
    """
    return _cached_rounded_corner_coverage(
        mask, width, height, int(radius), kind, corner_style
    ).copy()


def _apply_retro_outline(
    image: Image.Image,
    mask: np.ndarray,
    *,
    outline_color: tuple[int, int, int, int] = (22, 26, 34, 255),
    strength: float = 0.72,
) -> Image.Image:
    """Apply a crisp 1-pixel dark retro outline along the terrain perimeter."""
    arr = np.asarray(image, dtype=np.uint8).copy()
    h, w = mask.shape
    inside = np.asarray(mask, dtype=bool)

    if not np.any(inside) or np.all(inside):
        return image

    padded = np.pad(inside, 1, mode="constant", constant_values=False)
    up = padded[:h, 1 : w + 1]
    down = padded[2:, 1 : w + 1]
    left = padded[1 : h + 1, :w]
    right = padded[1 : h + 1, 2:]

    border = inside & ~(up & down & left & right)
    if not np.any(border):
        return image

    target = np.array(outline_color[:3], dtype=np.float32)
    original = arr[..., :3].astype(np.float32)
    blended = original * (1.0 - strength) + target * strength
    arr[border, :3] = np.clip(blended[border], 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGBA")


def _dual_grid_texture_field(
    width: int,
    height: int,
    *,
    profile: TerrainEdgeProfile,
    seed: int,
) -> np.ndarray:
    """Build a seamless, quarter-turn-covariant field for restrained edge texture."""

    digest = hashlib.sha256(f"dual-grid:{profile}:{seed}".encode()).digest()
    x = np.arange(width, dtype=np.float32) / max(1, width - 1)
    y = np.arange(height, dtype=np.float32) / max(1, height - 1)
    u, v = np.meshgrid(x, y)

    if profile == "organic_neutral":
        low_frequency = 1 + digest[0] % 2
        high_frequency = 3 + digest[1] % 3
        bias = 0.0
        low_weight, high_weight, cross_weight = 0.52, 0.30, 0.18
    elif profile == "grass_over_dirt":
        low_frequency = 2 + digest[0] % 2
        high_frequency = 4 + digest[1] % 3
        bias = 0.10
        low_weight, high_weight, cross_weight = 0.22, 0.58, 0.20
    elif profile == "dirt_over_water":
        low_frequency = 1 + digest[0] % 2
        high_frequency = 2 + digest[1] % 2
        bias = 0.28
        low_weight, high_weight, cross_weight = 0.58, 0.22, 0.20
    elif profile == "grass_over_water":
        low_frequency = 2 + digest[0] % 2
        high_frequency = 3 + digest[1] % 3
        bias = -0.10
        low_weight, high_weight, cross_weight = 0.34, 0.46, 0.20
    elif profile == "rounded_grass_tufts":
        low_frequency = 3 + digest[0] % 2
        high_frequency = 5 + digest[1] % 2
        bias = 0.05
        low_weight, high_weight, cross_weight = 0.40, 0.40, 0.20
    else:  # rounded_clean, rounded_dither, clean
        low_frequency = 2
        high_frequency = 4
        bias = 0.0
        low_weight, high_weight, cross_weight = 0.30, 0.50, 0.20

    sign = -1.0 if digest[2] & 1 else 1.0
    low = (
        np.cos(2.0 * math.pi * low_frequency * u) + np.cos(2.0 * math.pi * low_frequency * v)
    ) * 0.5
    high = (
        np.cos(2.0 * math.pi * high_frequency * u) + np.cos(2.0 * math.pi * high_frequency * v)
    ) * 0.5
    cross = np.cos(2.0 * math.pi * low_frequency * u) * np.cos(2.0 * math.pi * low_frequency * v)
    field = bias + low_weight * low + sign * high_weight * high + cross_weight * cross
    peak = float(np.max(np.abs(field)))
    return field / max(1.0, peak)


def _dual_grid_profile_coverage(
    mask: int,
    width: int,
    height: int,
    *,
    kind: TerrainPatternKind = "dual_grid_15",
    profile: TerrainEdgeProfile = "clean",
    variation: int = 0,
    seed: int = 0,
    corner_radius: int = 0,
    inner_rounding: float = 0.5,
) -> np.ndarray:
    """Return styled coverage while keeping compatible atlas edges deterministic."""

    normalizer = (
        _normalize_dual_grid_edge_style
        if kind == "dual_grid_15"
        else _normalize_terrain_edge_style
    )
    profile, variation, seed = normalizer(profile, variation, seed)
    if kind in ("wang_16", "sides_16"):
        return _wang_edge_path_coverage(
            mask,
            width,
            height,
            profile=profile,
            variation=variation,
            seed=seed,
        )

    if corner_radius > 0 or profile in {"rounded_clean", "rounded_grass_tufts", "rounded_dither"}:
        eff_radius = (
            corner_radius
            if corner_radius > 0
            else max(1, (variation + 1) * max(1, min(width, height) // 16))
        )
        coverage = _rounded_corner_coverage(mask, width, height, radius=eff_radius, kind=kind)
    elif kind == "dual_grid_15":
        coverage = _wang_bitmap_coverage(mask, width, height)
    else:
        coverage = _blob_bitmap_coverage(mask, width, height)

    if (
        profile in {"clean", "rounded_clean"}
        or variation == 0
        or mask in _profile_terminal_masks(kind)
    ):
        return coverage

    if profile == "rounded_grass_tufts":
        field = _dual_grid_texture_field(width, height, profile="rounded_grass_tufts", seed=seed)
        tufts = (field > 0.40).astype(np.float32) * 0.16
        coverage = np.clip(coverage + tufts, 0.0, 1.0)
        if variation <= 0:
            return np.asarray(coverage, dtype=np.float32)

    if profile == "rounded_dither":
        yy, xx = np.indices((height, width))
        bayer = np.where((xx % 2 == 0) == (yy % 2 == 0), 0.10, -0.10).astype(np.float32)
        near_boundary = (coverage > 0.3) & (coverage < 0.7)
        coverage = np.where(near_boundary, np.clip(coverage + bayer, 0.0, 1.0), coverage)
        return np.asarray(coverage, dtype=np.float32)

    # A displacement below one source pixel frequently vanishes after the
    # boolean threshold (all three profiles used to collapse to the same
    # bitmap at 8x8).  These levels remain restrained, but make even the
    # "subtle" preset cross a real pixel boundary on practical tile sizes.
    requested_pixels = (1.2, 1.8, 2.6)[variation - 1]
    profile_scale = {
        "grass_over_dirt": 1.0,
        "dirt_over_water": 0.84,
        "grass_over_water": 0.92,
        "rounded_grass_tufts": 1.05,
    }.get(profile, 1.0)
    amplitude = min(0.24, requested_pixels * profile_scale / max(2, min(width, height)))
    field = _dual_grid_texture_field(width, height, profile=profile, seed=seed)
    x = np.arange(width, dtype=np.float32) / max(1, width - 1)
    y = np.arange(height, dtype=np.float32) / max(1, height - 1)
    u, v = np.meshgrid(x, y)
    # Keep silhouette noise away from the outer pixel ring. The mathematical
    # edge samples below still let palette bands continue across compatible
    # roles without inheriting a different local perturbation on either side.
    edge_distance = np.minimum.reduce((u, 1.0 - u, v, 1.0 - v))
    seam_envelope = np.clip(edge_distance * 8.0, 0.0, 1.0)
    styled = coverage + amplitude * field * seam_envelope

    # The ordinary coverage samples pixel centres. On the outer ring that can
    # make two compatible roles see slightly different distances from their
    # shared boundary. Sample the exact mathematical edge instead, so shading
    # bands and ownership meet without a one-pixel colour break.
    if kind == "dual_grid_15":
        nw, ne, se, sw = (1.0 if mask & (1 << index) else 0.0 for index in range(4))
        edge_x = (np.arange(width, dtype=np.float32) + 0.5) / width
        edge_y = (np.arange(height, dtype=np.float32) + 0.5) / height
        styled[0, :] = nw * (1.0 - edge_x) + ne * edge_x
        styled[-1, :] = sw * (1.0 - edge_x) + se * edge_x
        styled[:, 0] = nw * (1.0 - edge_y) + sw * edge_y
        styled[:, -1] = ne * (1.0 - edge_y) + se * edge_y
        styled[0, 0], styled[0, -1] = nw, ne
        styled[-1, 0], styled[-1, -1] = sw, se
        styled[-1, -1], styled[-1, 0] = se, sw
    return np.asarray(styled, dtype=np.float32)


def _pixel_distance_to_mask(mask: np.ndarray) -> np.ndarray:
    """Return a deterministic four-neighbour distance map for a pixel mask."""

    target = np.asarray(mask, dtype=bool)
    height, width = target.shape
    unreachable = height + width + 1

    if _HAS_SCIPY:
        if not np.any(target):
            return np.full((height, width), unreachable, dtype=np.int32)
        return distance_transform_cdt(~target, metric="taxicab").astype(np.int32)

    distance = np.full((height, width), unreachable, dtype=np.int32)
    distance[target] = 0
    for y in range(height):
        for x in range(width):
            best = int(distance[y, x])
            if y:
                best = min(best, int(distance[y - 1, x]) + 1)
            if x:
                best = min(best, int(distance[y, x - 1]) + 1)
            distance[y, x] = best
    for y in range(height - 1, -1, -1):
        for x in range(width - 1, -1, -1):
            best = int(distance[y, x])
            if y + 1 < height:
                best = min(best, int(distance[y + 1, x]) + 1)
            if x + 1 < width:
                best = min(best, int(distance[y, x + 1]) + 1)
            distance[y, x] = best
    return distance


def _authored_edge_profile_coverage(
    edge_ownership: np.ndarray,
    width: int,
    height: int,
) -> np.ndarray | None:
    """Build a profile edge from the actual authored border ownership.

    TileSetter Sources can place a border anywhere inside a complete tile. The
    canonical Blob/Wang coverage is therefore not a safe proxy after Sources
    have been composed: it can put a second material band in the middle of a
    tile whose authored border already ends at the outer edge.
    """

    owned = np.asarray(edge_ownership, dtype=bool)
    if owned.shape != (height, width) or not np.any(owned) or np.all(owned):
        return None
    inside_distance = _pixel_distance_to_mask(owned)
    outside_distance = _pixel_distance_to_mask(~owned)
    signed_distance = np.where(owned, -outside_distance, inside_distance).astype(np.float32)
    axis = max(2, min(width, height))
    return np.clip(0.5 + signed_distance / axis, 0.0, 1.0)


def _organic_blob_corner_coverage(
    coverage: np.ndarray,
    mask: int,
    *,
    profile: TerrainEdgeProfile,
    variation: int,
    seed: int,
    inner_rounding: float = 0.5,
) -> np.ndarray:
    """Warp Blob corner arcs into asymmetric, port-safe organic contours."""

    source = np.asarray(coverage, dtype=np.float32)
    height, width = source.shape
    if variation <= 0 or mask in (0, 0xFF):
        return source.copy()

    output = source.copy()
    half_width = width / 2.0
    half_height = height / 2.0
    minimum_radius = max(1.0, min(half_width, half_height))
    size_scale = math.sqrt(max(2, min(width, height)) / 16.0)
    profile_scale = {
        "organic_neutral": 1.0,
        "grass_over_dirt": 1.08,
        "dirt_over_water": 0.88,
        "grass_over_water": 1.0,
    }.get(profile, 0.82)
    amplitude = (0.55, 1.0, 1.55)[variation - 1] * size_scale * profile_scale
    transition = max(0.55, 0.72 * size_scale) / minimum_radius
    digest = hashlib.sha256(f"blob-corner:{profile}:{seed}".encode()).digest()
    quadrants = (
        ("top_left", "top", "left", 0, width // 2, 0, height // 2, 1, 1),
        (
            "top_right",
            "top",
            "right",
            (width + 1) // 2,
            width,
            0,
            height // 2,
            -1,
            1,
        ),
        (
            "bottom_right",
            "bottom",
            "right",
            (width + 1) // 2,
            width,
            (height + 1) // 2,
            height,
            -1,
            -1,
        ),
        (
            "bottom_left",
            "bottom",
            "left",
            0,
            width // 2,
            (height + 1) // 2,
            height,
            1,
            -1,
        ),
    )
    for corner_index, (
        diagonal,
        first,
        second,
        x0,
        x1,
        y0,
        y1,
        step_x,
        step_y,
    ) in enumerate(quadrants):
        diagonal_on = bool(mask & _DIRECTION_BITS[diagonal])
        first_on = bool(mask & _DIRECTION_BITS[first])
        second_on = bool(mask & _DIRECTION_BITS[second])
        is_outer = not diagonal_on and not first_on and not second_on
        is_inner = not diagonal_on and first_on and second_on
        if diagonal_on:
            continue

        phase = digest[corner_index * 2] / 255.0 * (2.0 * math.pi)
        phase2 = digest[corner_index * 2 + 1] / 255.0 * (2.0 * math.pi)
        bias = (digest[16 + corner_index] / 255.0 - 0.5) * 0.55
        xs = np.arange(x0, x1, dtype=np.float64)
        ys = np.arange(y0, y1, dtype=np.float64)
        if step_x > 0:
            u = (xs + 0.5) / half_width
        else:
            u = (width - xs - 0.5) / half_width
        if step_y > 0:
            v = (ys + 0.5) / half_height
        else:
            v = (height - ys - 0.5) / half_height

        u_grid = u[None, :]
        v_grid = v[:, None]

        if is_outer:
            radial_x = 1.0 - u_grid
            radial_y = 1.0 - v_grid
            distance = np.sqrt(radial_x**2 + radial_y**2)
            # Use the same quarter-circle model as the clean rounded
            # pass. A min(u, v) field makes a square wedge; the radial
            # field gives the convex shoreline one broad arc.
            signed = 1.0 - distance
            angle = np.where(distance > 1e-6, np.arctan2(radial_y, radial_x), 0.0)
            port_envelope = np.maximum(0.0, np.sin(2.0 * angle)) ** 2.0
            broad_lobe = np.sin(angle + phase)
            secondary_lobe = np.cos(2.0 * angle + phase2)
            warp = (
                amplitude
                / minimum_radius
                * port_envelope
                * (bias + 0.68 * broad_lobe + 0.16 * secondary_lobe)
            )
        elif is_inner:
            # Gentle organic inner corner:
            # Starts from the clean bilinear boundary (u + v - u*v)
            corner_env = np.maximum(0.0, 1.0 - u_grid / 0.8) * np.maximum(0.0, 1.0 - v_grid / 0.8)
            angle = np.arctan2(v_grid, u_grid)
            broad_lobe = np.sin(2.0 * angle + phase)
            secondary_lobe = np.cos(3.0 * angle + phase2)
            warp = (
                amplitude
                * 0.08
                / minimum_radius
                * corner_env
                * (bias * 0.5 + 0.5 * broad_lobe + 0.2 * secondary_lobe)
            )
            output[y0:y1, x0:x1] = np.clip(
                u_grid + v_grid - u_grid * v_grid - 0.25 * max(0.0, min(1.0, float(inner_rounding))) * corner_env + warp,
                0.0,
                1.0,
            )
            continue
        else:
            radial_x = u_grid
            radial_y = v_grid
            distance = np.ones((len(ys), len(xs)), dtype=np.float64)
            signed = v_grid - 0.5 if second_on else u_grid - 0.5
            warp = 0.0

        output[y0:y1, x0:x1] = np.clip(0.5 + (signed + warp) / (2.0 * transition), 0.0, 1.0)

    # Broad convex fillets extend beyond a quadrant into both adjacent sides.
    # Their tangent stays at the authored quarter-tile inset, so increasing
    # the radius rounds the corner without moving the straight port.
    yy, xx = np.indices(source.shape, dtype=np.float32)
    radius = min(width, height) * 0.375
    for index, (_diagonal, first, second, _x0, _x1, _y0, _y1, sx, sy) in enumerate(quadrants):
        if mask & (_DIRECTION_BITS[first] | _DIRECTION_BITS[second]):
            continue
        local_x = xx + 0.5 if sx > 0 else width - xx - 0.5
        local_y = yy + 0.5 if sy > 0 else height - yy - 0.5
        dx = np.maximum(width * 0.25 + radius - local_x, 0.0)
        dy = np.maximum(height * 0.25 + radius - local_y, 0.0)
        angle = np.arctan2(dy, dx)
        phase = digest[index * 2] / 255.0 * 2.0 * math.pi
        warp = amplitude * 0.6 * np.sin(2.0 * angle) ** 2 * np.sin(angle + phase)
        signed = radius - np.hypot(dx, dy) + warp
        fillet = np.clip(0.5 + signed / (2.0 * max(0.55, 0.72 * size_scale)), 0.0, 1.0)
        output = np.minimum(output, fillet)

    # Curvature may vary inside the cell, but the complete outer ring remains
    # the canonical Blob port so every mask and visual bank can still meet.
    output[0, :] = source[0, :]
    output[-1, :] = source[-1, :]
    output[:, 0] = source[:, 0]
    output[:, -1] = source[:, -1]
    return output


def _organic_blob_coverage(
    coverage: np.ndarray,
    *,
    profile: TerrainEdgeProfile,
    variation: int,
    seed: int,
    exposed_directions: Sequence[str] | None = None,
    mask: int | None = None,
    inner_rounding: float = 0.5,
) -> np.ndarray:
    """Displace a smooth Blob boundary without making noisy pixel holes.

    The canonical coverage supplies topology; this pass converts it to a
    signed pixel distance and adds a multi-harmonic organic offset. Using a
    distance field keeps each contour connected, while the immutable outer
    ring guarantees byte-identical atlas ports for every variant.
    """

    source = np.asarray(coverage, dtype=np.float32)
    height, width = source.shape
    if variation <= 0 or profile in {"clean", "rounded_clean"}:
        return source.copy()
    if mask is not None:
        source = _organic_blob_corner_coverage(
            source,
            mask,
            profile=profile,
            variation=variation,
            seed=seed,
            inner_rounding=inner_rounding,
        )
    minimum_axis = max(2, min(width, height))
    ownership = source >= 0.5
    if not np.any(ownership) or np.all(ownership):
        return source.copy()

    inside_distance = _pixel_distance_to_mask(~ownership).astype(np.float32)
    outside_distance = _pixel_distance_to_mask(ownership).astype(np.float32)
    distance_signed = np.where(ownership, inside_distance, -outside_distance)
    # Keep the sub-pixel position from the analytical arc as well as the
    # integer distance. This lets a wave move a boundary smoothly
    # instead of waiting until a whole binary row flips at once.
    fractional_signed = (source - 0.5) * float(minimum_axis)
    signed = 0.58 * distance_signed + 0.42 * fractional_signed
    size_scale = math.sqrt(minimum_axis / 16.0)
    material_scale = {
        "organic_neutral": 0.95,
        "grass_over_dirt": 1.05,
        "dirt_over_water": 0.88,
        "grass_over_water": 1.00,
        "rounded_grass_tufts": 1.05,
        "rounded_dither": 0.75,
    }.get(profile, 0.95)
    displacement_pixels = min(
        2.8 * size_scale,
        (0.65, 0.95, 1.30)[variation - 1] * size_scale * material_scale,
    )
    digest = hashlib.sha256(f"blob-boundary:{profile}:{seed}".encode()).digest()
    yy, xx = np.indices((height, width), dtype=np.float32)
    border_distance = np.minimum.reduce(
        (xx, width - 1.0 - xx, yy, height - 1.0 - yy)
    )
    lock_width = max(1.0, minimum_axis / 16.0)
    port_envelope = np.clip(border_distance / lock_width, 0.0, 1.0)

    # Multi-harmonic wave for organic pixel-art clusters
    x = xx / max(1.0, width - 1.0)
    y = yy / max(1.0, height - 1.0)
    phase_x = digest[0] / 255.0 * (2.0 * math.pi)
    phase_y = digest[1] / 255.0 * (2.0 * math.pi)
    phase_x2 = digest[2] / 255.0 * (2.0 * math.pi)
    phase_y2 = digest[3] / 255.0 * (2.0 * math.pi)

    w1 = np.cos(2.0 * math.pi * x + phase_x) + np.cos(2.0 * math.pi * y + phase_y)
    w2 = 0.50 * (np.sin(4.0 * math.pi * x + phase_y) + np.sin(4.0 * math.pi * y + phase_x))
    w3 = 0.25 * (np.cos(6.0 * math.pi * x + phase_x2) + np.cos(6.0 * math.pi * y + phase_y2))
    wave = (w1 + w2 + w3) / 1.75

    # Fade only at the immutable outer ring. A fractional power keeps the
    # first interior row visibly wavy while still reaching exactly zero at
    # every shared port; the old linear envelope made straight shores read as
    # rigid lines at native 16px resolution.
    envelope = np.power(
        np.clip(np.sin(math.pi * x) * np.sin(math.pi * y), 0.0, 1.0),
        0.80,
    )
    near_boundary = np.abs(distance_signed) <= 1.5
    if mask is not None:
        # Preserve the continuous radial field, including its subpixel phase,
        # but only close to the boundary so deep interior pixels preserve their
        # true signed Euclidean distance and cannot be breached by displacement.
        subpixel = (source - 0.5) * (2.0 * max(0.55, 0.72 * size_scale))
        signed = np.where(near_boundary, subpixel, distance_signed)
    else:
        signed = np.where(ownership, inside_distance - 0.5, 0.5 - outside_distance)
    displaced = np.clip(
        0.5 + (signed + displacement_pixels * wave * envelope * port_envelope)
        / (2.0 * max(0.75, 0.90 * size_scale)),
        0.0,
        1.0,
    ).astype(np.float32)
    # Remove single-pixel tips and notches in the binary geometry, without
    # filtering or resampling any Source pixels. Keep two-neighbour staircase
    # corners intact and never edit the shared port ring.
    owned = displaced >= 0.5
    neighbors = (
        owned[:-2, 1:-1].astype(np.uint8) + owned[2:, 1:-1]
        + owned[1:-1, :-2] + owned[1:-1, 2:]
    )
    interior = displaced[1:-1, 1:-1]
    interior[neighbors <= 1] = np.minimum(interior[neighbors <= 1], 0.49)
    interior[neighbors >= 3] = np.maximum(interior[neighbors >= 3], 0.51)
    displaced[0, :] = source[0, :]
    displaced[-1, :] = source[-1, :]
    displaced[:, 0] = source[:, 0]
    displaced[:, -1] = source[:, -1]
    return cast(np.ndarray, displaced)


def _remap_blob_boundary_pixels(
    tile: Image.Image,
    authored_edge_ownership: np.ndarray,
    coverage: np.ndarray,
) -> Image.Image:
    """Materialize ownership changes using pixels from the authored Sources."""

    output = np.asarray(tile, dtype=np.uint8).copy()
    old_outside = np.asarray(authored_edge_ownership, dtype=bool)
    new_base = np.asarray(coverage, dtype=np.float32) >= 0.5
    # Authored border pixels are immutable. Organic variation may grow the
    # border into the base, but it never erases or recolours deliberate art.
    pending = ~new_base & ~old_outside
    known = old_outside.copy()
    samples = output.copy()
    for _step in range(max(output.shape[:2])):
        if not np.any(pending):
            break
        assigned = np.zeros_like(pending)
        candidates = (
            (known[:-1, :], (slice(1, None), slice(None)), (slice(None, -1), slice(None))),
            (known[1:, :], (slice(None, -1), slice(None)), (slice(1, None), slice(None))),
            (known[:, :-1], (slice(None), slice(1, None)), (slice(None), slice(None, -1))),
            (known[:, 1:], (slice(None), slice(None, -1)), (slice(None), slice(1, None))),
        )
        for neighbor_known, target_slice, source_slice in candidates:
            selectable = pending[target_slice] & neighbor_known & ~assigned[target_slice]
            output_view = output[target_slice]
            source_view = samples[source_slice]
            output_view[selectable] = source_view[selectable]
            assigned[target_slice] |= selectable
        if not np.any(assigned):
            break
        known |= assigned
        pending &= ~assigned
        samples = output.copy()
    return Image.fromarray(output, mode="RGBA")


def _fill_transparent_edge_source(
    image: Image.Image,
    fallback: Image.Image,
) -> Image.Image:
    """Make a complete exterior sample from a partial authored Border Source."""

    output = np.asarray(image, dtype=np.uint8).copy()
    fallback_pixels = np.asarray(fallback, dtype=np.uint8)
    known = output[..., 3] != 0
    if np.all(known):
        return Image.fromarray(output, mode="RGBA")
    samples = output.copy()
    pending = ~known
    for _step in range(max(output.shape[:2])):
        if not np.any(pending):
            break
        assigned = np.zeros_like(pending)
        candidates = (
            (known[:-1, :], (slice(1, None), slice(None)), (slice(None, -1), slice(None))),
            (known[1:, :], (slice(None, -1), slice(None)), (slice(1, None), slice(None))),
            (known[:, :-1], (slice(None), slice(1, None)), (slice(None), slice(None, -1))),
            (known[:, 1:], (slice(None), slice(None, -1)), (slice(None), slice(1, None))),
        )
        for neighbor_known, target_slice, source_slice in candidates:
            selectable = pending[target_slice] & neighbor_known & ~assigned[target_slice]
            output_view = output[target_slice]
            source_view = samples[source_slice]
            output_view[selectable] = source_view[selectable]
            assigned[target_slice] |= selectable
        if not np.any(assigned):
            break
        known |= assigned
        pending &= ~assigned
        samples = output.copy()
    output[pending] = fallback_pixels[pending]
    return Image.fromarray(output, mode="RGBA")


def _dual_grid_bitmap_mask(
    mask: int,
    width: int,
    height: int,
    *,
    profile: TerrainEdgeProfile = "clean",
    variation: int = 0,
    seed: int = 0,
) -> np.ndarray:
    """Render one Dual Grid role with a deterministic material-pair silhouette."""

    return (
        _dual_grid_profile_coverage(
            mask,
            width,
            height,
            kind="dual_grid_15",
            profile=profile,
            variation=variation,
            seed=seed,
        )
        >= 0.5
    )


def _tone_dual_grid_band(
    output: np.ndarray,
    band: np.ndarray,
    samples: np.ndarray,
    *,
    target: tuple[int, int, int],
    amount: float,
) -> None:
    """Tone selected RGB pixels without filtering, moving samples, or changing alpha."""

    if not np.any(band):
        return
    source_rgb = samples[..., :3].astype(np.float32)
    target_rgb = np.asarray(target, dtype=np.float32)
    toned = np.rint(source_rgb * (1.0 - amount) + target_rgb * amount)
    output[..., :3][band] = np.clip(toned, 0, 255).astype(np.uint8)[band]


def _blob_material_layers(
    pixels: np.ndarray,
    owned: np.ndarray,
    *,
    profile: TerrainEdgeProfile,
    seed: int,
    allowed: np.ndarray | None = None,
    fringe_source: np.ndarray | None = None,
) -> np.ndarray:
    """Paint discrete native bands and whole clusters on final ownership.

    Geometry and material have independent fields. Shades are explicit dark
    levels of the original sample, never spatial filtering of Source pixels.
    """
    output = pixels.copy()
    height, width = owned.shape
    outside_distance = _pixel_distance_to_mask(owned)
    inside_distance = _pixel_distance_to_mask(~owned)
    editable = np.ones_like(owned)
    editable[[0, -1], :] = False
    editable[:, [0, -1]] = False
    if allowed is not None and min(width, height) > 32:
        editable &= allowed

    def shade(region: np.ndarray, factor: float) -> None:
        selected = region & editable
        output[..., :3][selected] = np.rint(
            pixels[..., :3][selected].astype(np.float32) * factor
        ).clip(0, 255).astype(np.uint8)

    # Distances are measured from the actual binary contour, so these bands
    # cannot float away from their shore when a variant changes its shape.
    contact_width = 1 if min(width, height) <= 32 else 2
    contact = ~owned & (outside_distance <= contact_width)
    if profile == "grass_over_dirt" and fringe_source is not None:
        # Procedural grass-over-dirt gets a continuous dark grass fringe. It
        # is copied from the generated interior material, never blended with
        # an authored Source; authored sets retain their source-owned shade.
        selected = contact & editable
        output[..., :3][selected] = np.rint(
            fringe_source[..., :3][selected].astype(np.float32) * 0.78
        ).clip(0, 255).astype(np.uint8)
    else:
        shade(contact, 0.70 if profile == "grass_over_dirt" else 0.64)
    yy, xx = np.indices(owned.shape)
    phase = (seed % 101) / 101.0 * 2.0 * math.pi
    broad = np.cos(xx / width * 2.0 * math.pi + phase)
    broad += np.sin(yy / height * 2.0 * math.pi + phase * 0.7)
    shade(~owned & (outside_distance == contact_width + 1) & (broad > -0.3), 0.86)

    # Jittered whole clusters give the material a mottled surface. Every mark
    # stays on one side of the contour; no clipped singleton tufts are emitted.
    digest = hashlib.sha256(f"blob-material:{profile}:{seed}".encode()).digest()
    for y in range(1, height - 3, 3):
        for x in range(1, width - 3, 3):
            token = digest[(x + 7 * y) % len(digest)]
            px, py = x + token % 2, y + (token // 2) % 2
            region = (slice(py, py + 2), slice(px, px + 2))
            land = bool(owned[py, px])
            if not np.all(owned[region] == land) or not np.all(editable[region]):
                continue
            # Shadows have priority over surface mottling.
            if not land and np.any(outside_distance[region] <= contact_width + 1):
                continue
            factor = (0.92, 1.05, 0.97, 1.08)[token % 4]
            if land and profile != "dirt_over_water" and np.all(inside_distance[region] <= 4):
                factor = 1.10 if token % 2 else 0.90
            if land and profile != "dirt_over_water":
                skip_y = py + (token // 4) % 2
                skip_x = px + (token // 8) % 2
                sub_out = np.rint(
                    pixels[py:py + 2, px:px + 2, :3].astype(np.float32) * factor
                ).clip(0, 255).astype(np.uint8)
                output[py:py + 2, px:px + 2, :3] = sub_out
                output[skip_y, skip_x, :3] = pixels[skip_y, skip_x, :3]
            else:
                output[py:py + 2, px:px + 2, :3] = np.rint(
                    pixels[py:py + 2, px:px + 2, :3].astype(np.float32) * factor
                ).clip(0, 255).astype(np.uint8)
    return output


def _render_dual_grid_pixels(
    inside: np.ndarray,
    outside: np.ndarray,
    mask: int,
    *,
    kind: TerrainPatternKind = "dual_grid_15",
    profile: TerrainEdgeProfile = "clean",
    variation: int = 0,
    seed: int = 0,
    base_output: np.ndarray | None = None,
    coverage_override: np.ndarray | None = None,
    profile_mask: np.ndarray | None = None,
    material_fringe: np.ndarray | None = None,
    corner_radius: int = 0,
    retro_outline: bool = False,
    inner_rounding: float = 0.5,
) -> np.ndarray:
    """Compose a pattern role with material-specific pixel-art edge bands."""

    normalizer = (
        _normalize_dual_grid_edge_style
        if kind == "dual_grid_15"
        else _normalize_terrain_edge_style
    )
    profile, variation, seed = normalizer(profile, variation, seed)
    height, width = inside.shape[:2]
    coverage = (
        _dual_grid_profile_coverage(
            mask,
            width,
            height,
            kind=kind,
            profile=profile,
            variation=variation,
            seed=seed,
            corner_radius=corner_radius,
            inner_rounding=inner_rounding,
        )
        if coverage_override is None
        else np.asarray(coverage_override, dtype=np.float32)
    )
    if coverage.shape != (height, width):
        raise ValueError("Terrain edge coverage must match the tile dimensions")
    ownership = coverage >= 0.5
    output = (
        np.asarray(base_output, dtype=np.uint8).copy()
        if base_output is not None
        else np.where(ownership[..., None], inside, outside).astype(np.uint8)
    )
    # The first/last atlas pixels are the shared seam of adjacent roles. Keep
    # their original source pixels for non-Dual patterns; otherwise a profile
    # can tone one side of a seam while its neighbour remains untouched (most
    # visible on Blob/Sides where the coverage curve is not corner-linear).
    seam_reference = output.copy() if kind != "dual_grid_15" else None
    profile_reference = output.copy() if profile_mask is not None else None
    normalized_profile_mask: np.ndarray | None = None
    if profile_mask is not None:
        normalized_profile_mask = np.asarray(profile_mask, dtype=bool)
        if normalized_profile_mask.shape != (height, width):
            raise ValueError("Terrain edge profile mask must match the tile dimensions")
    if (
        profile in {"clean", "rounded_clean"}
        or variation == 0
        or mask in _profile_terminal_masks(kind)
    ):
        if retro_outline and mask not in _profile_terminal_masks(kind):
            img = _apply_retro_outline(Image.fromarray(output, mode="RGBA"), ownership)
            output = np.asarray(img, dtype=np.uint8)
        return output

    if profile == "organic_neutral":
        if retro_outline and mask not in _profile_terminal_masks(kind):
            img = _apply_retro_outline(Image.fromarray(output, mode="RGBA"), ownership)
            output = np.asarray(img, dtype=np.uint8)
        return output

    if kind == "blob_47":
        return _blob_material_layers(
            output,
            ownership,
            profile=profile,
            seed=seed,
            allowed=normalized_profile_mask,
            fringe_source=material_fringe,
        )

    minimum_axis = max(2, min(width, height))
    size_scale = min(1.75, max(1.0, minimum_axis / 16.0))
    signed_pixels = (coverage - 0.5) * minimum_axis
    band_field = _dual_grid_texture_field(
        width,
        height,
        profile=profile,
        seed=seed ^ 0x5A17,
    )
    grain_field = _dual_grid_texture_field(
        width,
        height,
        profile=profile,
        seed=seed ^ 0x2D6B,
    )
    width_modulation = 1.0 + 0.28 * band_field
    style_limit = minimum_axis * 0.44
    level = variation - 1

    if profile == "dirt_over_water":
        shadow_width = np.minimum(
            (1.0, 1.55, 2.2)[level] * size_scale * width_modulation,
            style_limit,
        )
        water_shadow = (signed_pixels < 0.0) & (signed_pixels >= -shadow_width)
        deep_shadow = water_shadow & (signed_pixels >= -shadow_width * 0.48)
        _tone_dual_grid_band(
            output,
            water_shadow,
            outside,
            target=(28, 72, 78),
            amount=(0.20, 0.28, 0.34)[level],
        )
        _tone_dual_grid_band(
            output,
            deep_shadow,
            outside,
            target=(18, 52, 58),
            amount=(0.30, 0.40, 0.50)[level],
        )

        rim_width = np.minimum(
            (0.80, 1.05, 1.20)[level] * min(size_scale, 1.35) * width_modulation,
            style_limit,
        )
        rim = (signed_pixels >= 0.0) & (signed_pixels < rim_width)
        rim &= grain_field > (-1.1, -0.92, -0.72)[level]
        _tone_dual_grid_band(
            output,
            rim,
            outside,
            target=(235, 250, 247),
            amount=(0.58, 0.70, 0.80)[level],
        )

        light_width = (0.75, 1.25, 1.75)[level] * size_scale * width_modulation
        light_end = np.minimum(rim_width + light_width, style_limit)
        light_bank = (signed_pixels >= rim_width) & (signed_pixels < light_end)
        _tone_dual_grid_band(
            output,
            light_bank,
            inside,
            target=(220, 155, 105),
            amount=(0.18, 0.28, 0.38)[level],
        )
        bank_glints = light_bank & (grain_field > (0.48, 0.25, 0.05)[level])
        _tone_dual_grid_band(
            output,
            bank_glints,
            inside,
            target=(235, 188, 140),
            amount=(0.22, 0.36, 0.55)[level],
        )

        dark_width = (0.35, 0.80, 1.25)[level] * size_scale * width_modulation
        dark_end = np.minimum(light_end + dark_width, style_limit)
        dark_bank = (signed_pixels >= light_end) & (signed_pixels < dark_end)
        _tone_dual_grid_band(
            output,
            dark_bank,
            inside,
            target=(65, 48, 40),
            amount=(0.14, 0.28, 0.42)[level],
        )
    elif profile == "grass_over_water":
        shadow_width = np.minimum(
            (0.9, 1.4, 2.0)[level] * size_scale * width_modulation,
            style_limit,
        )
        water_shadow = (signed_pixels < 0.0) & (signed_pixels >= -shadow_width)
        _tone_dual_grid_band(
            output,
            water_shadow,
            outside,
            target=(24, 68, 76),
            amount=(0.22, 0.32, 0.42)[level],
        )

        wet_width = np.minimum(
            (0.65, 0.90, 1.10)[level] * min(size_scale, 1.35) * width_modulation,
            style_limit,
        )
        wet_edge = (signed_pixels >= 0.0) & (signed_pixels < wet_width)
        wet_edge &= grain_field > (0.12, -0.12, -0.35)[level]
        _tone_dual_grid_band(
            output,
            wet_edge,
            outside,
            target=(225, 248, 240),
            amount=(0.42, 0.55, 0.66)[level],
        )

        root_width = (1.0, 1.55, 2.25)[level] * size_scale * width_modulation
        root_end = np.minimum(wet_width + root_width, style_limit)
        grass_roots = (signed_pixels >= wet_width) & (signed_pixels < root_end)
        _tone_dual_grid_band(
            output,
            grass_roots,
            inside,
            target=(30, 75, 45),
            amount=(0.20, 0.29, 0.38)[level],
        )
        grass_glints = grass_roots & (grain_field > (0.48, 0.30, 0.12)[level])
        _tone_dual_grid_band(
            output,
            grass_glints,
            inside,
            target=(175, 220, 115),
            amount=(0.14, 0.20, 0.27)[level],
        )
    else:  # grass_over_dirt
        dirt_width = np.minimum(
            (0.9, 1.4, 1.95)[level] * size_scale * width_modulation,
            style_limit,
        )
        dirt_shadow = (signed_pixels < 0.0) & (signed_pixels >= -dirt_width)
        _tone_dual_grid_band(
            output,
            dirt_shadow,
            outside,
            target=(62, 43, 34),
            amount=(0.18, 0.28, 0.38)[level],
        )

        root_width = np.minimum(
            (0.85, 1.35, 1.85)[level] * size_scale * width_modulation,
            style_limit,
        )
        grass_roots = (signed_pixels >= 0.0) & (signed_pixels < root_width)
        _tone_dual_grid_band(
            output,
            grass_roots,
            inside,
            target=(35, 76, 38),
            amount=(0.18, 0.28, 0.37)[level],
        )
        glint_width = (0.65, 0.95, 1.30)[level] * size_scale * width_modulation
        glint_end = np.minimum(root_width + glint_width, style_limit)
        grass_glints = (signed_pixels >= root_width) & (signed_pixels < glint_end)
        grass_glints &= grain_field > (0.38, 0.18, -0.02)[level]
        _tone_dual_grid_band(
            output,
            grass_glints,
            inside,
            target=(175, 215, 105),
            amount=(0.14, 0.21, 0.29)[level],
        )

    if profile_reference is not None and normalized_profile_mask is not None:
        output[~normalized_profile_mask] = profile_reference[~normalized_profile_mask]
    if seam_reference is not None:
        output[0, ...] = seam_reference[0, ...]
        output[-1, ...] = seam_reference[-1, ...]
        output[:, 0, ...] = seam_reference[:, 0, ...]
        output[:, -1, ...] = seam_reference[:, -1, ...]
    if retro_outline and mask not in _profile_terminal_masks(kind):
        img = _apply_retro_outline(Image.fromarray(output, mode="RGBA"), ownership)
        output = np.asarray(img, dtype=np.uint8)
    return output


def _blob_quadrant_values(mask: int, right: bool, bottom: bool) -> tuple[float, ...]:
    if not right and not bottom:
        names = ("top_left", "top", "left")
    elif right and not bottom:
        names = ("top_right", "top", "right")
    elif not right and bottom:
        names = ("bottom_left", "bottom", "left")
    else:
        names = ("bottom_right", "bottom", "right")
    return tuple(1.0 if mask & _DIRECTION_BITS[name] else 0.0 for name in names)


@lru_cache(maxsize=512)
def _cached_blob_bitmap_coverage(mask: int, width: int, height: int) -> np.ndarray:
    output = np.empty((height, width), dtype=np.float32)
    half_w = width // 2
    half_h = height // 2
    xs_left = (np.arange(half_w, dtype=np.float32) + 0.5) / (width / 2.0)
    xs_right = (width - (np.arange(half_w, width, dtype=np.float32) + 0.5)) / (width / 2.0)
    ys_top = (np.arange(half_h, dtype=np.float32) + 0.5) / (height / 2.0)
    ys_bottom = (height - (np.arange(half_h, height, dtype=np.float32) + 0.5)) / (height / 2.0)

    quads = [
        (slice(0, half_h), slice(0, half_w), False, False, xs_left, ys_top),
        (slice(0, half_h), slice(half_w, width), True, False, xs_right, ys_top),
        (slice(half_h, height), slice(0, half_w), False, True, xs_left, ys_bottom),
        (slice(half_h, height), slice(half_w, width), True, True, xs_right, ys_bottom),
    ]
    for y_sl, x_sl, right, bottom, u_1d, v_1d in quads:
        diag, horiz, vert = _blob_quadrant_values(mask, right, bottom)
        u = u_1d[None, :]
        v = v_1d[:, None]
        output[y_sl, x_sl] = (
            diag * (1.0 - u) * (1.0 - v)
            + horiz * u * (1.0 - v)
            + vert * (1.0 - u) * v
            + u * v
        )
    return output


def _blob_bitmap_coverage(mask: int, width: int, height: int) -> np.ndarray:
    return _cached_blob_bitmap_coverage(mask, width, height).copy()


def _blob_bitmap_mask(mask: int, width: int, height: int) -> np.ndarray:
    return _blob_bitmap_coverage(mask, width, height) >= 0.5


def _tile_neighbors(kind: TerrainPatternKind, mask: int) -> tuple[str, ...]:
    if kind == "dual_grid_15":
        return tuple(name for index, name in enumerate(_WANG_CORNERS) if mask & (1 << index))
    if kind in ("wang_16", "sides_16"):
        return tuple(
            name
            for index, name in enumerate(("top", "right", "bottom", "left"))
            if mask & (1 << index)
        )
    return tuple(name for name in _DIRECTIONS if mask & _DIRECTION_BITS[name])


def _relevant_directions(kind: TerrainPatternKind) -> tuple[str, ...]:
    if kind == "dual_grid_15":
        return _WANG_CORNERS
    if kind in ("wang_16", "sides_16"):
        return ("top", "right", "bottom", "left")
    return _DIRECTIONS


def _profile_terminal_masks(kind: TerrainPatternKind) -> tuple[int, int]:
    """Return the empty/full roles that should never receive an edge band."""

    if kind == "blob_47":
        return 0, 0xFF
    return 0, 0x0F


def _sides_blob_mask(mask: int) -> int:
    value = 0
    for index, name in enumerate(("top", "right", "bottom", "left")):
        if mask & (1 << index):
            value |= _DIRECTION_BITS[name]
    return value


def _placeholder_tile(
    size: tuple[int, int],
    *,
    kind: TerrainPatternKind,
    mask: int,
) -> Image.Image:
    width, height = size
    tile = Image.new("RGBA", size, (22, 29, 43, 255))
    draw = ImageDraw.Draw(tile)
    step = max(1, min(width, height) // 6)
    for y in range(0, height, step):
        for x in range(0, width, step):
            if (x // step + y // step) % 2 == 0:
                draw.rectangle(
                    (x, y, min(width - 1, x + step - 1), min(height - 1, y + step - 1)),
                    fill=(31, 41, 58, 255),
                )
    neighbors = set(_tile_neighbors(kind, mask))
    cell = max(1, min(width, height) // 5)
    origin_x = (width - cell * 3) // 2
    origin_y = (height - cell * 3) // 2
    positions = {
        "top_left": (0, 0),
        "top": (1, 0),
        "top_right": (2, 0),
        "left": (0, 1),
        "right": (2, 1),
        "bottom_left": (0, 2),
        "bottom": (1, 2),
        "bottom_right": (2, 2),
    }
    for name, (column, row) in positions.items():
        enabled = name in neighbors
        color = (79, 220, 188, 255) if enabled else (94, 104, 127, 255)
        x = origin_x + column * cell
        y = origin_y + row * cell
        draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=color)
    center_x = origin_x + cell
    center_y = origin_y + cell
    draw.rectangle(
        (center_x, center_y, center_x + cell - 1, center_y + cell - 1),
        fill=(255, 89, 139, 255),
    )
    return tile


def render_terrain_bitmask_template(
    kind: TerrainPatternKind,
    *,
    tile_size: int = 48,
) -> Image.Image:
    """Render the canonical Godot bitmap guide in the same layout as exports."""

    logical_size = max(12, int(tile_size))
    layout = terrain_pattern_layout(kind)
    image = Image.new(
        "RGBA",
        (len(layout[0]) * logical_size, len(layout) * logical_size),
        (255, 255, 255, 255),
    )
    draw = ImageDraw.Draw(image)
    on = (255, 57, 106, 255)
    grid = (183, 57, 255, 255)
    ignored = (83, 126, 189, 255)
    for row, layout_row in enumerate(layout):
        for column, mask in enumerate(layout_row):
            ox = column * logical_size
            oy = row * logical_size
            if mask is None:
                draw.rectangle(
                    (ox, oy, ox + logical_size - 1, oy + logical_size - 1),
                    outline=grid,
                    width=1,
                )
                continue
            if kind == "dual_grid_15":
                half = logical_size // 2
                quadrants = (
                    (0, 0, 1),
                    (half, 0, 2),
                    (half, half, 4),
                    (0, half, 8),
                )
                for dx, dy, bit in quadrants:
                    if mask & bit:
                        draw.rectangle(
                            (
                                ox + dx,
                                oy + dy,
                                ox + dx + half - 1,
                                oy + dy + half - 1,
                            ),
                            fill=on,
                        )
            else:
                step = logical_size / 3.0
                positions = {
                    "top_left": (0, 0),
                    "top": (1, 0),
                    "top_right": (2, 0),
                    "left": (0, 1),
                    "right": (2, 1),
                    "bottom_left": (0, 2),
                    "bottom": (1, 2),
                    "bottom_right": (2, 2),
                }
                neighbors = set(_tile_neighbors(kind, mask))
                for direction, (inner_column, inner_row) in positions.items():
                    x0 = ox + round(inner_column * step)
                    y0 = oy + round(inner_row * step)
                    x1 = ox + round((inner_column + 1) * step) - 1
                    y1 = oy + round((inner_row + 1) * step) - 1
                    if kind in ("sides_16", "wang_16") and "_" in direction:
                        draw.rectangle((x0, y0, x1, y1), fill=ignored)
                        continue
                    if direction in neighbors:
                        draw.rectangle((x0, y0, x1, y1), fill=on)
                center_start = round(step)
                center_end = round(step * 2) - 1
                draw.rectangle(
                    (
                        ox + center_start,
                        oy + center_start,
                        ox + center_end,
                        oy + center_end,
                    ),
                    fill=on,
                )
            draw.rectangle(
                (ox, oy, ox + logical_size - 1, oy + logical_size - 1),
                outline=grid,
                width=1,
            )
    return image


def build_manual_terrain_pattern(
    atlas: Image.Image,
    grid: TilesetGrid,
    assignments: Mapping[int, int],
    *,
    kind: TerrainPatternKind = "blob_47",
    columns: int | None = None,
    background_source: int | None = None,
) -> TerrainPatternResult:
    """Build a role-ordered preview/export atlas from manual source-tile assignments.

    A Dual Grid also needs an explicit background Source for its physical
    mask-0 TileMapDual cell; its 15 role assignments alone are not enough.
    """

    _validate_dual_grid_size(kind, (grid.tile_width, grid.tile_height))
    sources = slice_tileset(atlas, grid)
    source_by_index = {source.index: source for source in sources}
    if kind == "dual_grid_15" and background_source is None:
        raise ValueError("Dual Grid manual patterns require background_source")
    dual_background = (
        source_by_index.get(int(background_source)) if background_source is not None else None
    )
    if kind == "dual_grid_15" and dual_background is None:
        raise ValueError("Dual Grid background_source references a missing tile")
    masks = terrain_pattern_masks(kind)
    unknown_masks = set(int(mask) for mask in assignments) - set(masks)
    if unknown_masks:
        raise ValueError(f"Assignments contain unsupported masks: {sorted(unknown_masks)}")
    positions, column_count, row_count = _role_positions(kind, columns)
    output = Image.new(
        "RGBA",
        (column_count * grid.tile_width, row_count * grid.tile_height),
        (0, 0, 0, 0),
    )
    rgba = atlas.convert("RGBA")
    roles: list[TerrainPatternTile] = []
    for index, mask in enumerate(masks):
        source_index = assignments.get(mask)
        source = source_by_index.get(int(source_index)) if source_index is not None else None
        if source_index is not None and source is None:
            raise ValueError(f"Assignment for mask {mask} references missing tile {source_index}")
        tile = (
            rgba.crop(source.bounds)
            if source is not None
            else _placeholder_tile(
                (grid.tile_width, grid.tile_height),
                kind=kind,
                mask=mask,
            )
        )
        column, row = positions[mask]
        _place_pattern_tile(
            output,
            tile,
            (column * grid.tile_width, row * grid.tile_height),
            kind=kind,
        )
        roles.append(
            TerrainPatternTile(
                index=index,
                mask=mask,
                column=column,
                row=row,
                neighbors=_tile_neighbors(kind, mask),
                source_index=int(source_index) if source_index is not None else None,
            )
        )
    if dual_background is not None:
        _place_dual_grid_background(
            output,
            rgba.crop(dual_background.bounds),
            (grid.tile_width, grid.tile_height),
        )
    return TerrainPatternResult(
        kind=kind,
        mode=_terrain_mode(kind),
        image=output,
        tile_width=grid.tile_width,
        tile_height=grid.tile_height,
        columns=column_count,
        rows=row_count,
        tiles=tuple(roles),
    )


def _source_image(
    atlas: Image.Image,
    grid: TilesetGrid,
    source_index: int,
) -> Image.Image:
    sources = {source.index: source for source in slice_tileset(atlas, grid)}
    source = sources.get(int(source_index))
    if source is None:
        raise ValueError(f"Missing source tile {source_index}")
    return atlas.convert("RGBA").crop(source.bounds)


def _transform_layer(
    image: Image.Image,
    size: tuple[int, int],
    *,
    quarter_turns: int = 0,
    flip_x: bool = False,
    flip_y: bool = False,
) -> Image.Image:
    layer = _fit_source(image, size)
    if flip_x:
        layer = layer.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_y:
        layer = layer.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    turns = int(quarter_turns) % 4
    if turns == 1:
        layer = layer.transpose(Image.Transpose.ROTATE_270)
    elif turns == 2:
        layer = layer.transpose(Image.Transpose.ROTATE_180)
    elif turns == 3:
        layer = layer.transpose(Image.Transpose.ROTATE_90)
    return _fit_source(layer, size)


def _edge_transform_turns(direction: str, transform: Mapping[str, object]) -> int:
    """Return TileSetter's automatic side orientation plus user rotation.

    Border Sources are authored in the canonical top-facing orientation.
    TileSetter rotates that Source automatically for right, bottom, and left
    borders; the configured rotation is an additional adjustment.
    """

    automatic = {"top": 0, "right": 1, "bottom": 2, "left": 3}[direction]
    return automatic + _object_int(transform.get("rotation"), 0)


def _fragment_bounds(
    fragment: Mapping[str, object],
    atlas_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    """Validate and return an arbitrary pixel selection from a source image."""

    if (
        fragment.get("x") is not None
        and fragment.get("y") is not None
        and fragment.get("width") is not None
        and fragment.get("height") is not None
    ):
        rx = fragment.get("x")
        ry = fragment.get("y")
        rw = fragment.get("width")
        rh = fragment.get("height")
    else:
        rect = fragment.get("rect")
        if (
            isinstance(rect, (list, tuple))
            and len(rect) == 4
            and all(isinstance(v, (int, float)) for v in rect)
        ):
            rx, ry, rw, rh = rect
        else:
            rx = fragment.get("x")
            ry = fragment.get("y")
            rw = fragment.get("width")
            rh = fragment.get("height")
    x = max(0, _object_int(rx, 0))
    y = max(0, _object_int(ry, 0))
    width = max(1, _object_int(rw, 1))
    height = max(1, _object_int(rh, 1))
    right = min(atlas_size[0], x + width)
    bottom = min(atlas_size[1], y + height)
    if x >= right or y >= bottom:
        raise ValueError("Fragment bounds fall outside the source image")
    return (x, y, right, bottom)


def _object_int(value: object, default: int = 0) -> int:
    if isinstance(value, (int, float, str)):
        return int(value)
    return default


def _object_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    return default


def _render_fragment_layers(
    atlas: Image.Image,
    fragments: Mapping[str, Mapping[str, object]],
    layers: Sequence[Mapping[str, object]],
    size: tuple[int, int],
) -> Image.Image:
    """Composite arbitrary source-image fragments onto one pixel-perfect tile."""

    output = Image.new("RGBA", size, (0, 0, 0, 0))
    rgba = atlas.convert("RGBA")
    for layer in layers:
        fragment_id = str(layer.get("fragmentId", ""))
        fragment = fragments.get(fragment_id)
        if fragment is None or layer.get("visible", True) is False:
            continue
        piece = rgba.crop(_fragment_bounds(fragment, rgba.size))
        if bool(layer.get("flipX", False)):
            piece = piece.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if bool(layer.get("flipY", False)):
            piece = piece.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        turns = _object_int(layer.get("rotation"), 0) % 4
        if turns == 1:
            piece = piece.transpose(Image.Transpose.ROTATE_270)
        elif turns == 2:
            piece = piece.transpose(Image.Transpose.ROTATE_180)
        elif turns == 3:
            piece = piece.transpose(Image.Transpose.ROTATE_90)
        opacity = max(0.0, min(1.0, _object_float(layer.get("opacity"), 1.0)))
        if opacity < 1.0:
            alpha = piece.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            piece.putalpha(alpha)
        output.alpha_composite(
            piece,
            (
                _object_int(layer.get("x"), 0),
                _object_int(layer.get("y"), 0),
            ),
        )
    return output


def build_fragment_terrain_pattern(
    atlas: Image.Image,
    *,
    tile_size: tuple[int, int],
    fragments: Sequence[Mapping[str, object]],
    master_layers: Sequence[Mapping[str, object]],
    semantic_roles: Mapping[str, str | None],
    variant_overrides: Mapping[int, Sequence[Mapping[str, object]]] | None = None,
    kind: TerrainPatternKind = "blob_47",
    columns: int | None = None,
) -> TerrainPatternResult:
    """Generate a terrain from freely cropped fragments and editable layer recipes.

    Semantic edge and corner layers are authored once in their canonical
    orientation (top or top-left) and rotated around the complete tile for the
    remaining directions. A variant override is an exact layer recipe for one
    generated mask, making every automatic result manually correctable.
    """

    size = (max(1, int(tile_size[0])), max(1, int(tile_size[1])))
    _validate_dual_grid_size(kind, size)
    if kind == "dual_grid_15":
        raise ValueError(
            "Dual Grid requires two complete textures; use the TileSetter or smart builder"
        )
    fragment_map = {
        str(fragment.get("id", "")): fragment
        for fragment in fragments
        if str(fragment.get("id", ""))
    }
    layer_by_id = {
        str(layer.get("id", "")): layer for layer in master_layers if str(layer.get("id", ""))
    }
    semantic_layer_ids = {
        str(layer_id)
        for layer_id in semantic_roles.values()
        if layer_id is not None and str(layer_id)
    }
    base_layers = [
        layer
        for layer in master_layers
        if str(layer.get("id", "")) not in semantic_layer_ids
        or str(layer.get("id", "")) == str(semantic_roles.get("center") or "")
    ]
    base = _render_fragment_layers(atlas, fragment_map, base_layers, size)

    def semantic_overlay(name: str) -> Image.Image | None:
        layer_id = semantic_roles.get(name)
        layer = layer_by_id.get(str(layer_id)) if layer_id else None
        if layer is None:
            return None
        return _render_fragment_layers(atlas, fragment_map, [layer], size)

    edge = semantic_overlay("edge")
    outer_corner = semantic_overlay("outerCorner")
    inner_corner = semantic_overlay("innerCorner")
    center_layer_id = str(semantic_roles.get("center") or "")
    ready = center_layer_id in layer_by_id and edge is not None
    overrides = {int(mask): list(layers) for mask, layers in (variant_overrides or {}).items()}
    masks = terrain_pattern_masks(kind)
    unknown_masks = set(overrides) - set(masks)
    if unknown_masks:
        raise ValueError(f"Overrides contain unsupported masks: {sorted(unknown_masks)}")
    positions, column_count, row_count = _role_positions(kind, columns)
    output = Image.new(
        "RGBA",
        (column_count * size[0], row_count * size[1]),
        (0, 0, 0, 0),
    )
    directions = ("top", "right", "bottom", "left")
    corner_rules = (
        ("top_left", "top", "left", 0),
        ("top_right", "top", "right", 1),
        ("bottom_right", "bottom", "right", 2),
        ("bottom_left", "bottom", "left", 3),
    )
    roles: list[TerrainPatternTile] = []
    for index, mask in enumerate(masks):
        override_layers = overrides.get(mask)
        if override_layers is not None:
            tile = _render_fragment_layers(
                atlas,
                fragment_map,
                override_layers,
                size,
            )
        elif ready:
            neighbors = set(_tile_neighbors(kind, mask))
            if kind == "dual_grid_15":
                corner_neighbors = neighbors
                neighbors = {
                    direction
                    for direction, corners in {
                        "top": ("top_left", "top_right"),
                        "right": ("top_right", "bottom_right"),
                        "bottom": ("bottom_right", "bottom_left"),
                        "left": ("bottom_left", "top_left"),
                    }.items()
                    if all(corner in corner_neighbors for corner in corners)
                }
            tile = base.copy()
            assert edge is not None
            for direction_index, direction in enumerate(directions):
                if direction not in neighbors:
                    tile.alpha_composite(
                        _transform_layer(edge, size, quarter_turns=direction_index)
                    )
            for diagonal, first, second, turns in corner_rules:
                if outer_corner is not None and first not in neighbors and second not in neighbors:
                    tile.alpha_composite(_transform_layer(outer_corner, size, quarter_turns=turns))
                elif (
                    inner_corner is not None
                    and first in neighbors
                    and second in neighbors
                    and diagonal not in neighbors
                ):
                    tile.alpha_composite(_transform_layer(inner_corner, size, quarter_turns=turns))
        else:
            tile = _placeholder_tile(size, kind=kind, mask=mask)
        column, row = positions[mask]
        _place_pattern_tile(
            output,
            tile,
            (column * size[0], row * size[1]),
            kind=kind,
        )
        roles.append(
            TerrainPatternTile(
                index=index,
                mask=mask,
                column=column,
                row=row,
                neighbors=_tile_neighbors(kind, mask),
                source_index=0 if ready or override_layers is not None else None,
                generated=override_layers is None and ready,
                override_source_index=0 if override_layers is not None else None,
            )
        )
    return TerrainPatternResult(
        kind=kind,
        mode=_terrain_mode(kind),
        image=output,
        tile_width=size[0],
        tile_height=size[1],
        columns=column_count,
        rows=row_count,
        tiles=tuple(roles),
    )


def _tilesetter_source_image(
    atlas: Image.Image,
    sources: Sequence[Mapping[str, object]],
    source_id: str | None,
    size: tuple[int, int],
) -> Image.Image | None:
    if not source_id:
        return None
    source = next(
        (item for item in sources if str(item.get("id", "")) == source_id),
        None,
    )
    if source is None:
        return None
    try:
        bounds = _fragment_bounds(source, atlas.size)
    except (ValueError, IndexError):
        return None
    cropped = atlas.convert("RGBA").crop(bounds)
    if cropped.getextrema()[3][1] == 0:
        return None
    return _fit_source(
        cropped,
        size,
    )


def _draw_missing_border(tile: Image.Image, direction: str) -> None:
    """Draw a TileSetter-like dotted placeholder for an unconfigured border."""

    width, height = tile.size
    draw = ImageDraw.Draw(tile)
    color = (245, 250, 255, 235)
    shadow = (35, 45, 62, 220)
    step = max(2, min(width, height) // 4)
    inset = max(1, min(width, height) // 8)
    if direction in {"top", "bottom"}:
        y = inset if direction == "top" else height - inset - 1
        for x in range(inset, max(inset + 1, width - inset), step):
            draw.point((x + 1, y + 1), fill=shadow)
            draw.point((x, y), fill=color)
    else:
        x = inset if direction == "left" else width - inset - 1
        for y in range(inset, max(inset + 1, height - inset), step):
            draw.point((x + 1, y + 1), fill=shadow)
            draw.point((x, y), fill=color)


def _replace_corner_quadrant(
    tile: Image.Image,
    corner_sample: Image.Image,
    diagonal: str,
) -> None:
    """Replace one tile quadrant with an authored corner sample.

    A custom corner is a finished piece, not another translucent edge layer.
    Replacing its quadrant prevents the two previously composited cardinal
    edges from bleeding through the corner and preserves transparent pixels
    from the authored Source.
    """

    width, height = tile.size
    # For odd dimensions leave the central row/column to the automatic
    # composite.  Giving them to two quadrants would make the result depend on
    # replacement order, while giving them to just one quadrant would break
    # rotational symmetry.
    split_x = width // 2
    split_y = height // 2
    far_x = (width + 1) // 2
    far_y = (height + 1) // 2
    bounds = {
        "top_left": (0, 0, split_x, split_y),
        "top_right": (far_x, 0, width, split_y),
        "bottom_right": (far_x, far_y, width, height),
        "bottom_left": (0, far_y, split_x, height),
    }.get(diagonal)
    if bounds is None:
        raise ValueError(f"Unsupported corner direction: {diagonal}")
    tile.paste(corner_sample.crop(bounds), (bounds[0], bounds[1]))


def _corner_quadrant_mask(size: tuple[int, int], diagonal: str) -> np.ndarray:
    """Return the pixels owned by one custom corner Source."""

    width, height = size
    split_x = width // 2
    split_y = height // 2
    far_x = (width + 1) // 2
    far_y = (height + 1) // 2
    bounds = {
        "top_left": (0, 0, split_x, split_y),
        "top_right": (far_x, 0, width, split_y),
        "bottom_right": (far_x, far_y, width, height),
        "bottom_left": (0, far_y, split_x, height),
    }.get(diagonal)
    if bounds is None:
        raise ValueError(f"Unsupported corner direction: {diagonal}")
    x0, y0, x1, y1 = bounds
    output = np.zeros((height, width), dtype=bool)
    output[y0:y1, x0:x1] = True
    return output


def _wang_transitions(mask: int) -> dict[str, bool]:
    """Return the four border endpoints present in a corner-Wang role."""

    north_west, north_east, south_east, south_west = (
        bool(mask & (1 << index)) for index in range(4)
    )
    return {
        "top": north_west != north_east,
        "right": north_east != south_east,
        "bottom": south_west != south_east,
        "left": north_west != south_west,
    }


def _wang_edge_owner_masks(
    size: tuple[int, int],
    directions: Sequence[str],
    cutoffs: Mapping[str, int],
) -> dict[str, np.ndarray]:
    """Partition a Wang tile between complete border samples.

    Each pixel has at most one owner.  Adjacent borders meet on a diagonal;
    opposite borders meet at their midpoint; four-border crossings form four
    deterministic sectors.  Cutoff offsets the distance of one Source and may
    be negative for Wang sets.  The calculation uses integer arithmetic only,
    so there is no interpolation, antialiasing, or alpha blending.
    """

    canonical = tuple(
        direction for direction in ("top", "right", "bottom", "left") if direction in directions
    )
    width, height = size
    yy, xx = np.indices((height, width), dtype=np.int64)
    horizontal_scale = max(1, height - 1)
    vertical_scale = max(1, width - 1)
    distance = {
        "top": (yy + int(cutoffs.get("top", 0))) * vertical_scale,
        "right": (width - 1 - xx + int(cutoffs.get("right", 0))) * horizontal_scale,
        "bottom": (height - 1 - yy + int(cutoffs.get("bottom", 0))) * vertical_scale,
        "left": (xx + int(cutoffs.get("left", 0))) * horizontal_scale,
    }
    if not canonical:
        return {}
    scores = np.stack([distance[direction] for direction in canonical], axis=0)
    minimum = np.min(scores, axis=0)
    tied = scores == minimum
    tie_count = np.sum(tied, axis=0)
    owners = {
        direction: tied[index] & (tie_count == 1) for index, direction in enumerate(canonical)
    }

    # A 45-degree seam belongs to the clockwise-facing Source at each corner.
    # Besides being deterministic, this rule rotates exactly with the artwork.
    adjacent_tie_owner = {
        frozenset(("top", "left")): "top",
        frozenset(("top", "right")): "right",
        frozenset(("right", "bottom")): "bottom",
        frozenset(("bottom", "left")): "left",
    }
    for pair, owner in adjacent_tie_owner.items():
        if not pair.issubset(canonical) or owner not in owners:
            continue
        pair_indices = tuple(canonical.index(direction) for direction in pair)
        only_pair = tie_count == 2
        for index in pair_indices:
            only_pair &= tied[index]
        owners[owner] |= only_pair

    # Opposite Sources use the midpoint of the overlap.  On an odd-sized
    # exact centre pixel, leave the two-base bitmap visible; arbitrarily giving
    # it to a side would destroy 90-degree rotational symmetry.
    if {"top", "bottom"}.issubset(canonical):
        top_index = canonical.index("top")
        bottom_index = canonical.index("bottom")
        opposite = (tie_count == 2) & tied[top_index] & tied[bottom_index]
        owners["top"] |= opposite & (2 * xx < width - 1)
        owners["bottom"] |= opposite & (2 * xx > width - 1)
    if {"left", "right"}.issubset(canonical):
        left_index = canonical.index("left")
        right_index = canonical.index("right")
        opposite = (tie_count == 2) & tied[left_index] & tied[right_index]
        owners["right"] |= opposite & (2 * yy < height - 1)
        owners["left"] |= opposite & (2 * yy > height - 1)
    return owners


def _render_tilesetter_wang_tile(
    base: Image.Image,
    secondary: Image.Image,
    edge_images: Mapping[str, Image.Image | None],
    corner_images: Mapping[str, Image.Image | None],
    mask: int,
    cutoffs: Mapping[str, int],
) -> Image.Image:
    """Compose one Wang role from two bases and complete border Sources."""

    width, height = base.size
    inside = np.asarray(base, dtype=np.uint8)
    outside = np.asarray(secondary, dtype=np.uint8)
    bitmap = _wang_bitmap_mask(mask, width, height)
    output = np.where(bitmap[..., None], inside, outside).astype(np.uint8)
    transitions = _wang_transitions(mask)
    available = tuple(
        direction
        for direction in ("top", "right", "bottom", "left")
        if transitions[direction] and edge_images.get(direction) is not None
    )
    owner_masks = _wang_edge_owner_masks((width, height), available, cutoffs)
    for direction in ("top", "right", "bottom", "left"):
        owner = owner_masks.get(direction)
        edge = edge_images.get(direction)
        if owner is None or edge is None:
            continue
        edge_pixels = np.asarray(edge, dtype=np.uint8)
        edge_content = edge_pixels[..., 3] != 0
        # A full Border Source owns a geometric region, but transparent
        # padding inside that Source does not own a pixel. Leave the already
        # composed base/secondary material visible instead of creating holes.
        owned_content = owner & edge_content
        output[owned_content] = edge_pixels[owned_content]
    tile = Image.fromarray(output, mode="RGBA")

    corner_bits = dict(
        zip(
            _WANG_CORNERS,
            (
                bool(mask & 1),
                bool(mask & 2),
                bool(mask & 4),
                bool(mask & 8),
            ),
            strict=True,
        )
    )
    incident = {
        "top_left": ("top", "left"),
        "top_right": ("top", "right"),
        "bottom_right": ("bottom", "right"),
        "bottom_left": ("bottom", "left"),
    }
    for diagonal in _WANG_CORNERS:
        first, second = incident[diagonal]
        if not transitions[first] or not transitions[second]:
            continue
        corner_type = "outer" if corner_bits[diagonal] else "inner"
        custom = corner_images.get(f"{corner_type}_{diagonal}")
        if custom is not None:
            _replace_corner_quadrant(tile, custom, diagonal)
    return tile


def _splice_intersecting_edges(
    tile: Image.Image,
    base: Image.Image,
    first_edge: Image.Image,
    second_edge: Image.Image,
    diagonal: str,
    *,
    inner: bool,
) -> None:
    """Build a corner by diagonally splicing two intersecting edge Sources.

    Outer corners take the closest cardinal edge on either side of the
    diagonal merge line. Inner corners keep only pixels affected by both edge
    samples, leaving the connected cardinal sides intact.
    """

    base_pixels = np.asarray(base, dtype=np.uint8)
    first_pixels = np.asarray(first_edge, dtype=np.uint8)
    second_pixels = np.asarray(second_edge, dtype=np.uint8)
    output = np.asarray(tile, dtype=np.uint8).copy()
    width, height = tile.size
    split_x = width // 2
    split_y = height // 2
    left = diagonal in {"top_left", "bottom_left"}
    top = diagonal in {"top_left", "top_right"}
    x_range = range(0, split_x) if left else range(split_x, width)
    y_range = range(0, split_y) if top else range(split_y, height)
    first_changed = np.any(first_pixels != base_pixels, axis=2)
    second_changed = np.any(second_pixels != base_pixels, axis=2)
    for y in y_range:
        distance_first = y if top else height - 1 - y
        for x in x_range:
            distance_second = x if left else width - 1 - x
            if inner and not (first_changed[y, x] and second_changed[y, x]):
                output[y, x] = base_pixels[y, x]
                continue
            output[y, x] = (
                first_pixels[y, x] if distance_first <= distance_second else second_pixels[y, x]
            )
    tile.paste(Image.fromarray(output, mode="RGBA"))


def _merge_tilesetter_edges(
    base: Image.Image,
    edge_images: Mapping[str, Image.Image | None],
    exposed_directions: Sequence[str],
) -> Image.Image:
    """Merge complete edge Sources instead of treating them as overlays.

    Tilesetter Sources describe a complete one-sided tile. A single exposed
    side therefore uses that Source verbatim. Multiple Sources are clipped at
    merge lines so an opaque background from one side cannot erase all other
    sides. Adjacent sides meet toward the solid corner; opposite and cap/island
    formations meet toward their exposed boundaries.
    """

    directions = [
        direction for direction in exposed_directions if edge_images.get(direction) is not None
    ]
    if not directions:
        return base.copy()
    if len(directions) == 1:
        edge = edge_images[directions[0]]
        assert edge is not None
        return edge.copy()

    width, height = base.size
    yy, xx = np.indices((height, width))
    distance_by_direction = {
        "top": yy,
        "right": width - 1 - xx,
        "bottom": height - 1 - yy,
        "left": xx,
    }
    distances = np.stack(
        [distance_by_direction[direction] for direction in directions],
        axis=0,
    )
    opposite_pair = set(directions) in ({"top", "bottom"}, {"left", "right"})
    # Adjacent outer corners keep the portion of each Source that points toward
    # the solid interior. Opposite edges and 3/4-sided formations use the
    # nearest exposed side, matching Tilesetter's non-overlap merge behavior.
    winners = (
        np.argmin(distances, axis=0)
        if opposite_pair or len(directions) > 2
        else np.argmax(distances, axis=0)
    )
    output = np.asarray(base, dtype=np.uint8).copy()
    for index, direction in enumerate(directions):
        edge = edge_images[direction]
        assert edge is not None
        edge_pixels = np.asarray(edge, dtype=np.uint8)
        output[winners == index] = edge_pixels[winners == index]
    return Image.fromarray(output, mode="RGBA")


def _erode_blob_core(mask: np.ndarray, cutoff: int, blob_mask: int) -> np.ndarray:
    """Shrink terrain so edge Sources may own a configurable transition band."""

    radius = max(0, int(cutoff))
    if radius == 0:
        return mask.copy()
    height, width = mask.shape
    padded = np.pad(mask, radius, mode="constant", constant_values=False)
    connected = {
        direction: bool(blob_mask & _DIRECTION_BITS[direction]) for direction in _DIRECTIONS
    }
    if connected["top"]:
        padded[:radius, radius : radius + width] = True
    if connected["right"]:
        padded[radius : radius + height, radius + width :] = True
    if connected["bottom"]:
        padded[radius + height :, radius : radius + width] = True
    if connected["left"]:
        padded[radius : radius + height, :radius] = True
    if connected["top_left"]:
        padded[:radius, :radius] = True
    if connected["top_right"]:
        padded[:radius, radius + width :] = True
    if connected["bottom_right"]:
        padded[radius + height :, radius + width :] = True
    if connected["bottom_left"]:
        padded[radius + height :, :radius] = True
    core = np.ones_like(mask, dtype=bool)
    for offset_y in range(radius * 2 + 1):
        for offset_x in range(radius * 2 + 1):
            core &= padded[offset_y : offset_y + height, offset_x : offset_x + width]
    return core


def _apply_blob_terrain_core(
    tile: Image.Image,
    base: Image.Image,
    mask: int,
    cutoff: int,
) -> Image.Image:
    """Keep the semantic Blob silhouette independent from Source artwork."""

    inside = _blob_bitmap_mask(mask, tile.width, tile.height)
    core = _erode_blob_core(inside, cutoff, mask)
    output = np.asarray(tile, dtype=np.uint8).copy()
    base_pixels = np.asarray(base, dtype=np.uint8)
    output[core] = base_pixels[core]
    return Image.fromarray(output, mode="RGBA")


def _tilesetter_edge_width(image: Image.Image, direction: int) -> int:
    """Measure a Blob border Source from its solid-facing side.

    This is the same directional alpha scan TileSetter uses to locate the
    merge point between opposite border Sources.
    """

    alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
    height, width = alpha.shape
    if direction == 0:  # top Source: scan from bottom toward the top
        hits = np.flatnonzero(np.any(alpha[::-1, :] != 0, axis=1))
        return 0 if len(hits) == 0 else height - int(hits[0])
    if direction == 1:  # right Source: scan from left toward the right
        hits = np.flatnonzero(np.any(alpha[:, :] != 0, axis=0))
        return 0 if len(hits) == 0 else width - int(hits[0])
    if direction == 2:  # bottom Source: scan from top toward the bottom
        hits = np.flatnonzero(np.any(alpha[:, :] != 0, axis=1))
        return 0 if len(hits) == 0 else height - int(hits[0])
    # left Source: scan from right toward the left
    hits = np.flatnonzero(np.any(alpha[:, ::-1] != 0, axis=0))
    return 0 if len(hits) == 0 else width - int(hits[0])


def _tilesetter_blob_clip_masks(
    size: tuple[int, int],
    widths: Sequence[int],
    cutoffs: Sequence[int],
) -> tuple[
    tuple[np.ndarray, ...],
    tuple[np.ndarray, ...],
    tuple[np.ndarray, ...],
    tuple[np.ndarray, ...],
    tuple[np.ndarray, ...],
]:
    """Create TileSetter's base, border, inner-corner, and diagonal clips."""

    width, height = size
    yy, xx = np.indices((height, width))
    top_cutoff, right_cutoff, bottom_cutoff, left_cutoff = cutoffs
    merge_y = math.floor((widths[0] + (height - widths[2])) / 2)
    merge_x = math.floor((widths[3] + (width - widths[1])) / 2)

    base = (
        yy >= top_cutoff,
        xx < width - right_cutoff,
        yy < height - bottom_cutoff,
        xx >= left_cutoff,
    )
    base_inner = (
        ~((xx < left_cutoff) & (yy < top_cutoff)),
        ~((xx >= width - right_cutoff) & (yy < top_cutoff)),
        ~((xx >= width - right_cutoff) & (yy >= height - bottom_cutoff)),
        ~((xx < left_cutoff) & (yy >= height - bottom_cutoff)),
    )
    border = (
        yy < merge_y,
        xx >= merge_x,
        yy >= merge_y,
        xx < merge_x,
    )
    border_inner = (
        ~((xx < merge_x) & (yy < merge_y)),
        ~((xx >= merge_x) & (yy < merge_y)),
        ~((xx >= merge_x) & (yy >= merge_y)),
        ~((xx < merge_x) & (yy >= merge_y)),
    )
    # Order matches BorderGeneratorBlob.clipsDiag:
    # upper-right, lower-right, lower-left, upper-left. Compare normalized
    # coordinates so the diagonal is geometric on rectangular tiles as well as
    # square ones; comparing raw x/y values skews the seam toward the longer
    # axis and can move a Border Source into the interior.
    x_scale = max(1, width - 1)
    y_scale = max(1, height - 1)
    diagonal_scale = x_scale * y_scale
    diagonal = (
        yy * x_scale <= xx * y_scale,
        xx * y_scale + yy * x_scale >= diagonal_scale,
        yy * x_scale >= xx * y_scale,
        xx * y_scale + yy * x_scale <= diagonal_scale,
    )
    return base, base_inner, border, border_inner, diagonal


def _tilesetter_masked_layer(
    image: Image.Image,
    clips: Sequence[np.ndarray],
) -> Image.Image:
    if not clips:
        return image.copy()
    visible = np.logical_and.reduce(clips)
    output = np.asarray(image, dtype=np.uint8).copy()
    output[..., 3] = np.where(visible, output[..., 3], 0)
    return Image.fromarray(output, mode="RGBA")


def _tilesetter_blob_neighbor_matrix(mask: int) -> tuple[bool | None, ...]:
    """Return TileSetter's NW,N,NE,E,SE,S,SW,W three-state matrix."""

    cardinal_neighbors = {
        direction: bool(mask & _DIRECTION_BITS[direction])
        for direction in ("top", "right", "bottom", "left")
    }

    def diagonal_state(diagonal_name: str, first: str, second: str) -> bool | None:
        if not cardinal_neighbors[first] or not cardinal_neighbors[second]:
            return None
        return bool(mask & _DIRECTION_BITS[diagonal_name])

    return (
        diagonal_state("top_left", "top", "left"),
        cardinal_neighbors["top"],
        diagonal_state("top_right", "top", "right"),
        cardinal_neighbors["right"],
        diagonal_state("bottom_right", "bottom", "right"),
        cardinal_neighbors["bottom"],
        diagonal_state("bottom_left", "bottom", "left"),
        cardinal_neighbors["left"],
    )


def _render_tilesetter_blob_tile_with_ownership(
    base: Image.Image,
    edge_images: Sequence[Image.Image],
    corner_images: Mapping[str, Image.Image | None],
    mask: int,
    cutoffs: Sequence[int],
    *,
    rotation_covariant: bool = False,
) -> tuple[Image.Image, np.ndarray]:
    """Port TileSetter 2.1's Blob layer compositor for one neighbor matrix."""

    width, height = base.size
    widths = tuple(_tilesetter_edge_width(image, index) for index, image in enumerate(edge_images))
    base_clips, base_inner_clips, border_clips, inner_clips, diagonal = _tilesetter_blob_clip_masks(
        (width, height), widths, cutoffs
    )
    # Matrix order: NW, N, NE, E, SE, S, SW, W. TileSetter does not use a
    # binary matrix here: diagonals whose two adjacent cardinal neighbors are
    # not both base terrain remain null. Treating null as the foreign terrain
    # creates false inner-corner cuts throughout the 47-tile set.
    matrix = _tilesetter_blob_neighbor_matrix(mask)

    visible_base = np.ones((height, width), dtype=bool)
    for rotation in range(4):
        cardinal = (1 + rotation * 2) % 8
        previous = (7 + rotation * 2) % 8
        diagonal_index = (rotation * 2) % 8
        if matrix[cardinal] is False:
            visible_base &= base_clips[rotation]
        if (
            matrix[cardinal] is True
            and matrix[previous] is True
            and matrix[diagonal_index] is False
        ):
            visible_base &= base_inner_clips[rotation]
    # Keep base ownership separate from opacity.  Alpha-compositing a partial
    # Source pixel would blend it with the previous layer and synthesize an
    # RGBA value that does not exist in any authored Source.
    output = np.zeros((height, width, 4), dtype=np.uint8)
    base_pixels = np.asarray(base, dtype=np.uint8)
    output[visible_base] = base_pixels[visible_base]
    edge_ownership = np.zeros((height, width), dtype=bool)

    directions = ("top", "right", "bottom", "left")
    layers: list[tuple[str, Image.Image, list[np.ndarray]]] = []

    def inner_sources(
        rotation: int,
        clips: Sequence[np.ndarray],
    ) -> tuple[tuple[str, Image.Image, list[np.ndarray]], ...]:
        """Return the two edge owners for one automatic inner corner."""

        return (
            (
                directions[rotation],
                edge_images[rotation],
                [diagonal[(rotation + 2) % 4], *clips],
            ),
            (
                directions[(rotation + 3) % 4],
                edge_images[(rotation + 3) % 4],
                [diagonal[rotation], *clips],
            ),
        )

    for rotation in range(4):
        north = (1 + rotation * 2) % 8
        east = (3 + rotation * 2) % 8
        south_east = (4 + rotation * 2) % 8
        south = (5 + rotation * 2) % 8
        south_west = (6 + rotation * 2) % 8
        west = (7 + rotation * 2) % 8
        north_west = (rotation * 2) % 8
        draw_cardinal = (
            (matrix[north] is False and matrix[east] is True and matrix[west] is True)
            or (matrix[north] is False and matrix[west] is False)
            or (matrix[north] is False and matrix[east] is False)
        )
        if draw_cardinal:
            clips: list[np.ndarray] = []
            if matrix[south_west] is False:
                clips.append(inner_clips[(rotation + 3) % 4])
            if matrix[south] is False:
                clips.append(border_clips[rotation])
            if matrix[south_east] is False:
                clips.append(inner_clips[(rotation + 2) % 4])
            if matrix[east] is False:
                clips.append(diagonal[(rotation + 3) % 4])
            if matrix[west] is False:
                clips.append(diagonal[rotation])
            layers.append(
                (
                    directions[rotation],
                    edge_images[rotation],
                    clips,
                )
            )

        if matrix[north_west] is False and matrix[north] is True and matrix[west] is True:
            clips = []
            if matrix[(2 + rotation * 2) % 8] is False:
                clips.append(inner_clips[(rotation + 1) % 4])
            if matrix[east] is False:
                clips.append(border_clips[(rotation + 3) % 4])
            if matrix[south_east] is False:
                clips.append(inner_clips[(rotation + 2) % 4])
            if matrix[south] is False:
                clips.append(border_clips[rotation])
            if matrix[south_west] is False:
                clips.append(inner_clips[(rotation + 3) % 4])
            layers.extend(inner_sources(rotation, clips))

    eligible = {direction: np.zeros((height, width), dtype=bool) for direction in directions}
    edge_content = {
        direction: np.asarray(edge_images[index].getchannel("A"), dtype=np.uint8) != 0
        for index, direction in enumerate(directions)
    }
    for direction, _image, clips in layers:
        visible = np.logical_and.reduce(clips) if clips else np.ones((height, width), dtype=bool)
        # Transparent padding in an edge Source is not border artwork.  It
        # leaves ownership with the clipped base (custom corner Sources are
        # intentionally exempt because they replace their quadrant later).
        visible &= edge_content[direction]
        eligible[direction] |= visible

    # TileSetter's inclusive diagonal clips deliberately overlap on their
    # seam.  Resolve only those overlaps geometrically: closest side wins and
    # adjacent exact ties use a cyclic rule that rotates with the artwork.
    # This retains the original midpoint/cutoff clips while avoiding both
    # alpha blending and fixed layer-order bias.
    yy, xx = np.indices((height, width), dtype=np.int64)
    horizontal_scale = max(1, height - 1)
    vertical_scale = max(1, width - 1)
    distance = {
        "top": yy * vertical_scale,
        "right": (width - 1 - xx) * horizontal_scale,
        "bottom": (height - 1 - yy) * vertical_scale,
        "left": xx * horizontal_scale,
    }
    if rotation_covariant:
        # A rotated canonical Source needs both opposite orientations to be
        # eligible on their exact midpoint.  TileSetter's half-open cardinal
        # clips otherwise assign that whole centre line to one fixed side,
        # which cannot rotate covariantly on odd-sized tiles.  Keep the legacy
        # half-open ownership for independently authored directional Sources.
        for first, second in (("top", "bottom"), ("left", "right")):
            if not np.any(eligible[first]) or not np.any(eligible[second]):
                continue
            midpoint = (distance[first] == distance[second]) & (eligible[first] | eligible[second])
            # Both orientations participate in the geometric tie even when
            # one has transparent padding at this coordinate.  The winning
            # Source's alpha is checked when pixels are copied below; if it is
            # transparent, the base remains instead of handing ownership to
            # the opposite orientation.
            eligible[first] |= midpoint
            eligible[second] |= midpoint
    eligibility = np.stack([eligible[direction] for direction in directions])
    candidate_count = np.sum(eligibility, axis=0)
    maximum = np.iinfo(np.int64).max
    scores = np.stack(
        [np.where(eligible[direction], distance[direction], maximum) for direction in directions]
    )
    minimum = np.min(scores, axis=0)
    tied = eligibility & (scores == minimum)
    tie_count = np.sum(tied, axis=0)
    winners = np.argmin(scores, axis=0)

    adjacent_tie_owner = {
        frozenset(("top", "left")): "top",
        frozenset(("top", "right")): "right",
        frozenset(("right", "bottom")): "bottom",
        frozenset(("bottom", "left")): "left",
    }
    for pair, owner in adjacent_tie_owner.items():
        pair_indices = tuple(directions.index(direction) for direction in pair)
        only_pair = tie_count == 2
        for index in pair_indices:
            only_pair &= tied[index]
        winners[only_pair] = directions.index(owner)

    # If opposite clips ever overlap after a cutoff, split the exact tie along
    # the perpendicular axis.  The centre pixel (and any 3/4-way tie) keeps
    # the base, since no single directional owner can be rotation-covariant.
    top_bottom = (tie_count == 2) & tied[0] & tied[2]
    winners[top_bottom & (2 * xx < width - 1)] = 0
    winners[top_bottom & (2 * xx > width - 1)] = 2
    left_right = (tie_count == 2) & tied[1] & tied[3]
    winners[left_right & (2 * yy < height - 1)] = 1
    winners[left_right & (2 * yy > height - 1)] = 3
    unresolved = (
        (tie_count >= 3)
        | (top_bottom & (2 * xx == width - 1))
        | (left_right & (2 * yy == height - 1))
    )
    output[unresolved] = base_pixels[unresolved]

    for index, _direction in enumerate(directions):
        owned = (
            (candidate_count > 0)
            & (winners == index)
            & ~unresolved
            & edge_content[directions[index]]
        )
        source_pixels = np.asarray(edge_images[index], dtype=np.uint8)
        output[owned] = source_pixels[owned]
        edge_ownership[owned] = True

    tile = Image.fromarray(output, mode="RGBA")
    incident = {
        "top_left": ("top", "left"),
        "top_right": ("top", "right"),
        "bottom_right": ("bottom", "right"),
        "bottom_left": ("bottom", "left"),
    }
    neighbors = set(_tile_neighbors("blob_47", mask))
    for diagonal_name in _WANG_CORNERS:
        first, second = incident[diagonal_name]
        corner_type: str | None = None
        if first not in neighbors and second not in neighbors:
            corner_type = "outer"
        elif first in neighbors and second in neighbors and diagonal_name not in neighbors:
            corner_type = "inner"
        if corner_type is None:
            continue
        custom = corner_images.get(f"{corner_type}_{diagonal_name}")
        if custom is not None:
            _replace_corner_quadrant(tile, custom, diagonal_name)
            edge_ownership |= _corner_quadrant_mask((width, height), diagonal_name)
    return tile, edge_ownership


def _render_tilesetter_blob_tile(
    base: Image.Image,
    edge_images: Sequence[Image.Image],
    corner_images: Mapping[str, Image.Image | None],
    mask: int,
    cutoffs: Sequence[int],
    *,
    rotation_covariant: bool = False,
) -> Image.Image:
    """Compose one Blob tile while retaining the legacy image-only API."""

    tile, _edge_ownership = _render_tilesetter_blob_tile_with_ownership(
        base,
        edge_images,
        corner_images,
        mask,
        cutoffs,
        rotation_covariant=rotation_covariant,
    )
    return tile


def _hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    clean = hex_code.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    if len(clean) != 6:
        raise ValueError(f"Invalid hex color code: {hex_code}")
    return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))


def _blob_procedural_material(
    size: tuple[int, int],
    material: str = "grass",
    *,
    base_color: tuple[int, int, int] | str | None = None,
    seed: int = 0,
) -> Image.Image:
    """Authentic, restrained pixel-art material textures with organic clusters."""
    default_colors: dict[str, tuple[int, int, int]] = {
        "grass": (82, 135, 104),
        "dirt": (123, 115, 95),
        "water": (45, 104, 123),
        "stone": (118, 122, 130),
        "sand": (198, 168, 112),
        "lava": (196, 72, 34),
        "snow": (214, 226, 238),
        "dungeon": (74, 68, 82),
    }
    mat_key = material.lower() if material.lower() in default_colors else "grass"
    if base_color is not None:
        if isinstance(base_color, str):
            try:
                color = _hex_to_rgb(base_color)
            except ValueError:
                color = default_colors[mat_key]
        else:
            color = (int(base_color[0]), int(base_color[1]), int(base_color[2]))
    else:
        color = default_colors[mat_key]

    w, h = size
    pixels = np.empty((h, w, 4), dtype=np.uint8)
    pixels[:] = (*color, 255)

    digest_input = f"mat:{mat_key}:{color}:{seed}".encode()
    digest = hashlib.sha256(digest_input).digest()

    # 1. Subtle natural dither base across all pixels (no rigid grid)
    xs = np.arange(w, dtype=np.int32)
    ys = np.arange(h, dtype=np.int32)[:, None]
    noise_grid = ((xs * 13 + ys * 29) % 19 - 9).astype(np.float32) * 0.008
    for c in range(3):
        channel_vals = np.clip(np.round(color[c] * (1.0 + noise_grid)), 0, 255).astype(np.uint8)
        pixels[..., c] = channel_vals

    def _apply_pixel(px: int, py: int, factor: float, alt_rgb: tuple[int, int, int] | None = None) -> None:
        if 0 <= px < w and 0 <= py < h:
            src = alt_rgb if alt_rgb is not None else color
            pixels[py, px, :3] = [max(0, min(255, round(ch * factor))) for ch in src]

    # 2. Material-specific organic pixel-art features
    tuft_count = max(3, (w * h) // 48)
    if mat_key == "grass":
        for i in range(tuft_count):
            tx = (digest[(i * 3) % len(digest)] * 17 + i * 7) % max(1, w - 2) + 1
            ty = (digest[(i * 3 + 1) % len(digest)] * 23 + i * 11) % max(1, h - 3) + 1
            _apply_pixel(tx, ty, 0.85)        # root shadow
            _apply_pixel(tx, ty - 1, 1.08)    # main blade
            _apply_pixel(tx, ty - 2, 1.18)    # tip highlight
            if digest[(i * 5) % len(digest)] % 2 == 0:
                _apply_pixel(tx + 1, ty - 1, 0.90)  # adjacent blade
            # Rare flower in variant banks
            if (seed + i) % 7 == 0:
                flower_color = (235, 210, 110) if (seed % 2 == 0) else (225, 140, 160)
                _apply_pixel(tx, ty - 3, 1.0, alt_rgb=flower_color)
    elif mat_key == "dirt":
        for i in range(tuft_count):
            tx = (digest[(i * 3) % len(digest)] * 19 + i * 5) % max(1, w - 2) + 1
            ty = (digest[(i * 3 + 1) % len(digest)] * 31 + i * 13) % max(1, h - 2) + 1
            _apply_pixel(tx, ty, 1.25)        # pebble highlight
            _apply_pixel(tx, ty + 1, 0.72)    # cast shadow
            if digest[(i * 4) % len(digest)] % 3 == 0:
                _apply_pixel(tx + 1, ty, 1.15)
                _apply_pixel(tx + 1, ty + 1, 0.75)
    elif mat_key == "water":
        wave_count = max(2, h // 4)
        for i in range(wave_count):
            wy = (i * 4 + (seed + digest[i % len(digest)]) % 3) % h
            wx = (digest[(i * 4 + 1) % len(digest)] * 11) % max(1, w - 4)
            length = 2 + (digest[(i * 4 + 2) % len(digest)] % 3)
            for lx in range(length):
                _apply_pixel(wx + lx, wy, 1.18)
                _apply_pixel(wx + lx, (wy + 1) % h, 0.88)
    elif mat_key == "stone":
        for i in range(tuft_count):
            tx = (digest[(i * 3) % len(digest)] * 17) % max(1, w - 2) + 1
            ty = (digest[(i * 3 + 1) % len(digest)] * 23) % max(1, h - 2) + 1
            _apply_pixel(tx, ty, 1.20)
            _apply_pixel(tx + 1, ty, 0.75)
    elif mat_key == "sand":
        for i in range(tuft_count):
            tx = (digest[(i * 3) % len(digest)] * 29) % max(1, w - 1)
            ty = (digest[(i * 3 + 1) % len(digest)] * 19) % max(1, h - 1)
            _apply_pixel(tx, ty, 1.12 if i % 2 == 0 else 0.90)
    else:
        for i in range(tuft_count):
            tx = (digest[(i * 3) % len(digest)] * 17) % max(1, w - 2) + 1
            ty = (digest[(i * 3 + 1) % len(digest)] * 23) % max(1, h - 2) + 1
            _apply_pixel(tx, ty, 1.15)
            _apply_pixel(tx, ty + 1, 0.82)

    return Image.fromarray(pixels, mode="RGBA")


generate_procedural_material = _blob_procedural_material


def apply_procedural_surface_noise(
    image: Image.Image,
    noise_style: str = "none",
    intensity: float = 0.0,
    *,
    seed: int = 0,
) -> Image.Image:
    """Apply authentic pixel-art surface noise and micro-texture to a tile or atlas.

    noise_style:
      - 'none': no noise modification
      - 'dither' or 'grain': subtle pseudo-random pixel-art stippling/dither
      - 'simplex' or 'smooth': low-frequency organic continuous undulating relief
      - 'gravel' or 'pebbles': high-contrast pebble and grit flecks
    intensity:
      - float from 0.0 (off) to 1.0 (maximum)
    seed:
      - integer randomization seed
    """
    if not noise_style or noise_style == "none" or intensity <= 0.001:
        return image

    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    h, w = rgba.shape[:2]
    alpha = rgba[..., 3]
    valid_mask = alpha > 10

    if not np.any(valid_mask):
        return image

    xs = np.arange(w, dtype=np.int32)
    ys = np.arange(h, dtype=np.int32)[:, None]

    if noise_style in {"dither", "grain"}:
        bayer4 = np.array([
            [ 0,  8,  2, 10],
            [12,  4, 14,  6],
            [ 3, 11,  1,  9],
            [15,  7, 13,  5],
        ], dtype=np.float32) / 15.0 - 0.5
        bayer = bayer4[ys % 4, xs % 4]
        jitter = (((xs * 17 + ys * 31 + (seed % 1000) * 13) % 11 - 5).astype(np.float32) / 5.0) * 0.25
        grid = (bayer * 0.75 + jitter * 0.25) * (intensity * 0.65)
    elif noise_style in {"simplex", "perlin", "smooth"}:
        f1 = np.sin((xs + (seed % 1000) * 7) * 0.25) * np.cos((ys + (seed % 1000) * 11) * 0.25)
        f2 = np.sin((xs * 0.5 + (seed % 1000) * 13)) * np.cos((ys * 0.5 + (seed % 1000) * 17)) * 0.5
        grid = (f1 + f2) * (intensity * 0.45)
    elif noise_style in {"gravel", "pebbles"}:
        speckle_hash = ((xs * 7919 + ys * 65537 + ((seed % 1000) + 1) * 104729) % 1000).astype(np.float32) / 1000.0
        grid = np.zeros((h, w), dtype=np.float32)
        grid[speckle_hash < 0.08] = -intensity * 0.55
        grid[(speckle_hash >= 0.08) & (speckle_hash < 0.16)] = intensity * 0.50
    else:
        return image

    rgb = rgba[..., :3]
    modulated_rgb = np.clip(np.round(rgb * (1.0 + grid[..., None])), 0, 255)
    rgba[valid_mask, :3] = modulated_rgb[valid_mask]

    result_arr = np.clip(rgba, 0, 255).astype(np.uint8)
    return Image.fromarray(result_arr, mode="RGBA")



def _render_blob_synthesis_tile(
    base: Image.Image,
    outside: Image.Image,
    mask: int,
    size: tuple[int, int],
    *,
    profile: TerrainEdgeProfile = "clean",
    variation: int = 0,
    seed: int = 0,
    corner_radius: int = 0,
    corner_style: str = "arc",
    retro_outline: bool = False,
    drop_shadow: int = 0,
    shadow_direction: str = "south",
    shadow_tint: str = "cool",
    shadow_intensity: float = 0.70,
    rim_light: bool = False,
    inner_rounding: float = 0.5,
) -> Image.Image:
    """Deterministically synthesize a Blob 47 tile from 1 or 2 material samples.

    Terreno A (base) forms the interior. Terreno B (outside) or transparent alpha
    forms the exterior. Profiles, corner radius, corner style (arc or chamfer),
    organic contours, drop shadows (with tint and intensity), and rim highlights
    are synthesized in pixel-perfect raster passes.
    """
    width, height = size
    if mask == 0:
        return outside.copy()
    if mask == 0xFF:
        return base.copy()

    # 1. Base geometric coverage
    eff_corner_style = "chamfer" if (corner_style == "chamfer" or profile == "rounded_chamfer") else "arc"
    if corner_radius > 0 or eff_corner_style == "chamfer" or profile in {"rounded_clean", "rounded_grass_tufts", "rounded_dither", "rounded_chamfer"}:
        eff_radius = (
            corner_radius
            if corner_radius > 0
            else max(1, (variation + 1) * max(1, min(width, height) // 16))
        )
        cov = _rounded_corner_coverage(
            mask, width, height, radius=eff_radius, kind="blob_47", corner_style=eff_corner_style
        )
    else:
        cov = _blob_bitmap_coverage(mask, width, height)

    # 2. Organic / micro-texture displacement
    if variation > 0 and profile not in {"clean", "rounded_clean", "rounded_chamfer"}:
        cov = _organic_blob_coverage(
            cov,
            profile=profile,
            variation=variation,
            seed=seed,
            mask=mask,
            inner_rounding=inner_rounding,
        )
        if profile == "rounded_grass_tufts":
            field = _dual_grid_texture_field(width, height, profile="rounded_grass_tufts", seed=seed)
            tufts = (field > 0.40).astype(np.float32) * 0.16
            cov = np.clip(cov + tufts, 0.0, 1.0)
        elif profile == "rounded_dither":
            yy, xx = np.indices((height, width))
            bayer = np.where((xx % 2 == 0) == (yy % 2 == 0), 0.10, -0.10).astype(np.float32)
            near_boundary = (cov > 0.3) & (cov < 0.7)
            cov = np.where(near_boundary, np.clip(cov + bayer, 0.0, 1.0), cov)

    ownership = cov >= 0.5

    # 3. Base composition of samples A and B
    base_arr = np.asarray(base, dtype=np.uint8)
    outside_arr = np.asarray(outside, dtype=np.uint8)
    pixels = np.where(ownership[..., None], base_arr, outside_arr).copy()

    # 4. Material-specific bands (grass roots, water fringe, etc.)
    if profile not in {"clean", "rounded_clean", "organic_neutral", "rounded_chamfer"} and variation > 0:
        pixels = _blob_material_layers(pixels, ownership, profile=profile, seed=seed)

    # 5. Drop shadow (sombra proyectada sobre el exterior)
    if drop_shadow > 0:
        intensity = max(0.1, min(1.0, float(shadow_intensity)))
        intensity_scale = intensity / 0.70
        for d in range(1, drop_shadow + 1):
            if shadow_direction == "south":
                layer = np.zeros((height, width), dtype=bool)
                layer[d:, :] = ownership[:-d, :]
                layer &= ~ownership
            elif shadow_direction == "south_east":
                layer = np.zeros((height, width), dtype=bool)
                layer[d:, d:] = ownership[:-d, :-d]
                layer &= ~ownership
            else:  # "all_around"
                dist = _pixel_distance_to_mask(ownership)
                layer = (~ownership) & (dist == d)

            if not np.any(layer):
                continue

            factor = 0.62 + 0.24 * ((d - 1) / max(1, drop_shadow))
            darkening = (1.0 - factor) * intensity_scale
            eff_factor = float(np.clip(1.0 - darkening, 0.10, 0.95))
            depth_ratio = max(0.0, 1.0 - ((d - 1) / max(1, drop_shadow)) * 0.45)

            if shadow_tint == "warm":
                r_mult, g_mult, b_mult = 1.08, 0.96, 0.88
                tint_color = (38, 24, 18)
            elif shadow_tint == "mystic":
                r_mult, g_mult, b_mult = 1.04, 0.90, 1.12
                tint_color = (32, 18, 38)
            elif shadow_tint == "neutral":
                r_mult, g_mult, b_mult = 1.00, 1.00, 1.00
                tint_color = (20, 20, 20)
            else:  # "cool"
                r_mult, g_mult, b_mult = 0.94, 0.98, 1.06
                tint_color = (18, 24, 38)

            opaque_layer = layer & (pixels[..., 3] > 10)
            transp_layer = layer & (pixels[..., 3] <= 10)

            if np.any(opaque_layer):
                rgb = pixels[opaque_layer, :3].astype(np.float32)
                rgb[..., 0] = np.clip(rgb[..., 0] * eff_factor * r_mult, 0, 255)
                rgb[..., 1] = np.clip(rgb[..., 1] * eff_factor * g_mult, 0, 255)
                rgb[..., 2] = np.clip(rgb[..., 2] * eff_factor * b_mult, 0, 255)
                pixels[opaque_layer, :3] = np.rint(rgb).astype(np.uint8)

            if np.any(transp_layer):
                shadow_alpha = int(np.clip(130 * depth_ratio * intensity_scale, 15, 235))
                pixels[transp_layer, 0] = tint_color[0]
                pixels[transp_layer, 1] = tint_color[1]
                pixels[transp_layer, 2] = tint_color[2]
                pixels[transp_layer, 3] = shadow_alpha

    # 6. Rim light (luz de borde superior / bisel)
    if rim_light:
        neighbors = set(_tile_neighbors("blob_47", mask))
        rim_mask = np.zeros((height, width), dtype=bool)
        if "top" not in neighbors:
            rim_mask[0, :] = ownership[0, :]
        if height > 1:
            rim_mask[1:, :] |= ownership[1:, :] & ~ownership[:-1, :]
        if np.any(rim_mask):
            rgb = pixels[rim_mask, :3].astype(np.float32)
            rgb[..., 0] = np.clip(rgb[..., 0] * 1.22, 0, 255)
            rgb[..., 1] = np.clip(rgb[..., 1] * 1.20, 0, 255)
            rgb[..., 2] = np.clip(rgb[..., 2] * 1.08, 0, 255)
            pixels[rim_mask, :3] = np.rint(rgb).astype(np.uint8)

    # 7. Retro outline (1px dark contour)
    if retro_outline:
        img = Image.fromarray(pixels, mode="RGBA")
        img = _apply_retro_outline(img, ownership)
        pixels = np.asarray(img, dtype=np.uint8)

    return Image.fromarray(pixels, mode="RGBA")


def build_tilesetter_terrain_pattern(
    atlas: Image.Image,
    *,
    tile_size: tuple[int, int],
    sources: Sequence[Mapping[str, object]],
    set_config: Mapping[str, object],
    kind: TerrainPatternKind = "blob_47",
    columns: int | None = None,
) -> TerrainPatternResult:
    """Render a selection-driven TileSetter-style generated set.

    Blob/Sides sets start from one base Source and may add directional Border
    Sources. Wang sets start from two solid Sources. For Blob/Wang, a material
    profile follows the actual non-transparent Border ownership after
    composition, preserving authored borders/corners and styling only the
    adjacent interior band. Any generated role may still be replaced with a
    custom Source through ``overrides``.
    """

    size = (max(1, int(tile_size[0])), max(1, int(tile_size[1])))
    _validate_dual_grid_size(kind, size)
    blob_variant_count = _normalize_blob_variant_count(
        kind,
        set_config.get("variantCount", set_config.get("variant_count", 1)),
    )
    if blob_variant_count > 1:
        profile_name, variation_level, base_seed = _normalize_pattern_edge_style(
            kind,
            set_config.get("edgeProfile") or set_config.get("terrainProfile", "clean"),
            set_config.get("edgeVariation", 0),
            set_config.get("edgeSeed", 0),
        )
        banks: list[TerrainPatternResult] = []
        for variant in range(blob_variant_count):
            variant_config = dict(set_config)
            variant_config["variantCount"] = 1
            variant_config["edgeSeed"] = (base_seed + variant * 104_729) % 1_000_000
            banks.append(
                build_tilesetter_terrain_pattern(
                    atlas,
                    tile_size=size,
                    sources=sources,
                    set_config=variant_config,
                    kind=kind,
                    columns=columns,
                )
            )
        first_bank = banks[0]
        combined = Image.new(
            "RGBA",
            (first_bank.image.width * blob_variant_count, first_bank.image.height),
            (0, 0, 0, 0),
        )
        variant_roles: list[TerrainPatternTile] = []
        for variant, bank_result in enumerate(banks):
            combined.paste(bank_result.image, (variant * first_bank.image.width, 0))
            for bank_tile in bank_result.tiles:
                variant_roles.append(
                    replace(
                        bank_tile,
                        index=variant * len(first_bank.tiles) + bank_tile.index,
                        column=variant * first_bank.columns + bank_tile.column,
                        variant=variant,
                        variant_seed=bank_result.edge_seed,
                        probability=1.0 / blob_variant_count,
                    )
                )
        multi_bank_result = replace(
            first_bank,
            image=combined,
            columns=first_bank.columns * blob_variant_count,
            tiles=tuple(variant_roles),
            terrain_profile=profile_name,
            edge_variation=variation_level,
            edge_seed=base_seed,
            variant_count=blob_variant_count,
        )
        from .animation import TerrainAnimationConfig, build_animated_terrain_frames

        anim_config = TerrainAnimationConfig.from_dict(set_config)
        if anim_config.enabled and anim_config.frame_count > 1:
            stacked_image, frame_images = build_animated_terrain_frames(
                multi_bank_result.image,
                multi_bank_result.tiles,
                tile_width=multi_bank_result.tile_width,
                tile_height=multi_bank_result.tile_height,
                config=anim_config,
                kind=multi_bank_result.kind,
                edge_seed=multi_bank_result.edge_seed,
            )
            return replace(
                multi_bank_result,
                image=stacked_image,
                is_animated=True,
                animation_frames=anim_config.frame_count,
                animation_fps=anim_config.fps,
                animation_style=anim_config.style,
                animation_frames_images=frame_images,
                base_rows=multi_bank_result.rows,
                rows=multi_bank_result.rows * anim_config.frame_count,
            )
        return multi_bank_result
    terrain_profile_name, terrain_edge_variation, terrain_edge_seed = _normalize_pattern_edge_style(
        kind,
        set_config.get("edgeProfile") or set_config.get("terrainProfile", "clean"),
        set_config.get("edgeVariation", 0),
        set_config.get("edgeSeed", 0),
    )
    raw_corner_radius = set_config.get("cornerRadius", set_config.get("corner_radius", 0))
    corner_radius = max(0, min(min(size) // 2, _object_int(raw_corner_radius, 0)))
    raw_inner_rounding = set_config.get(
        "innerCornerRounding",
        set_config.get("inner_corner_rounding", 0.5),
    )
    try:
        inner_corner_rounding = max(0.0, min(1.0, float(raw_inner_rounding)))
    except (TypeError, ValueError):
        inner_corner_rounding = 0.5
    retro_outline = bool(set_config.get("retroOutline", set_config.get("retro_outline", False)))
    base = _tilesetter_source_image(
        atlas,
        sources,
        str(set_config.get("baseSource") or "") or None,
        size,
    )
    secondary = _tilesetter_source_image(
        atlas,
        sources,
        str(set_config.get("secondarySource") or "") or None,
        size,
    )
    authored_base_id = str(set_config.get("baseSource") or "") or None
    authored_secondary_id = str(set_config.get("secondarySource") or "") or None
    is_procedural_mode = set_config.get("blobMaterialMode") == "procedural"
    is_procedural = is_procedural_mode or (
        not authored_base_id
        and not authored_secondary_id
        and (bool(set_config.get("primaryColor") or set_config.get("insideColor")) or not sources)
    )
    procedural_blob = (kind in {"blob_47", "sides_16"}) and is_procedural
    procedural_outside: Image.Image | None = None

    inside_material = (
        set_config.get("insideMaterial")
        or set_config.get("primaryMaterial")
        or ("dirt" if terrain_profile_name == "dirt_over_water" else "grass")
    )
    outside_material = (
        set_config.get("outsideMaterial")
        or set_config.get("secondaryMaterial")
        or ("dirt" if terrain_profile_name == "grass_over_dirt" else "water")
    )
    inside_color = set_config.get("primaryColor") or set_config.get("insideColor")
    outside_color = set_config.get("secondaryColor") or set_config.get("outsideColor")

    if base is None and (is_procedural or (not authored_base_id and bool(inside_color))):
        base = _blob_procedural_material(
            size,
            str(inside_material),
            base_color=inside_color,
            seed=0,
        )

    if secondary is None and (
        is_procedural
        or (not authored_secondary_id and (kind in {"dual_grid_15", "wang_16"} and bool(outside_color)))
    ):
        fallback_outside = outside_color or ("#2563EB" if "water" in str(terrain_profile_name) else "#6B4423")
        secondary = _blob_procedural_material(
            size,
            str(outside_material),
            base_color=fallback_outside,
            seed=1,
        )
        procedural_outside = secondary
    elif secondary is not None and procedural_outside is None:
        procedural_outside = secondary

    raw_edges = set_config.get("edges", {})
    edges = raw_edges if isinstance(raw_edges, Mapping) else {}
    raw_transforms = set_config.get("edgeTransforms", {})
    edge_transforms = raw_transforms if isinstance(raw_transforms, Mapping) else {}
    edge_images: dict[str, Image.Image | None] = {
        direction: None for direction in ("top", "right", "bottom", "left")
    }
    auto_orient_edges = bool(set_config.get("autoOrientEdges", False))
    if kind != "dual_grid_15":
        for direction in ("top", "right", "bottom", "left"):
            source = _tilesetter_source_image(
                atlas,
                sources,
                str(edges.get(direction) or "") or None,
                size,
            )
            if source is None or base is None:
                continue
            transform = edge_transforms.get(direction, {})
            transform_map = transform if isinstance(transform, Mapping) else {}
            # TileSetter edge Sources are complete tile-sized samples.  They
            # are clipped against one another later; extracting an alpha
            # overlay here loses intentional base pixels and makes opaque
            # Sources unusable.
            edge_layer = (
                source
                if kind in {"blob_47", "wang_16"}
                else _overlay_from_sample(base, source, size)
            )
            edge_images[direction] = _transform_layer(
                edge_layer,
                size,
                quarter_turns=(
                    _edge_transform_turns(direction, transform_map)
                    if auto_orient_edges
                    else _object_int(transform_map.get("rotation"), 0)
                ),
                flip_x=bool(transform_map.get("flipX", False)),
                flip_y=bool(transform_map.get("flipY", False)),
            )
        if procedural_blob and procedural_outside is not None:
            for direction in edge_images:
                if edge_images[direction] is None:
                    border = Image.new("RGBA", size)
                    depth = max(1, size[1] // 4)
                    border.paste(procedural_outside.crop((0, 0, size[0], depth)), (0, 0))
                    edge_images[direction] = _transform_layer(
                        border,
                        size,
                        quarter_turns=("top", "right", "bottom", "left").index(direction),
                        flip_x=False,
                        flip_y=False,
                    )
    raw_corners = set_config.get("corners", {})
    corners = raw_corners if isinstance(raw_corners, Mapping) else {}
    raw_corner_transforms = set_config.get("cornerTransforms", {})
    corner_transforms = raw_corner_transforms if isinstance(raw_corner_transforms, Mapping) else {}
    raw_custom_corners = set_config.get("customCorners", {})
    custom_corners = raw_custom_corners if isinstance(raw_custom_corners, Mapping) else {}
    corner_images: dict[str, Image.Image | None] = {
        f"{corner_type}_{diagonal}": None
        for corner_type in ("outer", "inner")
        for diagonal in _WANG_CORNERS
    }
    if kind != "dual_grid_15":
        for corner_type in ("outer", "inner"):
            for diagonal in _WANG_CORNERS:
                corner_key = f"{corner_type}_{diagonal}"
                if custom_corners.get(corner_key) is not True:
                    continue
                source = _tilesetter_source_image(
                    atlas,
                    sources,
                    str(corners.get(corner_key) or "") or None,
                    size,
                )
                if source is None or base is None:
                    continue
                transform = corner_transforms.get(corner_key, {})
                transform_map = transform if isinstance(transform, Mapping) else {}
                corner_images[corner_key] = _transform_layer(
                    source,
                    size,
                    quarter_turns=_object_int(transform_map.get("rotation"), 0),
                    flip_x=bool(transform_map.get("flipX", False)),
                    flip_y=bool(transform_map.get("flipY", False)),
                )
    raw_overrides = set_config.get("overrides", {})
    overrides = raw_overrides if isinstance(raw_overrides, Mapping) else {}
    override_sources = {
        int(mask): str(source_id)
        for mask, source_id in overrides.items()
        if str(mask).isdigit() and str(source_id)
    }
    masks = terrain_pattern_masks(kind)
    positions, column_count, row_count = _role_positions(kind, columns)
    output = Image.new(
        "RGBA",
        (column_count * size[0], row_count * size[1]),
        (0, 0, 0, 0),
    )
    raw_blob_mode = str(set_config.get("blobMode", set_config.get("blob_mode", "")) or "")
    drop_shadow = max(0, min(8, _object_int(set_config.get("dropShadow", set_config.get("drop_shadow", 0)), 0)))
    raw_shadow_dir = str(set_config.get("shadowDirection", set_config.get("shadow_direction", "south")) or "south")
    shadow_direction = raw_shadow_dir if raw_shadow_dir in {"south", "south_east", "all_around"} else "south"
    raw_shadow_tint = str(set_config.get("shadowTint", set_config.get("shadow_tint", "cool")) or "cool")
    shadow_tint = raw_shadow_tint if raw_shadow_tint in {"cool", "warm", "mystic", "neutral"} else "cool"
    raw_shadow_intensity = set_config.get("shadowIntensity", set_config.get("shadow_intensity", 0.70))
    try:
        shadow_intensity = max(0.1, min(1.0, float(raw_shadow_intensity)))
    except (TypeError, ValueError):
        shadow_intensity = 0.70
    raw_corner_style = str(set_config.get("cornerStyle", set_config.get("corner_style", "arc")) or "arc")
    corner_style = "chamfer" if (raw_corner_style == "chamfer" or terrain_profile_name == "rounded_chamfer") else "arc"
    rim_light = bool(set_config.get("rimLight", set_config.get("rim_light", False)))
    all_edges_ready = all(edge_images[direction] is not None for direction in edge_images)
    has_authored_edges = any(bool(edges.get(direction)) for direction in ("top", "right", "bottom", "left"))
    has_secondary_target = (
        secondary is not None
        or bool(set_config.get("secondarySource"))
        or bool(set_config.get("secondaryColor"))
        or bool(set_config.get("outsideColor"))
    )
    is_blob_synthesis = (
        kind == "blob_47"
        and (
            raw_blob_mode == "synthesis"
            or set_config.get("blobMaterialMode") in ("synthesis", "two_tile")
            or (
                has_secondary_target
                and not all_edges_ready
                and raw_blob_mode != "manual_edges"
                and base is not None
            )
            or (
                not procedural_blob
                and raw_blob_mode != "manual_edges"
                and not all_edges_ready
                and base is not None
                and (secondary is not None or not has_authored_edges)
            )
        )
    )
    is_procedural_wang = (
        kind == "wang_16"
        and secondary is not None
        and (is_procedural or not has_authored_edges or raw_blob_mode == "synthesis")
    )
    required_bases = base is not None and (not _is_wang_pattern(kind) or secondary is not None)
    # Dual Grid depends only on its two terrain Sources. Blob synthesis depends on base.
    ready = (
        (base is not None)
        if is_blob_synthesis
        else (required_bases and (kind == "dual_grid_15" or is_procedural_wang or all_edges_ready))
    )
    default_cutoff = 0 if _is_wang_pattern(kind) else max(1, min(size) // 8)
    raw_cutoff = _object_int(set_config.get("cutoff"), default_cutoff)
    cutoff = (
        max(-min(size), min(min(size), raw_cutoff))
        if _is_wang_pattern(kind)
        else max(0, min(min(size) // 2, raw_cutoff))
    )
    raw_edge_cutoffs = set_config.get("edgeCutoffs", {})
    edge_cutoffs = raw_edge_cutoffs if isinstance(raw_edge_cutoffs, Mapping) else {}
    directional_cutoff_map = {
        direction: max(
            -(size[1] if direction in {"top", "bottom"} else size[0])
            if _is_wang_pattern(kind)
            else 0,
            min(
                size[1] if direction in {"top", "bottom"} else size[0],
                _object_int(edge_cutoffs.get(direction), cutoff),
            ),
        )
        for direction in ("top", "right", "bottom", "left")
    }
    directional_cutoffs = tuple(
        directional_cutoff_map[direction] for direction in ("top", "right", "bottom", "left")
    )
    roles: list[TerrainPatternTile] = []
    for index, mask in enumerate(masks):
        override_source_id = override_sources.get(mask)
        override = _tilesetter_source_image(
            atlas,
            sources,
            override_source_id,
            size,
        )
        authored_edge_ownership: np.ndarray | None = None
        if override is not None:
            tile = override
        elif base is None:
            tile = _placeholder_tile(size, kind=kind, mask=mask)
        elif is_blob_synthesis:
            outside_img = secondary if secondary is not None else Image.new("RGBA", size, (0, 0, 0, 0))
            tile = _render_blob_synthesis_tile(
                base,
                outside_img,
                mask,
                size,
                profile=terrain_profile_name,
                variation=terrain_edge_variation,
                seed=terrain_edge_seed,
                corner_radius=corner_radius,
                corner_style=corner_style,
                retro_outline=retro_outline,
                drop_shadow=drop_shadow,
                shadow_direction=shadow_direction,
                shadow_tint=shadow_tint,
                shadow_intensity=shadow_intensity,
                rim_light=rim_light,
                inner_rounding=inner_corner_rounding,
            )
        elif _is_wang_pattern(kind) and secondary is not None:
            if kind == "dual_grid_15" or is_procedural_wang:
                tile = Image.fromarray(
                    _render_dual_grid_pixels(
                        np.asarray(base, dtype=np.uint8),
                        np.asarray(secondary, dtype=np.uint8),
                        mask,
                        kind=kind,
                        profile=terrain_profile_name,
                        variation=terrain_edge_variation,
                        seed=terrain_edge_seed,
                        corner_radius=corner_radius,
                        retro_outline=retro_outline,
                        inner_rounding=inner_corner_rounding,
                    ),
                    mode="RGBA",
                )
            else:
                tile = _render_tilesetter_wang_tile(
                    base,
                    secondary,
                    edge_images,
                    corner_images,
                    mask,
                    directional_cutoff_map,
                )
                if retro_outline and override is None:
                    tile = _apply_retro_outline(tile, _wang_bitmap_mask(mask, size[0], size[1]))
            if not is_procedural_wang:
                transitions = _wang_transitions(mask)
                for direction, present in transitions.items():
                    if not present:
                        continue
                    if kind != "dual_grid_15" and edge_images[direction] is None:
                        _draw_missing_border(tile, direction)
            if kind == "wang_16" and not is_procedural_wang and terrain_profile_name != "clean":
                available = tuple(
                    direction
                    for direction, present in transitions.items()
                    if present and edge_images[direction] is not None
                )
                authored_edge_ownership = np.zeros((size[1], size[0]), dtype=bool)
                for direction, owner in _wang_edge_owner_masks(
                    size,
                    available,
                    directional_cutoff_map,
                ).items():
                    edge = edge_images[direction]
                    if edge is not None:
                        authored_edge_ownership |= owner & (
                            np.asarray(edge.getchannel("A"), dtype=np.uint8) != 0
                        )
                incident = {
                    "top_left": ("top", "left"),
                    "top_right": ("top", "right"),
                    "bottom_right": ("bottom", "right"),
                    "bottom_left": ("bottom", "left"),
                }
                for corner_index, diagonal in enumerate(_WANG_CORNERS):
                    first, second = incident[diagonal]
                    corner_type = "outer" if mask & (1 << corner_index) else "inner"
                    if (
                        transitions[first]
                        and transitions[second]
                        and corner_images.get(f"{corner_type}_{diagonal}") is not None
                    ):
                        authored_edge_ownership |= _corner_quadrant_mask(size, diagonal)
                profile_coverage = _authored_edge_profile_coverage(
                    authored_edge_ownership,
                    size[0],
                    size[1],
                )
                if profile_coverage is not None and authored_edge_ownership is not None:
                    tile = Image.fromarray(
                        _render_dual_grid_pixels(
                            np.asarray(base, dtype=np.uint8),
                            np.asarray(secondary, dtype=np.uint8),
                            mask,
                            kind=kind,
                            profile=terrain_profile_name,
                            variation=terrain_edge_variation,
                            seed=terrain_edge_seed,
                            base_output=np.asarray(tile, dtype=np.uint8),
                            coverage_override=profile_coverage,
                            profile_mask=~authored_edge_ownership,
                        ),
                        mode="RGBA",
                    )
        else:
            neighbors = set(_tile_neighbors(kind, mask))
            exposed_directions = [
                direction
                for direction in ("top", "right", "bottom", "left")
                if direction not in neighbors
            ]
            inner_corner_directions: list[str] = []
            if kind == "blob_47":
                for diagonal, first, second_direction in (
                    ("top_left", "top", "left"),
                    ("top_right", "top", "right"),
                    ("bottom_right", "bottom", "right"),
                    ("bottom_left", "bottom", "left"),
                ):
                    if (
                        first in neighbors
                        and second_direction in neighbors
                        and diagonal not in neighbors
                    ):
                        inner_corner_directions.extend((first, second_direction))
            influence_directions = list(dict.fromkeys(exposed_directions + inner_corner_directions))
            if kind == "blob_47" and all_edges_ready:
                tile, authored_edge_ownership = _render_tilesetter_blob_tile_with_ownership(
                    base,
                    [
                        cast(Image.Image, edge_images[direction])
                        for direction in ("top", "right", "bottom", "left")
                    ],
                    corner_images,
                    mask,
                    directional_cutoffs,
                    rotation_covariant=auto_orient_edges,
                )
            else:
                tile = _merge_tilesetter_edges(
                    base,
                    edge_images,
                    influence_directions,
                )
                if kind == "blob_47" and influence_directions:
                    tile = _apply_blob_terrain_core(tile, base, mask, cutoff)
            for direction in exposed_directions:
                if edge_images[direction] is None:
                    _draw_missing_border(tile, direction)
            if kind == "blob_47" and not all_edges_ready:
                corner_rules = (
                    ("top_left", "top", "left"),
                    ("top_right", "top", "right"),
                    ("bottom_right", "bottom", "right"),
                    ("bottom_left", "bottom", "left"),
                )
                for diagonal, first, second_direction in corner_rules:
                    detected_corner_type: str | None = None
                    if first not in neighbors and second_direction not in neighbors:
                        detected_corner_type = "outer"
                    elif (
                        first in neighbors
                        and second_direction in neighbors
                        and diagonal not in neighbors
                    ):
                        detected_corner_type = "inner"
                    if detected_corner_type is None:
                        continue
                    corner_key = f"{detected_corner_type}_{diagonal}"
                    corner = corner_images.get(corner_key)
                    if corner is not None:
                        _replace_corner_quadrant(tile, corner, diagonal)
            if kind == "blob_47" and terrain_profile_name != "clean":
                canonical_coverage: np.ndarray | None
                if (
                    terrain_edge_variation > 0
                    or corner_radius > 0
                    or terrain_profile_name.startswith("rounded_")
                ):
                    canonical_coverage = _rounded_corner_coverage(
                        mask,
                        size[0],
                        size[1],
                        radius=(
                            corner_radius
                            if corner_radius > 0
                            else max(
                                1,
                                (terrain_edge_variation + 2) * max(1, min(size) // 16),
                            )
                        ),
                        kind=kind,
                    )
                else:
                    canonical_coverage = _authored_edge_profile_coverage(
                        ~_blob_bitmap_mask(mask, size[0], size[1]),
                        size[0],
                        size[1],
                    )
                if canonical_coverage is None:
                    canonical_coverage = np.full(
                        (size[1], size[0]),
                        1.0 if mask == 0xFF else 0.0,
                        dtype=np.float32,
                    )
                assert canonical_coverage is not None
                organic_coverage = _organic_blob_coverage(
                    canonical_coverage,
                    profile=terrain_profile_name,
                    variation=terrain_edge_variation,
                    seed=terrain_edge_seed,
                    exposed_directions=exposed_directions,
                    mask=mask,
                    inner_rounding=inner_corner_rounding,
                )
                authored_band = (
                    _authored_edge_profile_coverage(
                        authored_edge_ownership,
                        size[0],
                        size[1],
                    )
                    if authored_edge_ownership is not None
                    else None
                )
                has_corner = any(
                    (first not in neighbors and second not in neighbors)
                    or (first in neighbors and second in neighbors and diagonal not in neighbors)
                    for diagonal, first, second in (
                        ("top_left", "top", "left"),
                        ("top_right", "top", "right"),
                        ("bottom_right", "bottom", "right"),
                        ("bottom_left", "bottom", "left"),
                    )
                )
                if (
                    not procedural_blob and min(size) > 32
                    and authored_band is not None and not has_corner
                ):
                    authored_window = (
                        np.abs(authored_band - 0.5) * max(2, min(size))
                        <= max(2, min(size) // 12)
                    )
                    organic_coverage = np.where(
                        authored_window,
                        np.minimum(organic_coverage, authored_band),
                        np.maximum(organic_coverage, authored_band),
                    )
                # A complete directional Source is still a useful material
                # sample, but its opaque rectangle must not win over the
                # procedural contour at a Blob corner.  At an outer/inner
                # corner the source compositor owns a whole quadrant; keeping
                # those pixels verbatim recreates the square notch that the
                # organic coverage just removed.  Preserve authored pixels on
                # one-sided borders (and the shared outer ring) while letting
                # the corner quadrant follow the signed contour.
                procedural_corner = np.zeros(
                    (size[1], size[0]),
                    dtype=bool,
                )
                for diagonal, first, second in (
                    ("top_left", "top", "left"),
                    ("top_right", "top", "right"),
                    ("bottom_right", "bottom", "right"),
                    ("bottom_left", "bottom", "left"),
                ):
                    is_outer = first not in neighbors and second not in neighbors
                    is_inner = (
                        first in neighbors
                        and second in neighbors
                        and diagonal not in neighbors
                    )
                    if is_outer or is_inner:
                        procedural_corner |= _corner_quadrant_mask(
                            size,
                            diagonal,
                        )
                outside_source = next(
                    (edge for edge in edge_images.values() if edge is not None),
                    base,
                )
                outside_sample = (
                    procedural_outside if procedural_outside is not None
                    else (secondary if secondary is not None else _fill_transparent_edge_source(outside_source, base))
                )
                base_pixels = np.asarray(base, dtype=np.uint8)
                outside_pixels = np.asarray(outside_sample, dtype=np.uint8)
                organic_ownership = organic_coverage >= 0.5
                composed = np.where(
                    organic_ownership[..., None],
                    base_pixels,
                    outside_pixels,
                ).astype(np.uint8)
                if authored_edge_ownership is not None and not procedural_blob:
                    edge_alpha = any(
                        edge is not None
                        and np.any(np.asarray(edge.getchannel("A"), dtype=np.uint8) < 255)
                        for edge in edge_images.values()
                    )
                    if edge_alpha:
                        preserve_authored = authored_edge_ownership & ~procedural_corner
                        # At the native 16 px authoring scale a multi-pixel
                        # rectangular Source band is too rigid to be the
                        # final silhouette. Keep only the immutable atlas
                        # ring and let the organic field choose the interior
                        # ownership; larger authored sources retain their
                        # hand-placed band verbatim for compatibility.
                        if min(size) <= 32:
                            ring = np.zeros_like(preserve_authored)
                            ring[0, :] = True
                            ring[-1, :] = True
                            ring[:, 0] = True
                            ring[:, -1] = True
                            preserve_authored &= ring
                        composed[preserve_authored] = np.asarray(tile)[preserve_authored]
                # The procedural displacement is the visual boundary now. A
                # mask derived from the pre-displacement coverage leaves the
                # material bands behind on a wavy edge (especially at 16 px),
                # so derive the texture/shadow envelope from the same field
                # that selects base versus outside pixels.
                influence_coverage = organic_coverage
                influence_width = (
                    max(2, min(size) // 4)
                    if min(size) <= 32
                    else max(2, min(size) // 10)
                )
                organic_influence = (
                    np.abs(influence_coverage - 0.5)
                    * max(2, min(size))
                    < influence_width
                )
                if authored_edge_ownership is not None and not np.any(procedural_corner):
                    # A one-sided authored band is an explicit artist seam;
                    # keep its pixels byte-for-byte stable.  Once a corner is
                    # being procedurally filleted, however, its neighbouring
                    # authored band is part of the organic contour and may
                    # receive the requested material shadow/texture.
                    if min(size) <= 32:
                        ring = np.zeros_like(organic_influence)
                        ring[0, :] = True
                        ring[-1, :] = True
                        ring[:, 0] = True
                        ring[:, -1] = True
                        organic_influence &= ~(
                            authored_edge_ownership & ~ring
                        )
                    else:
                        organic_influence &= ~authored_edge_ownership
                tile = Image.fromarray(
                    _render_dual_grid_pixels(
                        base_pixels,
                        outside_pixels,
                        mask,
                        kind=kind,
                        profile=terrain_profile_name,
                        variation=terrain_edge_variation,
                        seed=terrain_edge_seed,
                        base_output=composed,
                        coverage_override=organic_coverage,
                        profile_mask=None if procedural_blob else organic_influence,
                        material_fringe=base_pixels if procedural_blob else None,
                        inner_rounding=inner_corner_rounding,
                    ),
                    mode="RGBA",
                )
            elif terrain_profile_name != "clean":
                style_outside = (
                    secondary
                    if secondary is not None
                    else next(
                        (edge for edge in edge_images.values() if edge is not None),
                        base,
                    )
                )
                tile = Image.fromarray(
                    _render_dual_grid_pixels(
                        np.asarray(base, dtype=np.uint8),
                        np.asarray(style_outside, dtype=np.uint8),
                        mask,
                        kind=kind,
                        profile=terrain_profile_name,
                        variation=terrain_edge_variation,
                        seed=terrain_edge_seed,
                        base_output=np.asarray(tile, dtype=np.uint8),
                        inner_rounding=inner_corner_rounding,
                    ),
                    mode="RGBA",
                )
            if (
                (
                    corner_radius > 0
                    or terrain_profile_name
                    in {"rounded_clean", "rounded_grass_tufts", "rounded_dither"}
                )
                and not all_edges_ready
                and override is None
                and secondary is None
                and procedural_outside is None
            ):
                r_val = (
                    corner_radius
                    if corner_radius > 0
                    else max(1, (terrain_edge_variation + 1) * max(1, min(size) // 16))
                )
                blob_cov = _rounded_corner_coverage(mask, size[0], size[1], radius=r_val, kind=kind)
                blob_mask = blob_cov >= 0.5
                tile_arr = np.asarray(tile, dtype=np.uint8).copy()
                tile_arr[~blob_mask] = [0, 0, 0, 0]
                tile = Image.fromarray(tile_arr, mode="RGBA")
            if retro_outline and override is None and kind in {"blob_47", "sides_16"}:
                b_cov = _rounded_corner_coverage(
                    mask,
                    size[0],
                    size[1],
                    radius=corner_radius,
                    kind=kind,
                )
                tile = _apply_retro_outline(tile, b_cov >= 0.5)
        column, row = positions[mask]
        _place_pattern_tile(
            output,
            tile,
            (column * size[0], row * size[1]),
            kind=kind,
        )
        roles.append(
            TerrainPatternTile(
                index=index,
                mask=mask,
                column=column,
                row=row,
                neighbors=_tile_neighbors(kind, mask),
                source_index=(
                    0 if ready or (kind != "dual_grid_15" and override is not None) else None
                ),
                generated=override is None,
                override_source_index=0 if override is not None else None,
                variant_seed=terrain_edge_seed,
            )
        )
    if kind == "dual_grid_15" and secondary is not None:
        _place_dual_grid_background(output, secondary, size)
    raw_noise_style = str(set_config.get("noiseStyle") or set_config.get("noise_style") or "none")
    raw_noise_intensity = set_config.get("noiseIntensity", set_config.get("noise_intensity", 0.0))
    try:
        noise_intensity = max(0.0, min(1.0, float(raw_noise_intensity)))
    except (TypeError, ValueError):
        noise_intensity = 0.0
    if raw_noise_style != "none" and noise_intensity > 0.001:
        output = apply_procedural_surface_noise(
            output,
            noise_style=raw_noise_style,
            intensity=noise_intensity,
            seed=terrain_edge_seed,
        )
    final_result = TerrainPatternResult(
        kind=kind,
        mode=_terrain_mode(kind),
        image=output,
        tile_width=size[0],
        tile_height=size[1],
        columns=column_count,
        rows=row_count,
        tiles=tuple(roles),
        dual_grid_profile=terrain_profile_name if kind == "dual_grid_15" else None,
        dual_grid_edge_variation=(terrain_edge_variation if kind == "dual_grid_15" else 0),
        dual_grid_edge_seed=terrain_edge_seed if kind == "dual_grid_15" else 0,
        terrain_profile=terrain_profile_name,
        edge_variation=terrain_edge_variation,
        edge_seed=terrain_edge_seed,
        corner_radius=corner_radius,
        retro_outline=retro_outline,
        variant_count=1,
        blob_mode=raw_blob_mode if raw_blob_mode else ("synthesis" if is_blob_synthesis else "manual_edges"),
        drop_shadow=drop_shadow,
        shadow_direction=shadow_direction,
        shadow_tint=shadow_tint,
        shadow_intensity=shadow_intensity,
        rim_light=rim_light,
        corner_style=corner_style,
        noise_style=raw_noise_style,
        noise_intensity=noise_intensity,
        inner_corner_rounding=inner_corner_rounding,
    )
    from .animation import TerrainAnimationConfig, build_animated_terrain_frames

    anim_config = TerrainAnimationConfig.from_dict(set_config)
    if anim_config.enabled and anim_config.frame_count > 1:
        stacked_image, frame_images = build_animated_terrain_frames(
            final_result.image,
            final_result.tiles,
            tile_width=final_result.tile_width,
            tile_height=final_result.tile_height,
            config=anim_config,
            kind=final_result.kind,
            edge_seed=final_result.edge_seed,
        )
        return replace(
            final_result,
            image=stacked_image,
            is_animated=True,
            animation_frames=anim_config.frame_count,
            animation_fps=anim_config.fps,
            animation_style=anim_config.style,
            animation_frames_images=frame_images,
            base_rows=final_result.rows,
            rows=final_result.rows * anim_config.frame_count,
        )
    return final_result


def _overlay_from_sample(
    base: Image.Image,
    sample: Image.Image,
    size: tuple[int, int],
) -> Image.Image:
    """Extract reusable detail when an opaque sample already contains the base."""

    fitted_base = np.asarray(_fit_source(base, size), dtype=np.uint8)
    fitted_sample = np.asarray(_fit_source(sample, size), dtype=np.uint8).copy()
    if np.any(fitted_sample[..., 3] < 255):
        return Image.fromarray(fitted_sample, mode="RGBA")
    changed = np.any(fitted_sample[..., :3] != fitted_base[..., :3], axis=2)
    fitted_sample[..., 3] = np.where(changed, 255, 0).astype(np.uint8)
    return Image.fromarray(fitted_sample, mode="RGBA")


def _clear_cutoff(tile: Image.Image, direction: str, cutoff: int) -> None:
    if cutoff <= 0:
        return
    width, height = tile.size
    draw = ImageDraw.Draw(tile)
    if direction == "top":
        bounds = (0, 0, width - 1, min(height - 1, cutoff - 1))
    elif direction == "right":
        bounds = (max(0, width - cutoff), 0, width - 1, height - 1)
    elif direction == "bottom":
        bounds = (0, max(0, height - cutoff), width - 1, height - 1)
    else:
        bounds = (0, 0, min(width - 1, cutoff - 1), height - 1)
    draw.rectangle(bounds, fill=(0, 0, 0, 0))


def build_smart_terrain_pattern(
    atlas: Image.Image,
    grid: TilesetGrid,
    *,
    base_source: int,
    edge_source: int,
    kind: TerrainPatternKind = "blob_47",
    edge_rotation: int = 0,
    flip_x: bool = False,
    flip_y: bool = False,
    cutoff: int = 0,
    outer_corner_source: int | None = None,
    inner_corner_source: int | None = None,
    overrides: Mapping[int, int] | None = None,
    columns: int | None = None,
    terrain_profile: TerrainEdgeProfile = "clean",
    edge_variation: int = 0,
    edge_seed: int = 0,
) -> TerrainPatternResult:
    """Generate every terrain role from reusable base, edge, and corner Sources."""

    size = (grid.tile_width, grid.tile_height)
    _validate_dual_grid_size(kind, size)
    terrain_profile_name, terrain_edge_variation, terrain_edge_seed = (
        _normalize_pattern_edge_style(kind, terrain_profile, edge_variation, edge_seed)
    )
    base = _source_image(atlas, grid, base_source)
    edge = _source_image(atlas, grid, edge_source)
    outer_corner = (
        _overlay_from_sample(
            base,
            _source_image(atlas, grid, outer_corner_source),
            size,
        )
        if outer_corner_source is not None
        else None
    )
    inner_corner = (
        _overlay_from_sample(
            base,
            _source_image(atlas, grid, inner_corner_source),
            size,
        )
        if inner_corner_source is not None
        else None
    )
    edge_overlay = _overlay_from_sample(base, edge, size)
    override_map = {int(mask): int(source) for mask, source in (overrides or {}).items()}
    masks = terrain_pattern_masks(kind)
    unknown_masks = set(override_map) - set(masks)
    if unknown_masks:
        raise ValueError(f"Overrides contain unsupported masks: {sorted(unknown_masks)}")
    positions, column_count, row_count = _role_positions(kind, columns)
    output = Image.new(
        "RGBA",
        (column_count * size[0], row_count * size[1]),
        (0, 0, 0, 0),
    )
    directions = ("top", "right", "bottom", "left")
    corner_rules = (
        ("top_left", "top", "left", 0),
        ("top_right", "top", "right", 1),
        ("bottom_right", "bottom", "right", 2),
        ("bottom_left", "bottom", "left", 3),
    )
    roles: list[TerrainPatternTile] = []
    for index, mask in enumerate(masks):
        override_source = override_map.get(mask)
        authored_edge_ownership: np.ndarray | None = None
        if override_source is not None:
            tile = _source_image(atlas, grid, override_source)
        elif _is_wang_pattern(kind):
            inside = np.asarray(_fit_source(base, size), dtype=np.uint8)
            outside = np.asarray(
                _transform_layer(
                    edge,
                    size,
                    quarter_turns=edge_rotation,
                    flip_x=flip_x,
                    flip_y=flip_y,
                ),
                dtype=np.uint8,
            )
            pixels = _render_dual_grid_pixels(
                inside,
                outside,
                mask,
                kind=kind,
                profile=terrain_profile_name,
                variation=terrain_edge_variation,
                seed=terrain_edge_seed,
            )
            tile = Image.fromarray(
                pixels,
                mode="RGBA",
            )
        else:
            neighbors = set(_tile_neighbors(kind, mask))
            tile = _fit_source(base, size)
            authored_edge_ownership = np.zeros((size[1], size[0]), dtype=bool)
            for direction_index, direction in enumerate(directions):
                if direction in neighbors:
                    continue
                _clear_cutoff(tile, direction, max(0, int(cutoff)))
                layer = _transform_layer(
                    edge_overlay,
                    size,
                    quarter_turns=edge_rotation + direction_index,
                    flip_x=flip_x,
                    flip_y=flip_y,
                )
                tile.alpha_composite(layer)
                if kind == "blob_47":
                    authored_edge_ownership |= (
                        np.asarray(layer.getchannel("A"), dtype=np.uint8) != 0
                    )
            for diagonal, first, second, turns in corner_rules:
                if outer_corner is not None and first not in neighbors and second not in neighbors:
                    tile.alpha_composite(_transform_layer(outer_corner, size, quarter_turns=turns))
                    if kind == "blob_47":
                        authored_edge_ownership |= _corner_quadrant_mask(size, diagonal)
                elif (
                    inner_corner is not None
                    and first in neighbors
                    and second in neighbors
                    and diagonal not in neighbors
                ):
                    tile.alpha_composite(_transform_layer(inner_corner, size, quarter_turns=turns))
                    if kind == "blob_47":
                        authored_edge_ownership |= _corner_quadrant_mask(size, diagonal)
            if kind == "blob_47" and terrain_profile_name != "clean":
                profile_coverage = _authored_edge_profile_coverage(
                    authored_edge_ownership,
                    size[0],
                    size[1],
                )
                if profile_coverage is not None and authored_edge_ownership is not None:
                    tile = Image.fromarray(
                        _render_dual_grid_pixels(
                            np.asarray(base, dtype=np.uint8),
                            np.asarray(edge, dtype=np.uint8),
                            mask,
                            kind=kind,
                            profile=terrain_profile_name,
                            variation=terrain_edge_variation,
                            seed=terrain_edge_seed,
                            base_output=np.asarray(tile, dtype=np.uint8),
                            coverage_override=profile_coverage,
                            profile_mask=~authored_edge_ownership,
                        ),
                        mode="RGBA",
                    )
            elif terrain_profile_name != "clean":
                tile = Image.fromarray(
                    _render_dual_grid_pixels(
                        np.asarray(base, dtype=np.uint8),
                        np.asarray(edge, dtype=np.uint8),
                        mask,
                        kind=kind,
                        profile=terrain_profile_name,
                        variation=terrain_edge_variation,
                        seed=terrain_edge_seed,
                        base_output=np.asarray(tile, dtype=np.uint8),
                    ),
                    mode="RGBA",
                )
        column, row = positions[mask]
        _place_pattern_tile(
            output,
            tile,
            (column * size[0], row * size[1]),
            kind=kind,
        )
        roles.append(
            TerrainPatternTile(
                index=index,
                mask=mask,
                column=column,
                row=row,
                neighbors=_tile_neighbors(kind, mask),
                source_index=base_source,
                generated=override_source is None,
                override_source_index=override_source,
            )
        )
    if kind == "dual_grid_15":
        _place_dual_grid_background(
            output,
            _transform_layer(
                edge,
                size,
                quarter_turns=edge_rotation,
                flip_x=flip_x,
                flip_y=flip_y,
            ),
            size,
        )
    return TerrainPatternResult(
        kind=kind,
        mode=_terrain_mode(kind),
        image=output,
        tile_width=size[0],
        tile_height=size[1],
        columns=column_count,
        rows=row_count,
        tiles=tuple(roles),
        dual_grid_profile=terrain_profile_name if kind == "dual_grid_15" else None,
        dual_grid_edge_variation=(terrain_edge_variation if kind == "dual_grid_15" else 0),
        dual_grid_edge_seed=terrain_edge_seed if kind == "dual_grid_15" else 0,
        terrain_profile=terrain_profile_name,
        edge_variation=terrain_edge_variation,
        edge_seed=terrain_edge_seed,
    )


def generate_terrain_pattern(
    interior: Image.Image,
    exterior: Image.Image,
    *,
    kind: TerrainPatternKind = "wang_16",
    tile_size: tuple[int, int] | None = None,
    columns: int | None = None,
    terrain_profile: TerrainEdgeProfile = "clean",
    edge_variation: int = 0,
    edge_seed: int = 0,
) -> TerrainPatternResult:
    """Compose a complete terrain atlas from two reusable bitmap sources."""

    if tile_size is None:
        tile_size = interior.size
    width, height = (int(value) for value in tile_size)
    if not 1 <= width <= 128 or not 1 <= height <= 128:
        raise ValueError("Terrain tiles must be between 1 and 128 pixels per axis")
    _validate_dual_grid_size(kind, (width, height))
    terrain_profile_name, terrain_edge_variation, terrain_edge_seed = (
        _normalize_pattern_edge_style(kind, terrain_profile, edge_variation, edge_seed)
    )
    inside = np.asarray(_fit_source(interior, (width, height)), dtype=np.uint8)
    outside = np.asarray(_fit_source(exterior, (width, height)), dtype=np.uint8)
    masks = terrain_pattern_masks(kind)
    positions, column_count, row_count = _role_positions(kind, columns)
    atlas = Image.new(
        "RGBA",
        (column_count * width, row_count * height),
        (0, 0, 0, 0),
    )
    roles: list[TerrainPatternTile] = []
    for index, mask in enumerate(masks):
        pixels = _render_dual_grid_pixels(
            inside,
            outside,
            mask,
            kind=kind,
            profile=terrain_profile_name,
            variation=terrain_edge_variation,
            seed=terrain_edge_seed,
        )
        tile = Image.fromarray(pixels, mode="RGBA")
        column, row = positions[mask]
        _place_pattern_tile(
            atlas,
            tile,
            (column * width, row * height),
            kind=kind,
        )
        roles.append(
            TerrainPatternTile(
                index=index,
                mask=mask,
                column=column,
                row=row,
                neighbors=_tile_neighbors(kind, mask),
                source_index=index,
            )
        )
    if kind == "dual_grid_15":
        _place_dual_grid_background(
            atlas,
            Image.fromarray(outside, mode="RGBA"),
            (width, height),
        )
    return TerrainPatternResult(
        kind=kind,
        mode=_terrain_mode(kind),
        image=atlas,
        tile_width=width,
        tile_height=height,
        columns=column_count,
        rows=row_count,
        tiles=tuple(roles),
        dual_grid_profile=terrain_profile_name if kind == "dual_grid_15" else None,
        dual_grid_edge_variation=(terrain_edge_variation if kind == "dual_grid_15" else 0),
        dual_grid_edge_seed=terrain_edge_seed if kind == "dual_grid_15" else 0,
        terrain_profile=terrain_profile_name,
        edge_variation=terrain_edge_variation,
        edge_seed=terrain_edge_seed,
    )


def _dual_grid_runtime_roles(
    result: TerrainPatternResult,
) -> tuple[tuple[TerrainPatternTile, int], ...]:
    """Return TileMapDual's 16 physical cells and their terrain assignments.

    The authored pattern deliberately has 15 foreground masks.  TileMapDual
    nevertheless scans a complete 4x4 atlas: mask 0 identifies the world
    background, mask 15 identifies the foreground, and transitions must not
    identify as either terrain or the plugin can select a transition as a
    world tile.
    """

    if result.kind != "dual_grid_15":
        raise ValueError("Dual Grid runtime roles require a dual_grid_15 result")
    if (result.columns, result.rows) != (4, 4):
        raise ValueError("Dual Grid runtime export requires TileMapDual's 4x4 layout")
    _validate_dual_grid_size(result.kind, (result.tile_width, result.tile_height))
    expected_masks = set(terrain_pattern_masks("dual_grid_15"))
    by_mask = {tile.mask: tile for tile in result.tiles}
    if set(by_mask) != expected_masks:
        raise ValueError("Dual Grid result must contain masks 1 through 15")
    positions, _, _ = _role_positions("dual_grid_15", None)
    if any((tile.column, tile.row) != positions[tile.mask] for tile in result.tiles):
        raise ValueError("Dual Grid result does not use TileMapDual's Standard layout")
    empty = TerrainPatternTile(
        index=0,
        mask=0,
        column=_DUAL_GRID_EMPTY_POSITION[0],
        row=_DUAL_GRID_EMPTY_POSITION[1],
        neighbors=(),
        generated=True,
    )
    return (
        (empty, 0),
        *(
            (by_mask[mask], 1 if mask == _DUAL_GRID_FOREGROUND_MASK else -1)
            for mask in range(1, _DUAL_GRID_FOREGROUND_MASK + 1)
        ),
    )


def _tile_peering_bits(
    result: TerrainPatternResult,
    tile: TerrainPatternTile,
) -> dict[str, int]:
    """Build Godot peer values for one exported tile.

    Standard Godot terrain exports use -1 for empty space.  TileMapDual's
    Standard preset instead requires an explicit binary 0/1 value at every
    corner, including all transition tiles.
    """

    if result.kind == "dual_grid_15":
        return {
            str(_GODOT_PEERING_BITS[name]): int(name in tile.neighbors)
            for name in _DUAL_GRID_TILEMAP_DUAL_PEERING_CORNERS
        }
    return {
        str(_GODOT_PEERING_BITS[name]): (0 if name in tile.neighbors else -1)
        for name in _relevant_directions(result.kind)
    }


def terrain_pattern_manifest(
    result: TerrainPatternResult,
    *,
    terrain_name: str = "Terrain",
) -> dict[str, object]:
    """Build stable, engine-neutral metadata for a generated pattern atlas."""

    png = io.BytesIO()
    result.image.save(png, format="PNG", optimize=False)
    godot: dict[str, object] = {
        "version": 4,
        "terrain_set": 0,
        "terrain": 0,
        "mode": result.mode,
        "importer": "install_terrain_tileset.gd",
    }
    runtime_roles = (
        _dual_grid_runtime_roles(result)
        if result.kind == "dual_grid_15"
        else tuple((tile, 0) for tile in result.tiles)
    )
    if result.kind == "dual_grid_15":
        godot["terrain"] = {
            "background": 0,
            "foreground": 1,
            "transitions": -1,
        }
    tiles: list[dict[str, object]] = []
    for tile, terrain in runtime_roles:
        entry: dict[str, object] = {
            "id": tile.mask if result.kind == "dual_grid_15" else tile.index,
            "column": tile.column,
            "row": tile.row,
            "mask": tile.mask,
            "neighbors": list(tile.neighbors),
            "source_index": tile.source_index,
            "generated": tile.generated,
            "override_source_index": tile.override_source_index,
            "variant": tile.variant,
            "variant_seed": tile.variant_seed,
            "probability": tile.probability,
            "peering_bits": _tile_peering_bits(result, tile),
        }
        if result.kind == "dual_grid_15":
            entry["terrain"] = terrain
            entry["role"] = (
                "background"
                if tile.mask == 0
                else "foreground"
                if tile.mask == _DUAL_GRID_FOREGROUND_MASK
                else "transition"
            )
        tiles.append(entry)
    manifest: dict[str, object] = {
        "schema_version": "1.1" if result.variant_count > 1 else "1.0",
        "kind": "terrain_pattern",
        "pattern": result.kind,
        "terrain_name": terrain_name,
        "atlas": {
            "path": "terrain_tiles.png",
            "width": result.image.width,
            "height": result.image.height,
            "sha256": hashlib.sha256(png.getvalue()).hexdigest(),
        },
        "grid": {
            "tile_width": result.tile_width,
            "tile_height": result.tile_height,
            "columns": result.columns,
            "rows": result.rows,
        },
        "godot": godot,
        "tiles": tiles,
    }
    if result.kind == "dual_grid_15":
        manifest["dual_grid"] = {
            "runtime": "TileMapDual",
            "atlas_layout": "tilemapdual_standard_4x4",
            "topology": "square",
            "neighborhood": "square",
            "terrain_profile": result.dual_grid_profile or "clean",
            "edge_variation": result.dual_grid_edge_variation,
            "edge_seed": result.dual_grid_edge_seed,
            "edge_generation": "deterministic_palette_bands",
            "logical_grid": "terrain_cells",
            "display_grid_offset": [-0.5, -0.5],
            "display_grid_offset_owner": "TileMapDual",
            "corner_order": list(_WANG_CORNERS),
            "tilemap_dual_peering_order": list(_DUAL_GRID_TILEMAP_DUAL_PEERING_CORNERS),
            "empty_mask": 0,
            "masks": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
            "runtime_masks": list(range(16)),
            "terrain_roles": {
                "background_mask": 0,
                "background_terrain": 0,
                "foreground_mask": _DUAL_GRID_FOREGROUND_MASK,
                "foreground_terrain": 1,
                "transition_terrain": -1,
            },
        }
    else:
        edge_profile: dict[str, object] = {
            "terrain_profile": result.terrain_profile or "clean",
            "edge_variation": result.edge_variation,
            "edge_seed": result.edge_seed,
            "edge_generation": "deterministic_palette_bands",
        }
        if result.variant_count > 1:
            edge_profile.update(
                {
                    "edge_generation": "deterministic_organic_contour_and_palette_bands",
                    "variant_count": result.variant_count,
                    "variant_layout": "horizontal_canonical_banks",
                    "variants_are_seam_compatible": True,
                }
            )
        manifest["edge_profile"] = edge_profile
    if result.is_animated:
        base_rows = result.base_rows or (result.rows // result.animation_frames)
        manifest["animation"] = {
            "is_animated": True,
            "frame_count": result.animation_frames,
            "fps": result.animation_fps,
            "style": result.animation_style,
            "layout": "vertical_stack",
            "base_rows": base_rows,
            "frame_height": base_rows * result.tile_height,
        }
    return manifest


def render_godot_terrain_installer(
    result: TerrainPatternResult,
    *,
    terrain_name: str = "Terrain",
    texture_resource_path: str | None = None,
    tileset_resource_path: str | None = None,
) -> str:
    """Render an EditorScript that creates a Godot 4 terrain TileSet resource.

    For Dual Grid this is specifically the TileMapDual Standard-preset
    contract, not a regular one-terrain TileMapLayer autotile.
    """

    for path in (texture_resource_path, tileset_resource_path):
        if path is None:
            continue
        if not path.startswith("res://") or path.endswith(".import"):
            raise ValueError("Godot resource paths must use res:// and never .import")
    needs_script_dir = texture_resource_path is None or tileset_resource_path is None
    script_dir_setup = (
        "    var current_script := get_script() as Script\n"
        "    var script_dir: String = current_script.resource_path.get_base_dir()\n"
        if needs_script_dir
        else ""
    )
    texture_path = (
        'script_dir.path_join("terrain_tiles.png")'
        if texture_resource_path is None
        else json.dumps(texture_resource_path)
    )
    tileset_path = (
        'script_dir.path_join("terrain_tileset.tres")'
        if tileset_resource_path is None
        else json.dumps(tileset_resource_path)
    )
    mode = {
        "match_corners": "TileSet.TERRAIN_MODE_MATCH_CORNERS",
        "match_sides": "TileSet.TERRAIN_MODE_MATCH_SIDES",
        "match_corners_and_sides": ("TileSet.TERRAIN_MODE_MATCH_CORNERS_AND_SIDES"),
    }[_terrain_mode(result.kind)]
    entry_lines: list[str] = []
    runtime_roles = (
        _dual_grid_runtime_roles(result)
        if result.kind == "dual_grid_15"
        else tuple((tile, 0) for tile in result.tiles)
    )
    for tile, terrain in runtime_roles:
        peers = ", ".join(
            f"{peering_bit}: {value}"
            for peering_bit, value in _tile_peering_bits(result, tile).items()
        )
        entry_lines.append(
            '        {"coords": Vector2i('
            f'{tile.column}, {tile.row}), "terrain": {terrain}, '
            f'"probability": {tile.probability:.8f}, "peers": {{{peers}}}}},'
        )
    entries = "\n".join(entry_lines)
    terrain_setup = (
        """    tile_set.add_terrain(0)
    tile_set.set_terrain_name(0, 0, \"Background\")
    tile_set.add_terrain(0)
    tile_set.set_terrain_name(0, 1, """
        + json.dumps(terrain_name, ensure_ascii=False)
        + ")"
        if result.kind == "dual_grid_15"
        else "    tile_set.add_terrain(0)\n    tile_set.set_terrain_name(0, 0, "
        + json.dumps(terrain_name, ensure_ascii=False)
        + ")"
    )
    anim_gdscript = ""
    if result.is_animated and result.animation_frames > 1:
        base_rows = result.base_rows or (result.rows // result.animation_frames)
        sep_y = base_rows - 1
        anim_gdscript = (
            f"        atlas.set_tile_animation_columns(coords, 1)\n"
            f"        atlas.set_tile_animation_separation(coords, Vector2i(0, {sep_y}))\n"
            f"        atlas.set_tile_animation_frames_count(coords, {result.animation_frames})\n"
            f"        atlas.set_tile_animation_speed(coords, {result.animation_fps:.2f})\n"
        )

    return f"""@tool
extends EditorScript

# Generated by sprite-builder. Copy this file beside terrain_tiles.png,
# open it in Godot 4's script editor, then choose File > Run.
func _run() -> void:
{script_dir_setup}    var texture := load({texture_path})
    if texture == null:
        push_error("Import terrain_tiles.png before running this script.")
        return

    var tile_set := TileSet.new()
    tile_set.tile_size = Vector2i({result.tile_width}, {result.tile_height})
    tile_set.add_terrain_set()
    tile_set.set_terrain_set_mode(0, {mode})
{terrain_setup}

    var atlas := TileSetAtlasSource.new()
    atlas.texture = texture
    atlas.texture_region_size = Vector2i({result.tile_width}, {result.tile_height})
    tile_set.add_source(atlas, 0)
    var entries := [
{entries}
    ]
    for entry in entries:
        var coords: Vector2i = entry["coords"]
        atlas.create_tile(coords)
{anim_gdscript}        var tile_data := atlas.get_tile_data(coords, 0)
        tile_data.terrain_set = 0
        tile_data.terrain = entry["terrain"]
        tile_data.probability = entry["probability"]
        for peering_bit in entry["peers"]:
            tile_data.set_terrain_peering_bit(peering_bit, entry["peers"][peering_bit])

    var error := ResourceSaver.save(tile_set, {tileset_path})
    if error != OK:
        push_error("Could not save the TileSet resource (error %s)." % error)
        return
    print("Created " + {tileset_path})
"""


def build_terrain_pattern_bundle(
    result: TerrainPatternResult,
    *,
    terrain_name: str = "Terrain",
) -> bytes:
    """Package a generated atlas, lineage metadata, and Godot 4 installer."""

    if not result.complete:
        raise ValueError(f"Terrain pattern has {len(result.unassigned_masks)} unassigned roles")
    atlas = io.BytesIO()
    result.image.save(atlas, format="PNG", optimize=False)
    bitmask_reference = io.BytesIO()
    render_terrain_bitmask_template(result.kind).save(
        bitmask_reference,
        format="PNG",
        optimize=False,
    )
    manifest = terrain_pattern_manifest(result, terrain_name=terrain_name)
    if result.kind == "dual_grid_15":
        readme = """TileMapDual 4x4 Standard pattern

1. Copy all files into one folder in your Godot project.
2. Install and enable the TileMapDual plugin, then wait for terrain_tiles.png
   to finish importing.
3. Open install_terrain_tileset.gd in Godot's script editor and choose
   File > Run. The script creates terrain_tileset.tres.
4. Assign that resource to a TileMapDual node with Square topology and the
   Standard preset. Do not use a normal TileMapLayer terrain-paint workflow.
   This atlas and its peers do not support isometric, hexagonal, or triangle
   TileMapDual configurations.

The atlas contains 15 authored foreground masks plus its required physical
mask-0 background cell at (0, 3). Mask 15 at (2, 1) identifies the foreground
terrain; masks 1 through 14 are transitions and intentionally have terrain
-1. Every role has four binary (0/1) corner peers, as TileMapDual requires.

If a material-pair edge profile was selected in Pattern Studio, its profile,
variation level, and deterministic seed are recorded in terrain_pattern.json.
The generated material-pair profiles build hard pixel-art palette bands from
Terrain A and B: shadow, rim, bank/root, and clustered accents. They may derive
new RGB tones, but never blur or alpha-blend; source alpha remains unchanged.

The artistic mask bit order is NW, NE, SE, SW. TileMapDual reads Godot peer
corners in TL, TR, BL, BR order; terrain_pattern.json records both orders.
TileMapDual owns the half-tile display offset between its logical world grid
and its display layer. The JSON manifest can also drive a procedural map
generator. The installer resolves terrain_tiles.png and terrain_tileset.tres
relative to its own folder, so this bundle may live in any project subfolder.
terrain_bitmask_reference.png is a visual guide; Godot 4 does not import it.
No .import file is included or created by sprite-builder.
"""
    else:
        readme = """Godot 4 terrain pattern

1. Copy all files into one folder in your Godot project.
2. Wait for terrain_tiles.png to finish importing.
3. Open install_terrain_tileset.gd in Godot's script editor.
4. Choose File > Run. The script creates terrain_tileset.tres.
5. Assign that resource to a TileMapLayer and paint terrain 0.

The JSON manifest is engine-neutral and can also drive a procedural map generator.
Blob exports with organic variants contain three horizontal canonical banks.
Every bank repeats the same 47 peering masks with a different deterministic
interior contour; their outer pixel ports remain compatible. Godot receives the
same probability for each matching variant.
The installer resolves terrain_tiles.png and terrain_tileset.tres relative to
its own folder, so this bundle may live in any project subfolder.
terrain_bitmask_reference.png is a visual guide; Godot 4 does not import it.
No .import file is included or created by sprite-builder.
"""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("terrain_tiles.png", atlas.getvalue())
        bundle.writestr("terrain_bitmask_reference.png", bitmask_reference.getvalue())
        bundle.writestr(
            "terrain_pattern.json",
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        bundle.writestr(
            "install_terrain_tileset.gd",
            render_godot_terrain_installer(result, terrain_name=terrain_name),
        )
        bundle.writestr("README.txt", readme)
    return archive.getvalue()


def _unity_neighbor_rules(kind: TerrainPatternKind, mask: int) -> dict[str, str]:
    """Map a pattern mask to Unity RuleTile 8-direction neighbor rules."""
    neighbors = set(_tile_neighbors(kind, mask))
    rules: dict[str, str] = {}

    if kind == "blob_47":
        for card in ("top", "right", "bottom", "left"):
            rules[card] = "This" if card in neighbors else "NotThis"
        corner_pairs = {
            "top_left": ("top", "left"),
            "top_right": ("top", "right"),
            "bottom_right": ("bottom", "right"),
            "bottom_left": ("bottom", "left"),
        }
        for corner, (c1, c2) in corner_pairs.items():
            if c1 in neighbors and c2 in neighbors:
                rules[corner] = "This" if corner in neighbors else "NotThis"
            else:
                rules[corner] = "DontCare"
    elif kind == "dual_grid_15":
        corner_names = ("top_left", "top_right", "bottom_right", "bottom_left")
        for corner in corner_names:
            rules[corner] = "This" if corner in neighbors else "NotThis"
        for card in ("top", "right", "bottom", "left"):
            rules[card] = "DontCare"
    else:  # wang_16, sides_16
        for card in ("top", "right", "bottom", "left"):
            rules[card] = "This" if card in neighbors else "NotThis"
        for corner in ("top_left", "top_right", "bottom_right", "bottom_left"):
            rules[corner] = "DontCare"

    return rules


def render_unity_ruletile_json(
    result: TerrainPatternResult,
    *,
    terrain_name: str = "Terrain",
) -> str:
    """Generate a clean JSON specification for Unity 2D RuleTile."""
    rules_list = []
    for tile in result.tiles:
        neighbor_rules = _unity_neighbor_rules(result.kind, tile.mask)
        rules_list.append({
            "index": tile.index,
            "column": tile.column,
            "row": tile.row,
            "mask": tile.mask,
            "probability": tile.probability,
            "neighbors": neighbor_rules,
        })
    payload = {
        "terrain_name": terrain_name,
        "kind": result.kind,
        "tile_width": result.tile_width,
        "tile_height": result.tile_height,
        "columns": result.columns,
        "rows": result.rows,
        "tiles": rules_list,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render_unity_ruletile_script(
    result: TerrainPatternResult,
    *,
    terrain_name: str = "Terrain",
    texture_name: str = "terrain_tiles.png",
) -> str:
    """Generate a Unity C# Editor script to create the RuleTile asset automatically."""
    safe_name = "".join(c for c in terrain_name if c.isalnum() or c == "_") or "Terrain"
    rule_entries = []
    for tile in result.tiles:
        rules = _unity_neighbor_rules(result.kind, tile.mask)
        pos_map = {
            "top_left": "new Vector3Int(-1, 1, 0)",
            "top": "new Vector3Int(0, 1, 0)",
            "top_right": "new Vector3Int(1, 1, 0)",
            "left": "new Vector3Int(-1, 0, 0)",
            "right": "new Vector3Int(1, 0, 0)",
            "bottom_left": "new Vector3Int(-1, -1, 0)",
            "bottom": "new Vector3Int(0, -1, 0)",
            "bottom_right": "new Vector3Int(1, -1, 0)",
        }
        neighbor_lines = []
        for dir_name, rule_val in rules.items():
            if rule_val == "DontCare":
                continue
            rule_enum = "RuleTile.TilingRuleOutput.Neighbor.This" if rule_val == "This" else "RuleTile.TilingRuleOutput.Neighbor.NotThis"
            neighbor_lines.append(f"            rule.m_NeighborPositions.Add({pos_map[dir_name]});")
            neighbor_lines.append(f"            rule.m_Neighbors.Add({rule_enum});")

        joined_neighbors = "\n".join(neighbor_lines)
        block = f"""        {{
            var rule = new RuleTile.TilingRule();
            rule.m_Sprites = new Sprite[] {{ GetSpriteAt(sprites, {tile.column}, {tile.row}, {result.columns}, {result.rows}) }};
{joined_neighbors}
            ruleTile.m_TilingRules.Add(rule);
        }}"""
        rule_entries.append(block)

    rules_code = "\n".join(rule_entries)

    return f"""#if UNITY_EDITOR
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Tilemaps;

// Generated by sprite-builder.
// Place this file in your Unity Assets/Editor/ folder.
// Select Tools > SpriteBuilder > Create RuleTile for {safe_name} to generate the RuleTile asset.
public static class Create{safe_name}RuleTile
{{
    [MenuItem("Tools/SpriteBuilder/Create RuleTile for {safe_name}")]
    public static void Generate()
    {{
        string scriptPath = new System.Diagnostics.StackTrace(true).GetFrame(0).GetFileName();
        string directory = Path.GetDirectoryName(scriptPath);
        string relativeDir = "Assets" + directory.Substring(Application.dataPath.Length);
        string texturePath = Path.Combine(relativeDir, "{texture_name}").Replace("\\\\", "/");
        string assetPath = Path.Combine(relativeDir, "{safe_name}_RuleTile.asset").Replace("\\\\", "/");

        Texture2D texture = AssetDatabase.LoadAssetAtPath<Texture2D>(texturePath);
        if (texture == null)
        {{
            EditorUtility.DisplayDialog("Error", "Could not find " + texturePath + ". Make sure the texture is in the same folder as this script.", "OK");
            return;
        }}

        ConfigureTextureImporter(texturePath, {result.tile_width}, {result.tile_height}, {result.columns}, {result.rows});

        Object[] allAssets = AssetDatabase.LoadAllAssetsAtPath(texturePath);
        List<Sprite> sprites = new List<Sprite>();
        foreach (var obj in allAssets)
        {{
            if (obj is Sprite s)
                sprites.Add(s);
        }}

        RuleTile ruleTile = ScriptableObject.CreateInstance<RuleTile>();
        ruleTile.m_TilingRules = new List<RuleTile.TilingRule>();

{rules_code}

        if (ruleTile.m_TilingRules.Count > 0 && ruleTile.m_TilingRules[0].m_Sprites.Length > 0)
        {{
            ruleTile.m_DefaultSprite = ruleTile.m_TilingRules[0].m_Sprites[0];
        }}

        AssetDatabase.CreateAsset(ruleTile, assetPath);
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        EditorUtility.DisplayDialog("Success", "RuleTile successfully created at " + assetPath, "OK");
    }}

    private static Sprite GetSpriteAt(List<Sprite> sprites, int col, int row, int cols, int rows)
    {{
        string targetName = Path.GetFileNameWithoutExtension("{texture_name}") + "_" + col + "_" + (rows - 1 - row);
        foreach (var s in sprites)
        {{
            if (s.name == targetName || s.name.EndsWith("_" + (row * cols + col)))
                return s;
        }}
        int index = row * cols + col;
        return index < sprites.Count ? sprites[index] : (sprites.Count > 0 ? sprites[0] : null);
    }}

    private static void ConfigureTextureImporter(string path, int tileW, int tileH, int cols, int rows)
    {{
        TextureImporter importer = AssetImporter.GetAtPath(path) as TextureImporter;
        if (importer == null) return;
        importer.isReadable = true;
        importer.textureType = TextureImporterType.Sprite;
        importer.spriteImportMode = SpriteImportMode.Multiple;
        importer.filterMode = FilterMode.Point;
        importer.textureCompression = TextureImporterCompression.Uncompressed;
        EditorUtility.SetDirty(importer);
        importer.SaveAndReimport();
    }}
}}
#endif
"""


def build_unity_ruletile_bundle(
    result: TerrainPatternResult,
    *,
    terrain_name: str = "Terrain",
) -> bytes:
    """Package a generated atlas, RuleTileConfig.json, and GenerateRuleTile.cs for Unity."""
    if not result.complete:
        raise ValueError(f"Terrain pattern has {len(result.unassigned_masks)} unassigned roles")
    atlas = io.BytesIO()
    result.image.save(atlas, format="PNG", optimize=False)
    bitmask_reference = io.BytesIO()
    render_terrain_bitmask_template(result.kind).save(bitmask_reference, format="PNG", optimize=False)

    safe_name = "".join(c for c in terrain_name if c.isalnum() or c == "_") or "Terrain"
    readme = f"""Unity 2D RuleTile Bundle for {safe_name}
Pattern: {result.kind} ({len(result.tiles)} tiles, {result.tile_width}x{result.tile_height} px)

INSTALLATION IN UNITY:
1. Copy all files from this ZIP into your Unity project under Assets/Tilesets/{safe_name}/ (or inside an Editor/ subfolder).
2. Select terrain_tiles.png in Unity's Project window:
   - Texture Type: Sprite (2D and UI)
   - Sprite Mode: Multiple
   - Pixels Per Unit: {result.tile_width}
   - Filter Mode: Point (no filter)
   - Compression: None
   - Open Sprite Editor and Slice by Cell Size ({result.tile_width}x{result.tile_height}), then click Apply.
3. In Unity's top menu bar, click:
   Tools > SpriteBuilder > Create RuleTile for {safe_name}
4. A new {safe_name}_RuleTile.asset will be generated with all 8-neighbor rules preconfigured!
5. Drag and drop the RuleTile asset into your Unity Tile Palette to paint seamlessly.

FILES INCLUDED:
- terrain_tiles.png: The compiled autotile sprite atlas.
- terrain_bitmask_reference.png: Visual peering reference map.
- RuleTileConfig.json: JSON specification of all neighbor rules for custom pipeline integrations.
- Create{safe_name}RuleTile.cs: Unity Editor script for 1-click asset creation.
"""

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("terrain_tiles.png", atlas.getvalue())
        bundle.writestr("terrain_bitmask_reference.png", bitmask_reference.getvalue())
        bundle.writestr("RuleTileConfig.json", render_unity_ruletile_json(result, terrain_name=terrain_name))
        bundle.writestr(f"Create{safe_name}RuleTile.cs", render_unity_ruletile_script(result, terrain_name=terrain_name))
        bundle.writestr("README_UNITY.txt", readme)
    return archive.getvalue()


def render_tiled_wangset_tsx(
    result: TerrainPatternResult,
    *,
    terrain_name: str = "Terrain",
    image_source: str = "terrain_tiles.png",
) -> str:
    """Generate a Tiled Map Editor TSX XML file with WangSet autotile definitions."""
    tile_count = result.columns * result.rows
    image_w = result.image.width
    image_h = result.image.height

    order = ("top", "top_right", "right", "bottom_right", "bottom", "bottom_left", "left", "top_left")

    wang_lines = []
    for tile in result.tiles:
        local_id = tile.row * result.columns + tile.column
        rules = _unity_neighbor_rules(result.kind, tile.mask)
        wang_vals = [("1" if rules.get(d) == "This" else "0") for d in order]
        wangid_str = ",".join(wang_vals)
        wang_lines.append(f'   <wangtile tileid="{local_id}" wangid="{wangid_str}"/>')

    wang_tiles_xml = "\n".join(wang_lines)

    anim_tiles_xml = ""
    if result.is_animated and result.animation_frames > 1:
        base_rows = result.base_rows or (result.rows // result.animation_frames)
        row_stride = base_rows * result.columns
        duration_ms = max(16, int(round(1000.0 / max(1.0, result.animation_fps))))
        tile_anim_lines: list[str] = []
        for tile in result.tiles:
            local_id = tile.row * result.columns + tile.column
            tile_anim_lines.append(f' <tile id="{local_id}">\n  <animation>')
            for f in range(result.animation_frames):
                frame_tile_id = local_id + f * row_stride
                tile_anim_lines.append(f'   <frame tileid="{frame_tile_id}" duration="{duration_ms}"/>')
            tile_anim_lines.append('  </animation>\n </tile>')
        anim_tiles_xml = "\n" + "\n".join(tile_anim_lines)

    wangset_type = "corner" if result.kind == "dual_grid_15" else ("edge" if result.kind in ("wang_16", "sides_16") else "mixed")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<tileset version="1.10" tiledversion="1.10.2" name="{terrain_name}" tilewidth="{result.tile_width}" tileheight="{result.tile_height}" tilecount="{tile_count}" columns="{result.columns}">
 <image source="{image_source}" width="{image_w}" height="{image_h}"/>{anim_tiles_xml}
 <wangsets>
  <wangset name="{terrain_name}" type="{wangset_type}" tile="-1">
   <wangcolor name="{terrain_name}" color="#44aa66" tile="-1" probability="1"/>
{wang_tiles_xml}
  </wangset>
 </wangsets>
</tileset>
"""


def build_tiled_bundle(
    result: TerrainPatternResult,
    *,
    terrain_name: str = "Terrain",
) -> bytes:
    """Package a generated atlas and Tiled Map Editor TSX file."""
    if not result.complete:
        raise ValueError(f"Terrain pattern has {len(result.unassigned_masks)} unassigned roles")
    atlas = io.BytesIO()
    result.image.save(atlas, format="PNG", optimize=False)
    bitmask_reference = io.BytesIO()
    render_terrain_bitmask_template(result.kind).save(bitmask_reference, format="PNG", optimize=False)
    safe_name = terrain_name.lower().replace(" ", "_") or "terrain"

    readme = f"""Tiled Map Editor Bundle for {terrain_name}
Pattern: {result.kind} ({len(result.tiles)} tiles, {result.tile_width}x{result.tile_height} px)

USAGE IN TILED:
1. Extract terrain_tiles.png and {safe_name}.tsx into your Tiled project folder.
2. In Tiled, select Map > Add External Tileset, and select {safe_name}.tsx.
3. Switch to the 'Terrain' / 'Wang Sets' tab in the Tilesets panel.
4. Select the '{terrain_name}' wangset and start painting seamlessly using Tiled's terrain brush!

FILES INCLUDED:
- terrain_tiles.png: The compiled autotile sprite atlas.
- {safe_name}.tsx: Tiled Map Editor external tileset with WangSet definitions.
- terrain_bitmask_reference.png: Visual bitmask layout reference.
"""

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("terrain_tiles.png", atlas.getvalue())
        bundle.writestr("terrain_bitmask_reference.png", bitmask_reference.getvalue())
        bundle.writestr(f"{safe_name}.tsx", render_tiled_wangset_tsx(result, terrain_name=terrain_name))
        bundle.writestr("README_TILED.txt", readme)
    return archive.getvalue()

