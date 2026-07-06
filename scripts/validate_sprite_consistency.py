#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from sprite_builder.consistency import validate_sprite_consistency


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure visual drift in aligned sprite frames")
    parser.add_argument("canonical")
    parser.add_argument("palette_json")
    parser.add_argument("frames", nargs="+")
    parser.add_argument("--output")
    args = parser.parse_args()
    palette_data = json.loads(Path(args.palette_json).read_text(encoding="utf-8"))
    palette = palette_data.get("colors", palette_data)
    palette = [
        tuple(bytes.fromhex(c.lstrip("#"))) if isinstance(c, str) else tuple(c) for c in palette
    ]
    report = validate_sprite_consistency(args.frames, canonical=args.canonical, palette=palette)
    text = json.dumps(report.to_dict(), indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    raise SystemExit(0 if report.status == "pass" else 3 if report.status == "review" else 4)


if __name__ == "__main__":
    main()
