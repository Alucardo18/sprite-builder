from __future__ import annotations

import unittest

from sprite_builder.domain.errors import ConfigurationError
from sprite_builder.domain.models import JobSpec


def valid_job_dict() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "job": {"id": "hero-walk"},
        "character": {
            "id": "hero",
            "bible": "characters/hero/bible.yaml",
            "references": ["reference.png"],
        },
        "animation": {
            "name": "walk",
            "directions": ["right"],
            "frame_count": 2,
            "fps": 8,
            "phases": ["contact", "passing"],
        },
        "generation": {
            "source_size": [1024, 1024],
            "quality": "medium",
            "mode": "sheet",
            "candidates_per_sheet": 2,
            "background": {"color": "#00ff00"},
        },
        "render": {"cell_size": [128, 128], "target_body_height_px": 74},
        "alignment": {
            "method": "torso_hybrid_v1",
            "canonical_canvas_anchor": [64, 68],
        },
        "export": {"formats": ["individual"], "output_dir": "exports/hero"},
    }


class JobSpecTests(unittest.TestCase):
    def test_parses_and_round_trips(self) -> None:
        spec = JobSpec.from_dict(valid_job_dict())
        self.assertEqual(spec.animation.frame_count, 2)
        self.assertEqual(spec.generation.background_color, "#00FF00")
        self.assertEqual(JobSpec.from_dict(spec.to_dict()), spec)

    def test_new_jobs_default_to_native_sheet_generation(self) -> None:
        data = valid_job_dict()
        del data["generation"]["mode"]  # type: ignore[index]
        del data["generation"]["candidates_per_sheet"]  # type: ignore[index]
        spec = JobSpec.from_dict(data)
        self.assertEqual(spec.generation.mode, "sheet")
        self.assertEqual(spec.generation.candidates_per_sheet, 1)
        self.assertEqual(spec.generation.resolved_sheet_grid(2), (1, 2))
        self.assertEqual(JobSpec.from_dict(spec.to_dict()), spec)

    def test_rejects_removed_frame_generation_route(self) -> None:
        data = valid_job_dict()
        data["generation"]["mode"] = "frame_sequence"  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "Only generation.mode=sheet"):
            JobSpec.from_dict(data)

        data = valid_job_dict()
        data["generation"]["candidates_per_frame"] = 1  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "candidates_per_frame"):
            JobSpec.from_dict(data)

    def test_sheet_layout_rejects_uncovered_frame_count(self) -> None:
        data = valid_job_dict()
        data["generation"]["mode"] = "sheet"  # type: ignore[index]
        data["generation"]["sheet"] = {"layout": "grid", "rows": 1, "columns": 1}  # type: ignore[index]
        spec = JobSpec.from_dict(data)
        with self.assertRaisesRegex(ConfigurationError, "rows\*columns"):
            spec.generation.resolved_sheet_grid(2)

    def test_rejects_phase_count_mismatch(self) -> None:
        data = valid_job_dict()
        data["animation"]["phases"] = ["only-one"]  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "phases"):
            JobSpec.from_dict(data)

    def test_rejects_unsupported_schema(self) -> None:
        data = valid_job_dict()
        data["schema_version"] = "2.0"
        with self.assertRaisesRegex(ConfigurationError, "Unsupported"):
            JobSpec.from_dict(data)

    def test_godot_export_requires_res_path(self) -> None:
        data = valid_job_dict()
        data["export"] = {"formats": ["godot"], "output_dir": "out"}
        with self.assertRaisesRegex(ConfigurationError, "Godot"):
            JobSpec.from_dict(data)

    def test_semantic_quality_contract_is_optional_and_round_trips(self) -> None:
        spec = JobSpec.from_dict(valid_job_dict())
        self.assertFalse(spec.quality_gates.semantic_integrity.enabled)
        data = valid_job_dict()
        data["quality_gates"] = {
            "block_export_on_review": True,
            "semantic_integrity": {
                "enabled": True,
                "body_roi_x": [0.2, 0.8],
                "required_support_components": 2,
                "runtime_preview_scales": [1, 0.5],
            },
        }
        spec = JobSpec.from_dict(data)
        self.assertTrue(spec.quality_gates.semantic_integrity.enabled)
        self.assertEqual(spec.quality_gates.semantic_integrity.body_roi_x, (0.2, 0.8))
        self.assertEqual(JobSpec.from_dict(spec.to_dict()), spec)

    def test_semantic_quality_contract_rejects_invalid_roi(self) -> None:
        data = valid_job_dict()
        data["quality_gates"] = {
            "semantic_integrity": {"enabled": True, "body_roi_x": [0.8, 0.2]}
        }
        with self.assertRaisesRegex(ConfigurationError, "body_roi_x"):
            JobSpec.from_dict(data)

    def test_transparent_resampling_and_alpha_contract_round_trip(self) -> None:
        data = valid_job_dict()
        data["generation"]["background"] = {  # type: ignore[index]
            "mode": "transparent_preferred",
            "fallback": "manual_ui",
            "color": "#00FF00",
            "max_attempts": 3,
        }
        data["render"].update(  # type: ignore[union-attr]
            {
                "palette_max_delta_e00": 10,
                "resampling": {
                    "methods": [
                        "premultiplied_area",
                        "premultiplied_lanczos",
                        "pixel_majority",
                        "edge_aware",
                    ],
                    "selection": "auto",
                    "save_variants": True,
                },
            }
        )
        data["quality_gates"] = {
            "alpha_integrity": {
                "min_transparent_ratio": 0.1,
                "min_border_transparent_ratio": 0.99,
            }
        }
        spec = JobSpec.from_dict(data)
        self.assertEqual(spec.generation.max_alpha_retries, 2)
        self.assertEqual(spec.to_dict()["generation"]["background"]["max_attempts"], 3)
        self.assertEqual(spec.generation.background_mode, "transparent_preferred")
        self.assertEqual(len(spec.render.resample_methods), 4)
        self.assertEqual(spec.render.palette_max_delta_e00, 10)
        self.assertEqual(JobSpec.from_dict(spec.to_dict()), spec)

    def test_generation_attempt_aliases_must_agree(self) -> None:
        data = valid_job_dict()
        data["generation"]["background"] = {  # type: ignore[index]
            "mode": "transparent_required",
            "fallback": "manual_ui",
            "max_attempts": 3,
            "max_alpha_retries": 1,
        }
        with self.assertRaisesRegex(ConfigurationError, "conflicts"):
            JobSpec.from_dict(data)


if __name__ == "__main__":
    unittest.main()
