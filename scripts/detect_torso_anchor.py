#!/usr/bin/env python3
import argparse
import json

from sprite_builder.alignment import calibrate_torso, detect_torso_anchor


def _point(value: str) -> tuple[float, float]:
    x, y = value.split(",")
    return float(x), float(y)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate and detect a torso anchor")
    parser.add_argument("canonical")
    parser.add_argument("frame")
    parser.add_argument("--shoulder-left", required=True, type=_point)
    parser.add_argument("--shoulder-right", required=True, type=_point)
    parser.add_argument("--hip-left", required=True, type=_point)
    parser.add_argument("--hip-right", required=True, type=_point)
    parser.add_argument("--override", type=_point)
    parser.add_argument("--output")
    args = parser.parse_args()
    calibration = calibrate_torso(
        args.canonical,
        (args.shoulder_left, args.shoulder_right),
        (args.hip_left, args.hip_right),
    )
    result = detect_torso_anchor(args.frame, calibration, override=args.override)
    payload = {
        "anchor": result.anchor,
        "confidence": result.confidence,
        "template_score": result.template_score,
        "flow_inlier_ratio": result.flow_inlier_ratio,
        "core_score": result.core_score,
        "source": result.source,
    }
    text = json.dumps(payload, indent=2)
    if args.output:
        from pathlib import Path

        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
