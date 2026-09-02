"""Reusable terrain-pattern generation for Godot 4 TileSets."""

from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
from PIL import Image, ImageDraw

from .core import TilesetGrid, slice_tileset

TerrainPatternKind = Literal["wang_16", "dual_grid_15", "blob_47", "sides_16"]
TerrainEdgeProfile = Literal[
    "clean",
    "grass_over_dirt",
    "dirt_over_water",
    "grass_over_water",
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
_TERRAIN_EDGE_PROFILES: tuple[TerrainEdgeProfile, ...] = (
    "clean",
    "grass_over_dirt",
    "dirt_over_water",
    "grass_over_water",
)
_DUAL_GRID_TERRAIN_PROFILES = _TERRAIN_EDGE_PROFILES
_DUAL_GRID_EDGE_VARIATION_MAX = 3
_DUAL_GRID_EDGE_SEED_MAX = 999_999
_WANG_PATTERN_KINDS = frozenset(("wang_16", "dual_grid_15"))
_PATTERN_MODES = {
    "wang_16": "match_corners",
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
    # Official Godot 3.x 2x2/corners template.
    "wang_16": (
        (8, 6, 13, 12),
        (5, 14, 15, 11),
        (2, 3, 7, 9),
        (0, 4, 10, 1),
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

    return _DUAL_GRID_TERRAIN_PROFILES


def dual_grid_terrain_profiles() -> tuple[DualGridTerrainProfile, ...]:
    """Compatibility alias for the original Dual Grid profile API."""

    return terrain_edge_profiles()


def _normalize_terrain_edge_style(
    profile: object = "clean",
    variation: object = 0,
    seed: object = 0,
) -> tuple[TerrainEdgeProfile, int, int]:
    profile_name = str(profile or "clean")
    if profile_name not in _DUAL_GRID_TERRAIN_PROFILES:
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


def _wang_bitmap_coverage(mask: int, width: int, height: int) -> np.ndarray:
    nw, ne, se, sw = (1.0 if mask & (1 << index) else 0.0 for index in range(4))
    xs = (np.arange(width, dtype=np.float32) + 0.5) / width
    ys = (np.arange(height, dtype=np.float32) + 0.5) / height
    u, v = np.meshgrid(xs, ys)
    return nw * (1.0 - u) * (1.0 - v) + ne * u * (1.0 - v) + sw * (1.0 - u) * v + se * u * v


def _wang_bitmap_mask(mask: int, width: int, height: int) -> np.ndarray:
    return _wang_bitmap_coverage(mask, width, height) >= 0.5


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

    if profile == "grass_over_dirt":
        low_frequency = 2 + digest[0] % 2
        high_frequency = 4 + digest[1] % 3
        bias = 0.10
        low_weight, high_weight, cross_weight = 0.22, 0.58, 0.20
    elif profile == "dirt_over_water":
        low_frequency = 1 + digest[0] % 2
        high_frequency = 2 + digest[1] % 2
        bias = 0.28
        low_weight, high_weight, cross_weight = 0.58, 0.22, 0.20
    else:  # grass_over_water
        low_frequency = 2 + digest[0] % 2
        high_frequency = 3 + digest[1] % 3
        # Let a restrained amount of water bite into the grass silhouette.
        # Keeping this bias on the opposite side of the other two profiles is
        # important on small pixel grids, where sub-pixel waves can otherwise
        # quantize to the exact same bitmap for every material pair.
        bias = -0.10
        low_weight, high_weight, cross_weight = 0.34, 0.46, 0.20

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
) -> np.ndarray:
    """Return styled coverage while keeping compatible atlas edges deterministic."""

    normalizer = (
        _normalize_dual_grid_edge_style
        if kind == "dual_grid_15"
        else _normalize_terrain_edge_style
    )
    profile, variation, seed = normalizer(profile, variation, seed)
    if _is_wang_pattern(kind):
        coverage = _wang_bitmap_coverage(mask, width, height)
    elif kind == "sides_16":
        coverage = _blob_bitmap_coverage(_sides_blob_mask(mask), width, height)
    else:
        coverage = _blob_bitmap_coverage(mask, width, height)
    if profile == "clean" or variation == 0 or mask in _profile_terminal_masks(kind):
        return coverage

    # A displacement below one source pixel frequently vanishes after the
    # boolean threshold (all three profiles used to collapse to the same
    # bitmap at 8x8).  These levels remain restrained, but make even the
    # "subtle" preset cross a real pixel boundary on practical tile sizes.
    requested_pixels = (1.2, 1.8, 2.6)[variation - 1]
    profile_scale = {
        "grass_over_dirt": 1.0,
        "dirt_over_water": 0.84,
        "grass_over_water": 0.92,
    }[profile]
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
    if _is_wang_pattern(kind):
        nw, ne, se, sw = (1.0 if mask & (1 << index) else 0.0 for index in range(4))
        edge_x = (np.arange(width, dtype=np.float32) + 0.5) / width
        edge_y = (np.arange(height, dtype=np.float32) + 0.5) / height
        styled[0, :] = nw * (1.0 - edge_x) + ne * edge_x
        styled[-1, :] = sw * (1.0 - edge_x) + se * edge_x
        styled[:, 0] = nw * (1.0 - edge_y) + sw * edge_y
        styled[:, -1] = ne * (1.0 - edge_y) + se * edge_y
        styled[0, 0], styled[0, -1] = nw, ne
        styled[-1, -1], styled[-1, 0] = se, sw
    return np.asarray(styled, dtype=np.float32)


def _pixel_distance_to_mask(mask: np.ndarray) -> np.ndarray:
    """Return a deterministic four-neighbour distance map for a pixel mask."""

    target = np.asarray(mask, dtype=bool)
    height, width = target.shape
    unreachable = height + width + 1
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
    if profile == "clean" or variation == 0 or mask in _profile_terminal_masks(kind):
        return output

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


def _blob_bitmap_coverage(mask: int, width: int, height: int) -> np.ndarray:
    output = np.zeros((height, width), dtype=np.float32)
    half_width = width / 2.0
    half_height = height / 2.0
    for y in range(height):
        bottom = y + 0.5 >= half_height
        v = (height - (y + 0.5)) / half_height if bottom else (y + 0.5) / half_height
        for x in range(width):
            right = x + 0.5 >= half_width
            u = (width - (x + 0.5)) / half_width if right else (x + 0.5) / half_width
            diagonal, horizontal, vertical = _blob_quadrant_values(mask, right, bottom)
            coverage = (
                diagonal * (1.0 - u) * (1.0 - v)
                + horizontal * u * (1.0 - v)
                + vertical * (1.0 - u) * v
                + u * v
            )
            output[y, x] = coverage
    return output


def _blob_bitmap_mask(mask: int, width: int, height: int) -> np.ndarray:
    return _blob_bitmap_coverage(mask, width, height) >= 0.5


def _tile_neighbors(kind: TerrainPatternKind, mask: int) -> tuple[str, ...]:
    if _is_wang_pattern(kind):
        return tuple(name for index, name in enumerate(_WANG_CORNERS) if mask & (1 << index))
    if kind == "sides_16":
        return tuple(
            name
            for index, name in enumerate(("top", "right", "bottom", "left"))
            if mask & (1 << index)
        )
    return tuple(name for name in _DIRECTIONS if mask & _DIRECTION_BITS[name])


def _relevant_directions(kind: TerrainPatternKind) -> tuple[str, ...]:
    if _is_wang_pattern(kind):
        return _WANG_CORNERS
    if kind == "sides_16":
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
            if _is_wang_pattern(kind):
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
                    if kind == "sides_16" and "_" in direction:
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

    x = max(0, _object_int(fragment.get("x"), 0))
    y = max(0, _object_int(fragment.get("y"), 0))
    width = max(1, _object_int(fragment.get("width"), 1))
    height = max(1, _object_int(fragment.get("height"), 1))
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
            if _is_wang_pattern(kind):
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
    return _fit_source(
        atlas.convert("RGBA").crop(_fragment_bounds(source, atlas.size)),
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
    terrain_profile_name, terrain_edge_variation, terrain_edge_seed = _normalize_pattern_edge_style(
        kind,
        set_config.get("terrainProfile", "clean"),
        set_config.get("edgeVariation", 0),
        set_config.get("edgeSeed", 0),
    )
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
    required_bases = base is not None and (not _is_wang_pattern(kind) or secondary is not None)
    all_edges_ready = all(edge_images[direction] is not None for direction in edge_images)
    # Dual Grid depends only on its two terrain Sources. Hidden edge/corner
    # fields from migrated configurations are deliberately discarded.
    ready = required_bases and (kind == "dual_grid_15" or all_edges_ready)
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
        elif _is_wang_pattern(kind) and secondary is not None:
            if kind == "dual_grid_15":
                tile = Image.fromarray(
                    _render_dual_grid_pixels(
                        np.asarray(base, dtype=np.uint8),
                        np.asarray(secondary, dtype=np.uint8),
                        mask,
                        kind=kind,
                        profile=terrain_profile_name,
                        variation=terrain_edge_variation,
                        seed=terrain_edge_seed,
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
            transitions = _wang_transitions(mask)
            for direction, present in transitions.items():
                if not present:
                    continue
                if kind != "dual_grid_15" and edge_images[direction] is None:
                    _draw_missing_border(tile, direction)
            if kind == "wang_16" and terrain_profile_name != "clean":
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
                profile_coverage = (
                    _authored_edge_profile_coverage(
                        authored_edge_ownership,
                        size[0],
                        size[1],
                    )
                    if authored_edge_ownership is not None
                    else None
                )
                if profile_coverage is not None and authored_edge_ownership is not None:
                    tile = Image.fromarray(
                        _render_dual_grid_pixels(
                            np.asarray(base, dtype=np.uint8),
                            np.asarray(
                                next(
                                    (edge for edge in edge_images.values() if edge is not None),
                                    base,
                                ),
                                dtype=np.uint8,
                            ),
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
                source_index=(
                    0 if ready or (kind != "dual_grid_15" and override is not None) else None
                ),
                generated=override is None,
                override_source_index=0 if override is not None else None,
            )
        )
    if kind == "dual_grid_15" and secondary is not None:
        _place_dual_grid_background(output, secondary, size)
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
        "schema_version": "1.0",
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
        manifest["edge_profile"] = {
            "terrain_profile": result.terrain_profile or "clean",
            "edge_variation": result.edge_variation,
            "edge_seed": result.edge_seed,
            "edge_generation": "deterministic_palette_bands",
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
            f'"peers": {{{peers}}}}},'
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
        var tile_data := atlas.get_tile_data(coords, 0)
        tile_data.terrain_set = 0
        tile_data.terrain = entry["terrain"]
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
