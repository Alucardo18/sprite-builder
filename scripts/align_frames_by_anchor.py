#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from sprite_builder.alignment import align_frames_by_anchor


def _pair(value: str) -> tuple[float, float]:
    a, b = value.split(",")
    return float(a), float(b)


def main() -> None:
    parser = argparse.ArgumentParser(description="Align frames to a constant torso anchor")
    parser.add_argument("anchors_json")
    parser.add_argument("output_dir")
    parser.add_argument("frames", nargs="+")
    parser.add_argument("--canvas", required=True, type=_pair)
    parser.add_argument("--target", required=True, type=_pair)
    args = parser.parse_args()
    raw = json.loads(Path(args.anchors_json).read_text(encoding="utf-8"))
    records = raw.get("frames", raw)
    anchors = [
        tuple(item.get("override") or item.get("anchor")) if isinstance(item, dict) else tuple(item)
        for item in records
    ]
    outputs = align_frames_by_anchor(
        args.frames, anchors, canvas_size=tuple(map(int, args.canvas)), target_anchor=args.target
    )
    target = Path(args.output_dir)
    target.mkdir(parents=True, exist_ok=True)
    for index, image in enumerate(outputs):
        image.save(target / f"frame_{index:03d}.png")


if __name__ == "__main__":
    main()
