#!/usr/bin/env python3
"""Build a horizontal or grid PNG sprite sheet without resampling frames."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sprite_builder.export import build_spritesheet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", nargs="+", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--layout", choices=("horizontal", "grid"), default="horizontal")
    parser.add_argument("--columns", type=int)
    parser.add_argument("--cell-width", type=int)
    parser.add_argument("--cell-height", type=int)
    parser.add_argument("--manifest", type=Path, help="Optional JSON sheet manifest")
    args = parser.parse_args()
    if (args.cell_width is None) != (args.cell_height is None):
        parser.error("--cell-width and --cell-height must be supplied together")
    result = build_spritesheet(
        args.frames,
        args.output,
        layout=args.layout,
        columns=args.columns,
        cell_size=((args.cell_width, args.cell_height) if args.cell_width is not None else None),
    )
    payload = result.as_dict()
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
