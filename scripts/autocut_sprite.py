#!/usr/bin/env python3
import argparse
import json

from sprite_builder.postprocess import autocut_sprite


def main() -> None:
    parser = argparse.ArgumentParser(description="Crop transparent margins from a sprite")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--padding", type=int, default=0)
    args = parser.parse_args()
    result = autocut_sprite(args.input, padding=args.padding)
    result.image.save(args.output)
    print(json.dumps({"bbox": result.bbox, "source_size": result.source_size}))


if __name__ == "__main__":
    main()
