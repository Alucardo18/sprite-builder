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
            "candidates_per_frame": 2,
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


if __name__ == "__main__":
    unittest.main()
