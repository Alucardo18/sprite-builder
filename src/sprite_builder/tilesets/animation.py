"""Algorithmic frame synthesis and vertical sheet stacking for animated autotiles."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from PIL import Image

TerrainAnimationStyle = Literal[
    "water_waves",
    "shore_ripples",
    "lava_pulse",
    "wind_sway",
]

_VALID_ANIMATION_STYLES = frozenset(
    {"water_waves", "shore_ripples", "lava_pulse", "wind_sway"}
)


@dataclass(frozen=True, slots=True)
class TerrainAnimationConfig:
    """Settings controlling autotile frame synthesis and playback."""

    enabled: bool = False
    style: TerrainAnimationStyle = "shore_ripples"
    frame_count: int = 4
    fps: float = 8.0
    speed: float = 1.0
    wave_amplitude: float = 1.0
    foam_intensity: float = 1.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> TerrainAnimationConfig:
        if not data:
            return cls(enabled=False)
        enabled = bool(
            data.get("animated")
            or data.get("is_animated")
            or data.get("animation_enabled")
            or False
        )
        style_val = str(data.get("animationStyle", data.get("animation_style", "shore_ripples")))
        style: TerrainAnimationStyle = (
            style_val if style_val in _VALID_ANIMATION_STYLES else "shore_ripples"  # type: ignore[assignment]
        )
        try:
            raw_frames = int(data.get("animationFrames", data.get("animation_frames", 4)))
            frames = max(2, min(16, raw_frames))
        except (ValueError, TypeError):
            frames = 4
        try:
            raw_fps = float(data.get("animationFps", data.get("animation_fps", 8.0)))
            fps = max(1.0, min(60.0, raw_fps))
        except (ValueError, TypeError):
            fps = 8.0

        return cls(
            enabled=enabled,
            style=style,
            frame_count=frames,
            fps=fps,
        )


def synthesize_animated_tile_frame(
    pixels: np.ndarray,
    owned: np.ndarray,
    *,
    frame_index: int,
    frame_count: int,
    style: TerrainAnimationStyle = "shore_ripples",
    seed: int = 0,
) -> np.ndarray:
    """Synthesize one loop-closed frame of an autotile using continuous wave phases.

    Invariants:
    - Shared land borders and port rings are NEVER corrupted.
    - Animation loops seamlessly from frame_count - 1 back to frame 0.
    """
    if frame_count <= 1 or frame_index == 0:
        return pixels.copy()

    height, width = owned.shape
    output = pixels.copy()
    phi = 2.0 * math.pi * float(frame_index) / float(frame_count)
    yy, xx = np.indices((height, width), dtype=np.float32)

    # Protect outer perimeter for non-water land boundaries to guarantee seam compatibility
    editable = np.ones_like(owned, dtype=bool)
    editable[[0, -1], :] = False
    editable[:, [0, -1]] = False

    water_mask = ~owned
    land_mask = owned

    if style in {"water_waves", "shore_ripples"}:
        # 1. Subtle rhythmic wave motion in water bodies
        freq_x = max(8.0, float(width) / 2.0)
        freq_y = max(8.0, float(height) / 2.0)
        wave1 = np.sin(2.0 * math.pi * (xx / freq_x) - phi)
        wave2 = np.cos(2.0 * math.pi * (yy / freq_y + xx / (freq_x * 2.0)) - phi * 1.5)
        wave = 0.65 * wave1 + 0.35 * wave2

        # Apply ripples strictly on water pixels
        ripple_crest = water_mask & (wave > 0.42)
        ripple_trough = water_mask & (wave < -0.42)
        
        # Lighten crests, darken troughs
        output[..., :3][ripple_crest] = np.clip(
            output[..., :3][ripple_crest].astype(np.float32) * 1.14 + 8,
            0,
            255,
        ).astype(np.uint8)
        output[..., :3][ripple_trough] = np.clip(
            output[..., :3][ripple_trough].astype(np.float32) * 0.88,
            0,
            255,
        ).astype(np.uint8)

        # 2. Coastline Foam Pulsing (shore waves lapping against the shore)
        if style == "shore_ripples" and np.any(land_mask) and np.any(water_mask):
            from .patterns import _pixel_distance_to_mask

            outside_dist = _pixel_distance_to_mask(land_mask)
            pulse = 0.5 + 0.5 * math.sin(phi)  # 0.0 to 1.0 continuous sinusoidal breathing
            
            # Foam extends further up at high pulse
            foam_band = water_mask & (outside_dist <= (1.0 + pulse * 1.3)) & editable
            
            # Blend bright white-cyan foam crest
            output[..., 0][foam_band] = np.clip(
                output[..., 0][foam_band].astype(np.float32) * 0.35 + 175,
                0,
                255,
            ).astype(np.uint8)
            output[..., 1][foam_band] = np.clip(
                output[..., 1][foam_band].astype(np.float32) * 0.35 + 210,
                0,
                255,
            ).astype(np.uint8)
            output[..., 2][foam_band] = np.clip(
                output[..., 2][foam_band].astype(np.float32) * 0.25 + 240,
                0,
                255,
            ).astype(np.uint8)

    elif style == "lava_pulse":
        # Breathing heat core and rising hot currents
        pulse = 0.90 + 0.18 * math.sin(phi)
        crawl = np.sin(2.0 * math.pi * (yy / 12.0 - xx / 16.0) - phi)
        hot = water_mask & (crawl > 0.40) & editable
        output[..., :3][water_mask] = np.clip(
            output[..., :3][water_mask].astype(np.float32) * pulse,
            0,
            255,
        ).astype(np.uint8)
        output[..., :3][hot] = np.clip(
            output[..., :3][hot].astype(np.float32) * 1.25 + 25,
            0,
            255,
        ).astype(np.uint8)

    elif style == "wind_sway":
        # Subtle breeze sway on interior land vegetation
        sway = np.sin(phi + xx / 8.0)
        sway_mask = land_mask & editable & (sway > 0.50)
        output[..., :3][sway_mask] = np.clip(
            output[..., :3][sway_mask].astype(np.float32) * 1.08 + 6,
            0,
            255,
        ).astype(np.uint8)

    return output


def build_animated_terrain_frames(
    base_image: Image.Image,
    tiles: Sequence[Any],
    *,
    tile_width: int,
    tile_height: int,
    config: TerrainAnimationConfig,
    kind: str = "blob_47",
    edge_seed: int = 0,
) -> tuple[Image.Image, tuple[Image.Image, ...]]:
    """Build a multi-frame vertical stack atlas and individual frame images.

    Returns:
        (combined_stacked_atlas, tuple_of_individual_frame_images)
    """
    frame_count = config.frame_count
    if not config.enabled or frame_count <= 1:
        return base_image, (base_image,)

    from .patterns import _blob_bitmap_coverage

    frame_images: list[Image.Image] = [base_image]

    # Render frames 1 to N-1
    for frame_idx in range(1, frame_count):
        frame_canvas = base_image.copy()
        for tile in tiles:
            mask = getattr(tile, "mask", 0)
            col = getattr(tile, "column", 0)
            row = getattr(tile, "row", 0)

            # Extract cell pixels
            box = (
                col * tile_width,
                row * tile_height,
                (col + 1) * tile_width,
                (row + 1) * tile_height,
            )
            tile_crop = frame_canvas.crop(box)
            pix = np.asarray(tile_crop, dtype=np.uint8).copy()

            # Determine ownership
            if mask == 0:
                owned = np.zeros((tile_height, tile_width), dtype=bool)
            elif mask == 255:
                owned = np.ones((tile_height, tile_width), dtype=bool)
            else:
                cov = _blob_bitmap_coverage(mask, tile_width, tile_height)
                owned = cov >= 0.5

            anim_pix = synthesize_animated_tile_frame(
                pix,
                owned,
                frame_index=frame_idx,
                frame_count=frame_count,
                style=config.style,
                seed=edge_seed,
            )
            frame_canvas.paste(Image.fromarray(anim_pix, mode="RGBA"), box)

        frame_images.append(frame_canvas)

    # Vertical stack: Frame 0 on top, Frame 1..N-1 underneath
    stacked_height = base_image.height * frame_count
    combined = Image.new("RGBA", (base_image.width, stacked_height), (0, 0, 0, 0))
    for idx, frame_img in enumerate(frame_images):
        combined.paste(frame_img, (0, idx * base_image.height))

    return combined, tuple(frame_images)
