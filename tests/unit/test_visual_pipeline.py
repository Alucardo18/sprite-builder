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
from sprite_builder.consistency import (
    render_masked_edit_overlay,
    validate_semantic_integrity,
    validate_sprite_consistency,
    verify_masked_edit,
)
from sprite_builder.domain.models import SemanticIntegritySpec
from sprite_builder.postprocess import (
    PaletteRole,
    autocut_sprite,
    inspect_native_alpha,
    normalize_sprite,
    quantize_palette,
    quantize_palette_with_report,
    remove_background,
    resize_sprite_variants,
    sanitize_transparent_rgb,
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
    def test_native_alpha_gate_rejects_opaque_background_and_sanitizes_hidden_rgb(self):
        opaque = Image.new("RGB", (16, 16), (0, 255, 0))
        self.assertEqual(inspect_native_alpha(opaque).status, "missing")

        transparent = Image.new("RGBA", (16, 16), (0, 255, 0, 0))
        ImageDraw.Draw(transparent).rectangle((5, 4, 10, 12), fill=(180, 90, 30, 255))
        dirty = inspect_native_alpha(transparent)
        self.assertEqual(dirty.status, "review")
        self.assertIn("hidden_rgb_under_transparency", dirty.reasons)
        clean = sanitize_transparent_rgb(transparent)
        self.assertEqual(inspect_native_alpha(clean).status, "pass")
        self.assertEqual(np.asarray(clean)[0, 0].tolist(), [0, 0, 0, 0])

    def test_premultiplied_reduction_does_not_mix_hidden_green_into_red_edge(self):
        image = Image.new("RGBA", (4, 2), (0, 255, 0, 0))
        image.putpixel((1, 0), (255, 0, 0, 255))
        image.putpixel((1, 1), (255, 0, 0, 255))
        variants = {
            variant.method: variant
            for variant in resize_sprite_variants(
                image, (2, 1), methods=("legacy", "premultiplied_area")
            )
        }
        legacy = np.asarray(variants["legacy"].image)
        premultiplied = np.asarray(variants["premultiplied_area"].image)
        self.assertGreater(int(legacy[0, 0, 1]), 0)
        self.assertEqual(int(premultiplied[0, 0, 1]), 0)
        self.assertGreater(int(premultiplied[0, 0, 0]), 240)

    def test_all_quality_resamplers_return_scored_equal_size_candidates(self):
        image = remove_background(
            sprite(), chroma_rgb=(0, 255, 0), feather_px=0, preserve_outline=True
        ).image
        methods = (
            "premultiplied_area",
            "premultiplied_lanczos",
            "pixel_majority",
            "edge_aware",
        )
        variants = resize_sprite_variants(image, (24, 20), methods=methods)
        self.assertEqual(tuple(item.method for item in variants), methods)
        self.assertTrue(all(item.image.size == (24, 20) for item in variants))
        self.assertTrue(all(0 <= item.score <= 1 for item in variants))

    def test_role_palette_and_delta_limit_preserve_unmatched_accents(self):
        image = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
        image.putpixel((0, 0), (205, 125, 85, 255))
        image.putpixel((1, 0), (110, 125, 145, 255))
        image.putpixel((2, 0), (255, 0, 255, 255))
        roles = (
            PaletteRole("skin", ((200, 120, 80),), ((210, 130, 90),)),
            PaletteRole("metal", ((100, 120, 140),), ((110, 130, 150),)),
        )
        result, report = quantize_palette_with_report(
            image,
            [(200, 120, 80), (100, 120, 140)],
            roles=roles,
            max_delta_e00=8,
        )
        pixels = np.asarray(result)[0, :, :3]
        self.assertEqual(pixels[0].tolist(), [200, 120, 80])
        self.assertEqual(pixels[1].tolist(), [100, 120, 140])
        self.assertEqual(pixels[2].tolist(), [255, 0, 255])
        self.assertEqual(report.preserved_pixels, 1)
        self.assertEqual(report.role_pixels, {"skin": 1, "metal": 1})

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

    def test_semantic_gate_distinguishes_gutter_from_complete_feet(self):
        proper = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(proper)
        draw.rectangle((11, 6, 20, 21), fill=(180, 90, 30, 255))
        draw.rectangle((11, 20, 14, 26), fill=(180, 90, 30, 255))
        draw.rectangle((17, 20, 20, 26), fill=(180, 90, 30, 255))
        draw.rectangle((10, 26, 13, 27), fill=(180, 90, 30, 255))
        draw.rectangle((18, 26, 21, 27), fill=(180, 90, 30, 255))
        # Two separated toe pixels make the terminal row narrower than the support band.
        draw.point((10, 28), fill=(180, 90, 30, 255))
        draw.point((21, 28), fill=(180, 90, 30, 255))

        flat = proper.copy()
        flat_draw = ImageDraw.Draw(flat)
        flat_draw.rectangle((10, 28, 21, 28), fill=(180, 90, 30, 255))
        config = SemanticIntegritySpec(
            enabled=True,
            body_roi_x=(0.2, 0.8),
            min_bottom_gutter_px=2,
            support_band_height_px=4,
            required_support_components=2,
            max_terminal_taper_ratio=0.75,
        )
        proper_report = validate_semantic_integrity([proper], config)
        flat_report = validate_semantic_integrity([flat], config)
        self.assertEqual(proper_report.status, "pass")
        self.assertEqual(proper_report.frames[0].bottom_gutter_px, 3)
        self.assertEqual(flat_report.status, "review")
        self.assertIn("flat_terminal_silhouette", flat_report.frames[0].reasons)
        self.assertGreater(flat_report.frames[0].bottom_gutter_px, 0)

    def test_semantic_gate_rejects_clipping_and_reviews_ground_jitter(self):
        def grounded(support_y: int) -> Image.Image:
            image = Image.new("RGBA", (24, 32), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((8, 6, 15, support_y - 2), fill=(180, 90, 30, 255))
            draw.point((8, support_y), fill=(180, 90, 30, 255))
            draw.point((15, support_y), fill=(180, 90, 30, 255))
            return image

        config = SemanticIntegritySpec(
            enabled=True,
            body_roi_x=(0.2, 0.8),
            min_bottom_gutter_px=1,
            support_band_height_px=4,
            required_support_components=2,
            max_support_y_jitter_px=0.5,
            max_terminal_taper_ratio=1.0,
        )
        jitter = validate_semantic_integrity([grounded(26), grounded(28)], config)
        self.assertEqual(jitter.status, "review")
        self.assertTrue(
            all("ground_support_jitter" in frame.reasons for frame in jitter.frames)
        )
        clipped = validate_semantic_integrity([grounded(31)], config)
        self.assertEqual(clipped.status, "reject")
        self.assertIn("bottom_gutter_below_minimum", clipped.frames[0].reasons)

    def test_masked_edit_is_byte_exact_outside_allowed_pixels(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
            after = before.copy()
            after.putpixel((3, 3), (90, 80, 70, 255))
            mask = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
            mask.putpixel((3, 3), (255, 255, 255, 255))
            paths = [root / name for name in ("before.png", "after.png", "mask.png")]
            for image, path in zip((before, after, mask), paths, strict=True):
                image.save(path)
            self.assertEqual(verify_masked_edit(*paths).status, "pass")
            after.putpixel((6, 6), (1, 2, 3, 255))
            after.save(paths[1])
            failed = verify_masked_edit(*paths)
            self.assertEqual(failed.status, "reject")
            self.assertEqual(failed.changed_outside_mask, 1)
            overlay = render_masked_edit_overlay(
                *paths, root / "overlay.png", scale=4
            )
            with Image.open(overlay) as rendered:
                self.assertEqual(rendered.size, (32, 32))
                self.assertEqual(rendered.getpixel((6 * 4, 6 * 4)), (255, 35, 70, 255))

if __name__ == "__main__":
    unittest.main()
