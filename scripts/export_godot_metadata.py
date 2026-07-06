#!/usr/bin/env python3
"""Export metadata JSON and a Godot 4 SpriteFrames .tres for an existing sheet."""

from __future__ import annotations

import argparse
import json
from math import ceil
from pathlib import Path

from PIL import Image

from sprite_builder.export import SheetResult, export_godot_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", nargs="+", type=Path)
    parser.add_argument("--sheet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--texture-resource", required=True, help="Godot res:// path")
    parser.add_argument("--animation", required=True)
    parser.add_argument("--fps", type=float, default=8.0)
    parser.add_argument("--no-loop", action="store_true")
    parser.add_argument("--cell-width", type=int, required=True)
    parser.add_argument("--cell-height", type=int, required=True)
    parser.add_argument("--columns", type=int)
    parser.add_argument("--anchors", type=Path)
    args = parser.parse_args()

    if args.cell_width <= 0 or args.cell_height <= 0:
        parser.error("Cell dimensions must be positive")
    with Image.open(args.sheet) as image:
        sheet_size = image.size
    columns = args.columns or len(args.frames)
    if columns <= 0:
        parser.error("--columns must be positive")
    rows = ceil(len(args.frames) / columns)
    expected = (columns * args.cell_width, rows * args.cell_height)
    if sheet_size != expected:
        parser.error(f"Sheet is {sheet_size}; expected {expected}")
    regions = tuple(
        (
            (index % columns) * args.cell_width,
            (index // columns) * args.cell_height,
            args.cell_width,
            args.cell_height,
        )
        for index in range(len(args.frames))
    )
    sheet = SheetResult(
        args.sheet,
        sheet_size,
        (args.cell_width, args.cell_height),
        columns,
        rows,
        regions,
        "horizontal" if rows == 1 else "grid",
    )
    anchors = None
    if args.anchors:
        data = json.loads(args.anchors.read_text(encoding="utf-8"))
        anchors = data.get("frames", data) if isinstance(data, dict) else data
        if not isinstance(anchors, list):
            parser.error("Anchor JSON must resolve to a list")
    metadata, tres = export_godot_bundle(
        sheet=sheet,
        frame_paths=args.frames,
        output_directory=args.output_dir,
        texture_resource_path=args.texture_resource,
        animation=args.animation,
        fps=args.fps,
        loop=not args.no_loop,
        anchors=anchors,
    )
    print(json.dumps({"metadata": str(metadata), "tres": str(tres)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
