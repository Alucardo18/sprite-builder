"""Deterministic sprite post-processing primitives."""

from .background import BackgroundRemovalResult, remove_background
from .crop import CropResult, autocut_sprite
from .pixelart import normalize_sprite, quantize_palette

__all__ = [
    "BackgroundRemovalResult",
    "CropResult",
    "autocut_sprite",
    "normalize_sprite",
    "quantize_palette",
    "remove_background",
]
