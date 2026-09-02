"""Deterministic sprite post-processing primitives."""

from .alpha import (
    AlphaInspection,
    inspect_native_alpha,
    inspect_native_sheet_alpha,
    sanitize_transparent_rgb,
)
from .background import BackgroundRemovalResult, remove_background
from .crop import CropResult, autocut_sprite
from .pixelart import (
    PaletteReport,
    PaletteRole,
    ResizeVariant,
    normalize_sprite,
    quantize_palette,
    quantize_palette_with_report,
    resize_sprite_variants,
)

__all__ = [
    "AlphaInspection",
    "BackgroundRemovalResult",
    "CropResult",
    "PaletteReport",
    "PaletteRole",
    "ResizeVariant",
    "autocut_sprite",
    "inspect_native_alpha",
    "inspect_native_sheet_alpha",
    "normalize_sprite",
    "quantize_palette",
    "quantize_palette_with_report",
    "remove_background",
    "resize_sprite_variants",
    "sanitize_transparent_rgb",
]
