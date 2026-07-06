#!/usr/bin/env python3
import argparse
import json

from sprite_builder.postprocess import remove_background


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove border-connected flat/chroma background")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--chroma", help="RGB hex, e.g. 00ff00")
    parser.add_argument("--tolerance", type=float, default=24)
    args = parser.parse_args()
    chroma = tuple(bytes.fromhex(args.chroma.lstrip("#"))) if args.chroma else None
    result = remove_background(args.input, chroma_rgb=chroma, lab_tolerance=args.tolerance)
    result.image.save(args.output)
    print(json.dumps({"confidence": result.confidence, "background_rgb": result.background_rgb}))


if __name__ == "__main__":
    main()
