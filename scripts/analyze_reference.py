#!/usr/bin/env python3
"""Analyze a local sprite reference without external services."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sprite_builder.character import analyze_reference


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract frame bounds, components, palette, and proportions"
    )
    parser.add_argument("reference")
    parser.add_argument("--palette-colors", type=int, default=16)
    parser.add_argument("--output")
    args = parser.parse_args()
    analysis = analyze_reference(args.reference, palette_colors=args.palette_colors)
    text = json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
