"""Build pixel-exact horizontal or grid sprite sheets."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Literal

from PIL import Image

Layout = Literal["horizontal", "vertical", "grid"]
FrameInput = str | Path | Image.Image


@dataclass(frozen=True)
class SheetResult:
    output_path: Path
    sheet_size: tuple[int, int]
    cell_size: tuple[int, int]
    columns: int
    rows: int
    regions: tuple[tuple[int, int, int, int], ...]
    layout: Layout = "horizontal"

    def as_dict(self) -> dict[str, object]:
        return {
            "path": str(self.output_path),
            "sheet_size": list(self.sheet_size),
            "cell_size": list(self.cell_size),
            "columns": self.columns,
            "rows": self.rows,
            "layout": self.layout,
            "regions": [list(region) for region in self.regions],
        }


def build_spritesheet(
    frame_paths: Iterable[FrameInput],
    output_path: str | Path,
    *,
    layout: Layout = "horizontal",
    columns: int | None = None,
    cell_size: tuple[int, int] | None = None,
) -> SheetResult:
    """Place RGBA frames in fixed cells without filtering or rescaling.

    Smaller images are centered in their cells. A frame larger than the cell is
    rejected, since shrinking one animation frame would break body consistency.
    """

    sources = tuple(frame_paths)
    if not sources:
        raise ValueError("At least one frame is required")
    if layout not in ("horizontal", "vertical", "grid"):
        raise ValueError(f"Unsupported layout: {layout}")

    images = tuple(
        (
            source.convert("RGBA")
            if isinstance(source, Image.Image)
            else Image.open(source).convert("RGBA")
        )
        for source in sources
    )
    try:
        natural = (
            max(image.width for image in images),
            max(image.height for image in images),
        )
        width, height = cell_size or natural
        if width <= 0 or height <= 0:
            raise ValueError("Cell dimensions must be positive")
        for source, image in zip(sources, images, strict=True):
            if image.width > width or image.height > height:
                raise ValueError(
                    f"CELL_OVERFLOW: {source} is {image.size}, cell is {(width, height)}"
                )

        if layout == "horizontal":
            actual_columns = len(images)
        elif layout == "vertical":
            actual_columns = 1
        else:
            actual_columns = columns or ceil(len(images) ** 0.5)
            if actual_columns <= 0:
                raise ValueError("Grid columns must be positive")
        rows = ceil(len(images) / actual_columns)
        sheet = Image.new("RGBA", (actual_columns * width, rows * height), (0, 0, 0, 0))
        regions: list[tuple[int, int, int, int]] = []
        for index, image in enumerate(images):
            column = index % actual_columns
            row = index // actual_columns
            cell_x, cell_y = column * width, row * height
            offset_x = cell_x + (width - image.width) // 2
            offset_y = cell_y + (height - image.height) // 2
            sheet.alpha_composite(image, (offset_x, offset_y))
            regions.append((cell_x, cell_y, width, height))

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(destination, format="PNG", optimize=False)
        return SheetResult(
            output_path=destination,
            sheet_size=sheet.size,
            cell_size=(width, height),
            columns=actual_columns,
            rows=rows,
            regions=tuple(regions),
            layout=layout,
        )
    finally:
        for image in images:
            image.close()
