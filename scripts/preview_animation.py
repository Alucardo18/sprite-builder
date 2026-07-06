#!/usr/bin/env python3
"""Create nearest-neighbor GIF, contact-sheet, or torso-anchor previews."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sprite_builder.preview import (
    create_anchor_overlay,
    create_animation_gif,
    create_contact_sheet,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", nargs="+", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("gif", "contact", "anchors"), default="gif")
    parser.add_argument("--fps", type=float, default=8.0)
    parser.add_argument("--scale", type=int, default=4)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument(
        "--anchors",
        type=Path,
        help="JSON list, or object with a frames list containing torso anchors",
    )
    args = parser.parse_args()

    if args.mode == "gif":
        result = create_animation_gif(args.frames, args.output, fps=args.fps, scale=args.scale)
    elif args.mode == "contact":
        result = create_contact_sheet(
            args.frames, args.output, columns=args.columns, scale=args.scale
        )
    else:
        if args.anchors is None:
            parser.error("--anchors is required for --mode anchors")
        data = json.loads(args.anchors.read_text(encoding="utf-8"))
        anchors = data.get("frames", data) if isinstance(data, dict) else data
        if not isinstance(anchors, list):
            parser.error("Anchor JSON must resolve to a list")
        result = create_anchor_overlay(
            args.frames,
            anchors,
            args.output,
            columns=args.columns,
            scale=args.scale,
        )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
