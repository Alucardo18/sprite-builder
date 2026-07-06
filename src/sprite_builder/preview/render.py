"""Preview helpers that preserve hard pixel edges."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw


def _load_frames(frame_paths: Iterable[str | Path]) -> list[Image.Image]:
    paths = tuple(Path(path) for path in frame_paths)
    if not paths:
        raise ValueError("At least one frame is required")
    return [Image.open(path).convert("RGBA") for path in paths]


def _fit_canvas(frames: Sequence[Image.Image]) -> tuple[int, int]:
    return max(frame.width for frame in frames), max(frame.height for frame in frames)


def _center(frame: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(frame, ((size[0] - frame.width) // 2, (size[1] - frame.height) // 2))
    return canvas


def create_animation_gif(
    frame_paths: Iterable[str | Path],
    output_path: str | Path,
    *,
    fps: float = 8.0,
    scale: int = 4,
    loop: bool = True,
) -> Path:
    if fps <= 0 or scale <= 0:
        raise ValueError("FPS and scale must be positive")
    frames = _load_frames(frame_paths)
    try:
        size = _fit_canvas(frames)
        rendered = [
            _center(frame, size).resize(
                (size[0] * scale, size[1] * scale), Image.Resampling.NEAREST
            )
            for frame in frames
        ]
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        rendered[0].save(
            destination,
            save_all=True,
            append_images=rendered[1:],
            duration=max(1, round(1000 / fps)),
            loop=0 if loop else 1,
            disposal=2,
            optimize=False,
        )
        return destination
    finally:
        for frame in frames:
            frame.close()


def create_contact_sheet(
    frame_paths: Iterable[str | Path],
    output_path: str | Path,
    *,
    columns: int = 4,
    scale: int = 2,
    background: tuple[int, int, int, int] = (34, 34, 42, 255),
) -> Path:
    if columns <= 0 or scale <= 0:
        raise ValueError("Columns and scale must be positive")
    frames = _load_frames(frame_paths)
    try:
        width, height = _fit_canvas(frames)
        rows = ceil(len(frames) / columns)
        sheet = Image.new("RGBA", (columns * width, rows * height), background)
        for index, frame in enumerate(frames):
            cell = _center(frame, (width, height))
            sheet.alpha_composite(cell, ((index % columns) * width, (index // columns) * height))
        if scale != 1:
            sheet = sheet.resize(
                (sheet.width * scale, sheet.height * scale),
                Image.Resampling.NEAREST,
            )
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(destination, format="PNG", optimize=False)
        return destination
    finally:
        for frame in frames:
            frame.close()


def create_anchor_overlay(
    frame_paths: Iterable[str | Path],
    anchors: Sequence[Sequence[float] | Mapping[str, object]],
    output_path: str | Path,
    *,
    columns: int = 4,
    scale: int = 3,
) -> Path:
    """Create a contact sheet with torso crosshairs and frame indices."""

    if columns <= 0 or scale <= 0:
        raise ValueError("Columns and scale must be positive")
    frames = _load_frames(frame_paths)
    if len(frames) != len(anchors):
        for frame in frames:
            frame.close()
        raise ValueError("Anchor count and frame count differ")
    try:
        width, height = _fit_canvas(frames)
        rows = ceil(len(frames) / columns)
        sheet = Image.new("RGBA", (columns * width, rows * height), (28, 28, 36, 255))
        draw = ImageDraw.Draw(sheet)
        for index, (frame, raw_anchor) in enumerate(zip(frames, anchors, strict=True)):
            ox = (index % columns) * width
            oy = (index // columns) * height
            centered_x = (width - frame.width) // 2
            centered_y = (height - frame.height) // 2
            sheet.alpha_composite(frame, (ox + centered_x, oy + centered_y))
            if isinstance(raw_anchor, Mapping):
                value = raw_anchor.get("override") or raw_anchor.get("torso_anchor")
                if value is None:
                    value = raw_anchor.get("auto")
                if not isinstance(value, Sequence):
                    raise ValueError(f"Frame {index} has no usable anchor")
                anchor = value
            else:
                anchor = raw_anchor
            x = ox + centered_x + round(float(anchor[0]))
            y = oy + centered_y + round(float(anchor[1]))
            radius = max(2, min(width, height) // 24)
            draw.line((x - radius, y, x + radius, y), fill=(255, 47, 79, 255), width=1)
            draw.line((x, y - radius, x, y + radius), fill=(255, 47, 79, 255), width=1)
            draw.rectangle((ox, oy, ox + width - 1, oy + height - 1), outline=(86, 92, 110, 255))
            draw.text((ox + 3, oy + 2), str(index), fill=(255, 255, 255, 255))
        if scale != 1:
            sheet = sheet.resize(
                (sheet.width * scale, sheet.height * scale),
                Image.Resampling.NEAREST,
            )
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(destination, format="PNG", optimize=False)
        return destination
    finally:
        for frame in frames:
            frame.close()
