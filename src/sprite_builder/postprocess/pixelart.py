from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from PIL import Image
from skimage.color import deltaE_ciede2000, rgb2lab

ResampleMethod = Literal[
    "legacy",
    "premultiplied_area",
    "premultiplied_lanczos",
    "pixel_majority",
    "edge_aware",
]


@dataclass(frozen=True, slots=True)
class PaletteRole:
    name: str
    colors: tuple[tuple[int, int, int], ...]
    match_colors: tuple[tuple[int, int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class PaletteReport:
    foreground_pixels: int
    quantized_pixels: int
    preserved_pixels: int
    unique_colors_before: int
    unique_colors_after: int
    mean_delta_e00: float
    max_delta_e00: float
    role_pixels: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResizeVariant:
    method: ResampleMethod
    image: Image.Image
    score: float
    alpha_iou: float
    component_similarity: float
    hard_alpha_ratio: float
    edge_contrast: float

    def metrics_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "score": self.score,
            "alpha_iou": self.alpha_iou,
            "component_similarity": self.component_similarity,
            "hard_alpha_ratio": self.hard_alpha_ratio,
            "edge_contrast": self.edge_contrast,
        }


def _image(value: str | Path | Image.Image) -> Image.Image:
    return (Image.open(value) if not isinstance(value, Image.Image) else value).convert("RGBA")


def quantize_palette(
    image: str | Path | Image.Image,
    palette: list[tuple[int, int, int]],
    *,
    alpha_thresholds: tuple[int, int] = (32, 223),
) -> Image.Image:
    if not palette:
        raise ValueError("Palette must not be empty")
    arr = np.asarray(_image(image)).copy()
    lab = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    pal_rgb = np.uint8(palette).reshape(-1, 1, 3)
    pal_lab = cv2.cvtColor(pal_rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    flat = lab.reshape(-1, 3)
    nearest = np.argmin(((flat[:, None] - pal_lab[None]) ** 2).sum(axis=2), axis=1)
    arr[:, :, :3] = np.asarray(palette, np.uint8)[nearest].reshape(arr.shape[:2] + (3,))
    lo, hi = alpha_thresholds
    alpha = arr[:, :, 3]
    alpha[alpha < lo] = 0
    alpha[alpha > hi] = 255
    return Image.fromarray(arr, "RGBA")


def quantize_palette_with_report(
    image: str | Path | Image.Image,
    palette: Sequence[tuple[int, int, int]],
    *,
    roles: Sequence[PaletteRole] = (),
    max_delta_e00: float | None = None,
    alpha_thresholds: tuple[int, int] = (32, 223),
) -> tuple[Image.Image, PaletteReport]:
    """Quantize with optional role routing and preserve colors beyond a Delta-E limit."""

    if not palette:
        raise ValueError("Palette must not be empty")
    source = np.asarray(_image(image)).copy()
    foreground = source[:, :, 3] > 0
    pixels = source[:, :, :3][foreground]
    if not len(pixels):
        raise ValueError("Cannot quantize an empty sprite")
    pixel_lab = rgb2lab(pixels.astype(np.float32).reshape(-1, 1, 3) / 255.0).reshape(-1, 3)
    active_roles = tuple(roles) or (PaletteRole("default", tuple(palette)),)
    output_pixels = pixels.copy()
    selected_delta = np.full(len(pixels), np.inf, dtype=np.float32)
    selected_color = pixels.copy()
    selected_role = np.full(len(pixels), -1, dtype=np.int32)

    role_match_distances: list[np.ndarray] = []
    for role in active_roles:
        matches = role.match_colors or role.colors
        match_lab = rgb2lab(np.asarray(matches, np.float32).reshape(-1, 1, 3) / 255.0).reshape(
            -1, 3
        )
        distances = np.stack(
            [deltaE_ciede2000(pixel_lab, match[None, :]) for match in match_lab], axis=1
        )
        role_match_distances.append(distances.min(axis=1))
    routing = np.argmin(np.stack(role_match_distances, axis=1), axis=1)

    for role_index, role in enumerate(active_roles):
        routed = routing == role_index
        if not routed.any():
            continue
        target_lab = rgb2lab(
            np.asarray(role.colors, np.float32).reshape(-1, 1, 3) / 255.0
        ).reshape(-1, 3)
        distances = np.stack(
            [deltaE_ciede2000(pixel_lab[routed], target[None, :]) for target in target_lab], axis=1
        )
        nearest = distances.argmin(axis=1)
        target_delta = distances[np.arange(len(nearest)), nearest]
        selected_delta[routed] = target_delta
        selected_color[routed] = np.asarray(role.colors, np.uint8)[nearest]
        selected_role[routed] = role_index

    apply = np.isfinite(selected_delta)
    if max_delta_e00 is not None:
        apply &= selected_delta <= max_delta_e00
    role_counts = {
        role.name: int(((routing == role_index) & apply).sum())
        for role_index, role in enumerate(active_roles)
    }
    output_pixels[apply] = selected_color[apply]
    source[:, :, :3][foreground] = output_pixels
    lo, hi = alpha_thresholds
    alpha = source[:, :, 3]
    alpha[alpha < lo] = 0
    alpha[alpha > hi] = 255
    finite = selected_delta[np.isfinite(selected_delta)]
    report = PaletteReport(
        foreground_pixels=len(pixels),
        quantized_pixels=int(apply.sum()),
        preserved_pixels=int((~apply).sum()),
        unique_colors_before=len(np.unique(pixels, axis=0)),
        unique_colors_after=len(np.unique(output_pixels, axis=0)),
        mean_delta_e00=float(finite.mean()) if len(finite) else 0.0,
        max_delta_e00=float(finite.max()) if len(finite) else 0.0,
        role_pixels=role_counts,
    )
    return Image.fromarray(source, "RGBA"), report


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    value = rgb.astype(np.float32) / 255.0
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    value = np.clip(rgb, 0.0, 1.0)
    srgb = np.where(value <= 0.0031308, value * 12.92, 1.055 * value ** (1 / 2.4) - 0.055)
    return np.clip(np.rint(srgb * 255.0), 0, 255).astype(np.uint8)


def _premultiplied_resize(
    rgba: np.ndarray,
    size: tuple[int, int],
    interpolation: int,
    *,
    hard_alpha: bool = False,
) -> np.ndarray:
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    premultiplied = _srgb_to_linear(rgba[:, :, :3]) * alpha[:, :, None]
    resized_alpha = cv2.resize(alpha, size, interpolation=interpolation)
    resized_rgb = cv2.resize(premultiplied, size, interpolation=interpolation)
    if resized_rgb.ndim == 2:
        resized_rgb = resized_rgb[:, :, None]
    if hard_alpha:
        coverage = float((alpha > 0.5).mean())
        if coverage <= 0:
            threshold = 1.0
        else:
            threshold = float(np.quantile(resized_alpha, max(0.0, 1.0 - coverage)))
        resized_alpha = (resized_alpha >= max(threshold, 0.08)).astype(np.float32)
    safe = np.maximum(resized_alpha[:, :, None], 1e-6)
    straight = np.where(resized_alpha[:, :, None] > 0, resized_rgb / safe, 0.0)
    return np.dstack((_linear_to_srgb(straight), np.rint(resized_alpha * 255).astype(np.uint8)))


def _pixel_majority_resize(rgba: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Collapse source regions to representative hard pixels without color averaging."""

    source_height, source_width = rgba.shape[:2]
    target_width, target_height = size
    result = np.zeros((target_height, target_width, 4), dtype=np.uint8)
    for y in range(target_height):
        y0 = int(np.floor(y * source_height / target_height))
        y1 = max(y0 + 1, int(np.ceil((y + 1) * source_height / target_height)))
        for x in range(target_width):
            x0 = int(np.floor(x * source_width / target_width))
            x1 = max(x0 + 1, int(np.ceil((x + 1) * source_width / target_width)))
            block = rgba[y0:y1, x0:x1]
            opaque = block[:, :, 3] > 127
            if float(opaque.mean()) < 0.5:
                continue
            colors = block[:, :, :3][opaque]
            mean = colors.astype(np.float32).mean(axis=0)
            representative = colors[np.argmin(((colors.astype(np.float32) - mean) ** 2).sum(1))]
            result[y, x, :3] = representative
            result[y, x, 3] = 255
    return result


def _component_count(mask: np.ndarray) -> int:
    return max(0, cv2.connectedComponents(mask.astype(np.uint8), 8)[0] - 1)


def _variant_score(
    source: np.ndarray, candidate: np.ndarray
) -> tuple[float, float, float, float, float]:
    source_mask = source[:, :, 3] > 8
    candidate_mask = candidate[:, :, 3] > 8
    restored = cv2.resize(
        candidate_mask.astype(np.uint8),
        (source.shape[1], source.shape[0]),
        interpolation=cv2.INTER_NEAREST,
    ).astype(bool)
    union = np.logical_or(source_mask, restored).sum()
    alpha_iou = float(np.logical_and(source_mask, restored).sum() / union) if union else 1.0
    source_components = _component_count(source_mask)
    candidate_components = _component_count(candidate_mask)
    component_similarity = 1.0 / (1.0 + abs(source_components - candidate_components))
    alpha = candidate[:, :, 3]
    hard_alpha_ratio = float(((alpha == 0) | (alpha == 255)).mean())
    gray = cv2.cvtColor(candidate[:, :, :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    edge_contrast = float(np.clip(np.hypot(gradient_x, gradient_y).mean() / 255.0, 0, 1))
    score = (
        0.60 * alpha_iou
        + 0.15 * component_similarity
        + 0.10 * hard_alpha_ratio
        + 0.15 * edge_contrast
    )
    return score, alpha_iou, component_similarity, hard_alpha_ratio, edge_contrast


def resize_sprite_variants(
    image: str | Path | Image.Image,
    size: tuple[int, int],
    *,
    methods: Sequence[ResampleMethod] = (
        "premultiplied_area",
        "premultiplied_lanczos",
        "pixel_majority",
        "edge_aware",
    ),
) -> tuple[ResizeVariant, ...]:
    """Build and score deterministic logical-resolution candidates."""

    rgba = np.asarray(_image(image))
    variants: list[ResizeVariant] = []
    for method in methods:
        if method == "legacy":
            interpolation = cv2.INTER_AREA if size[0] < rgba.shape[1] else cv2.INTER_NEAREST
            candidate = cv2.resize(rgba, size, interpolation=interpolation)
        elif method == "premultiplied_area":
            candidate = _premultiplied_resize(rgba, size, cv2.INTER_AREA)
        elif method == "premultiplied_lanczos":
            candidate = _premultiplied_resize(rgba, size, cv2.INTER_LANCZOS4)
        elif method == "pixel_majority":
            candidate = _pixel_majority_resize(rgba, size)
        elif method == "edge_aware":
            candidate = _premultiplied_resize(
                rgba, size, cv2.INTER_LANCZOS4, hard_alpha=True
            )
        else:
            raise ValueError(f"Unsupported resample method: {method}")
        score, alpha_iou, component_similarity, hard_alpha_ratio, edge_contrast = (
            _variant_score(rgba, candidate)
        )
        variants.append(
            ResizeVariant(
                method=method,
                image=Image.fromarray(candidate.astype(np.uint8), "RGBA"),
                score=score,
                alpha_iou=alpha_iou,
                component_similarity=component_similarity,
                hard_alpha_ratio=hard_alpha_ratio,
                edge_contrast=edge_contrast,
            )
        )
    return tuple(variants)


def normalize_sprite(
    image: str | Path | Image.Image,
    *,
    target_body_height: int,
    source_body_height: int | None = None,
    palette: list[tuple[int, int, int]] | None = None,
    method: ResampleMethod = "legacy",
) -> Image.Image:
    """Scale once to a fixed canonical body height.

    Callers should pass the same ``source_body_height`` for every frame.
    When omitted, the alpha bounding-box height is used (suited to calibration,
    not weapon-heavy animation frames).
    """
    rgba = _image(image)
    arr = np.asarray(rgba)
    if source_body_height is None:
        ys = np.where(arr[:, :, 3] > 8)[0]
        if not len(ys):
            raise ValueError("Cannot normalize an empty sprite")
        source_body_height = int(ys.max() - ys.min() + 1)
    if source_body_height <= 0 or target_body_height <= 0:
        raise ValueError("Body heights must be positive")
    scale = target_body_height / source_body_height
    size = (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale)))
    result = max(
        resize_sprite_variants(rgba, size, methods=(method,)),
        key=lambda item: item.score,
    ).image
    return quantize_palette(result, palette) if palette else result
