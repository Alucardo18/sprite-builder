import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageDraw

from sprite_builder.alignment import (
    align_frames_by_anchor,
    calibrate_torso,
    detect_torso_anchor,
    load_anchor_overrides,
)
from sprite_builder.consistency import validate_sprite_consistency
from sprite_builder.postprocess import (
    autocut_sprite,
    normalize_sprite,
    quantize_palette,
    remove_background,
)


def sprite(*, shift=(0, 0), weapon=False, background=(0, 255, 0)):
    im = Image.new("RGB", (96, 80), background)
    d = ImageDraw.Draw(im)
    x, y = shift
    d.rectangle((35 + x, 20 + y, 59 + x, 57 + y), fill=(180, 90, 30))
    d.rectangle((39 + x, 25 + y, 55 + x, 48 + y), fill=(230, 160, 45))
    d.rectangle((38 + x, 58 + y, 45 + x, 70 + y), fill=(60, 30, 20))
    d.rectangle((50 + x, 58 + y, 57 + x, 70 + y), fill=(60, 30, 20))
    if weapon:
        d.rectangle((59 + x, 35 + y, 93, 37 + y), fill=(100, 70, 20))
    return im


class VisualPipelineTests(unittest.TestCase):
    def test_background_flood_fill_preserves_enclosed_chroma(self):
        im = sprite()
        ImageDraw.Draw(im).rectangle((44, 32, 47, 35), fill=(0, 255, 0))
        result = remove_background(im, chroma_rgb=(0, 255, 0), feather_px=0)
        arr = np.asarray(result.image)
        self.assertEqual(arr[0, 0, 3], 0)
        self.assertEqual(arr[33, 45, 3], 255)
        self.assertGreater(result.confidence, 0.8)

    def test_crop_and_palette_scale(self):
        transparent = remove_background(sprite(), chroma_rgb=(0, 255, 0), feather_px=0).image
        crop = autocut_sprite(transparent, padding=2)
        self.assertLess(crop.image.width, transparent.width)
        normalized = normalize_sprite(crop.image, target_body_height=26, source_body_height=52)
        quantized = quantize_palette(normalized, [(180, 90, 30), (230, 160, 45), (60, 30, 20)])
        colors = set(
            map(tuple, np.asarray(quantized)[:, :, :3][np.asarray(quantized)[:, :, 3] > 0])
        )
        self.assertTrue(colors.issubset({(180, 90, 30), (230, 160, 45), (60, 30, 20)}))

    def test_weapon_does_not_drag_torso_anchor(self):
        canonical = remove_background(sprite(), chroma_rgb=(0, 255, 0), feather_px=0).image
        frame = remove_background(
            sprite(shift=(4, 2), weapon=True), chroma_rgb=(0, 255, 0), feather_px=0
        ).image
        calibration = calibrate_torso(canonical, ((37, 24), (57, 24)), ((39, 50), (55, 50)))
        found = detect_torso_anchor(frame, calibration)
        self.assertAlmostEqual(found.anchor[0], calibration.anchor[0] + 4, delta=3)
        self.assertAlmostEqual(found.anchor[1], calibration.anchor[1] + 2, delta=3)

    def test_manual_override_and_strict_overflow(self):
        im = remove_background(sprite(), chroma_rgb=(0, 255, 0), feather_px=0).image
        cal = calibrate_torso(im, ((37, 24), (57, 24)), ((39, 50), (55, 50)))
        found = detect_torso_anchor(im, cal, override=(48, 40))
        self.assertEqual(found.source, "manual")
        aligned = align_frames_by_anchor(
            [im], [found], canvas_size=(128, 96), target_anchor=(64, 45)
        )
        self.assertEqual(aligned[0].size, (128, 96))
        with self.assertRaisesRegex(OverflowError, "CELL_OVERFLOW"):
            align_frames_by_anchor([im], [(48, 40)], canvas_size=(60, 60), target_anchor=(10, 10))

    def test_override_json_formats(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "overrides.json"
            path.write_text(json.dumps({"frames": [{"frame": 2, "override": [10, 20]}]}))
            self.assertEqual(load_anchor_overrides(path), {2: (10.0, 20.0)})

    def test_consistency_detects_recolor(self):
        canon = remove_background(sprite(), chroma_rgb=(0, 255, 0), feather_px=0).image
        bad = np.asarray(canon).copy()
        bad[bad[:, :, 3] > 0, :3] = (0, 0, 255)
        report = validate_sprite_consistency(
            [canon, Image.fromarray(bad)],
            canonical=canon,
            palette=[(180, 90, 30), (230, 160, 45), (60, 30, 20)],
        )
        self.assertEqual(report.frames[0].status, "pass")
        self.assertIn(report.frames[1].status, ("review", "reject"))


if __name__ == "__main__":
    unittest.main()
