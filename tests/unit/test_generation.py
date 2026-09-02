from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

from PIL import Image, ImageDraw

from sprite_builder.domain.errors import ConfigurationError
from sprite_builder.domain.models import JobSpec
from sprite_builder.generation.ingest import ingest_candidate
from sprite_builder.generation.prompts import PromptCompiler, build_character_context
from sprite_builder.generation.queue import GenerationRequest, prepare_requests
from sprite_builder.pipeline import validate_sheet_sources
from tests.unit.test_domain import valid_job_dict


class GenerationBoundaryTests(unittest.TestCase):
    @staticmethod
    def _load_request(path: Path) -> GenerationRequest:
        value = json.loads(path.read_text(encoding="utf-8"))
        allowed = {field.name for field in fields(GenerationRequest)}
        value = {key: item for key, item in value.items() if key in allowed}
        value["reference_paths"] = tuple(value.get("reference_paths", ()))
        value["source_size"] = tuple(value.get("source_size", (1024, 1024)))
        return GenerationRequest(**value)

    def test_prepares_one_request_per_sheet_candidate(self) -> None:
        spec = JobSpec.from_dict(valid_job_dict())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_sheet.jinja2").write_text(
                "{{ character_description }} {{ animation }} {{ direction }} "
                "{{ frame_count }} {{ background_color }}",
                encoding="utf-8",
            )
            requests = prepare_requests(
                spec,
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )
            self.assertEqual(len(requests), 2)
            self.assertTrue(all(item.request_kind == "sheet" for item in requests))
            self.assertEqual(len({item.request_id for item in requests}), 2)
            self.assertTrue((root / "jobs/hero-walk/generation/requests/index.json").is_file())
            self.assertTrue((root / "jobs/hero-walk/raw").is_dir())

    def test_sheet_mode_prepares_one_native_sheet_request_with_complete_prompt(self) -> None:
        data = valid_job_dict()
        data["generation"]["mode"] = "sheet"  # type: ignore[index]
        data["generation"]["candidates_per_sheet"] = 1  # type: ignore[index]
        data["generation"]["sheet"] = {  # type: ignore[index]
            "layout": "horizontal",
            "rows": 1,
            "columns": 2,
            "gutter_px": 0,
        }
        spec = JobSpec.from_dict(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_sheet.jinja2").write_text(
                "{{ animation }} {{ direction }} {{ frame_count }} "
                "{{ sheet_layout }} {% for item in frame_plan %}{{ item.phase }} {% endfor %}",
                encoding="utf-8",
            )
            requests = prepare_requests(
                spec,
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )
            self.assertEqual(len(requests), 1)
            request = requests[0]
            self.assertEqual(request.request_kind, "sheet")
            self.assertEqual(request.sheet_frame_count, 2)
            self.assertEqual(request.sheet_rows, 1)
            self.assertEqual(request.sheet_columns, 2)
            self.assertIn("contact passing", (root / request.prompt_path).read_text())
            self.assertIn("_sheet_candidate_00_", request.output_filename)

    def test_sheet_source_validation_is_metadata_only_and_preserves_native_size(self) -> None:
        data = valid_job_dict()
        data["generation"]["mode"] = "sheet"  # type: ignore[index]
        data["generation"]["candidates_per_sheet"] = 1  # type: ignore[index]
        spec = JobSpec.from_dict(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_sheet.jinja2").write_text(
                "{{ animation }} {{ direction }}", encoding="utf-8"
            )
            request = prepare_requests(
                spec,
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )[0]
            source = root / "native-sheet.png"
            Image.new("RGBA", spec.generation.source_size, (0, 0, 0, 0)).save(source)
            ingest_candidate(request, source, workspace=root)
            manifest = validate_sheet_sources(spec, workspace=root)
            self.assertEqual(manifest["status"], "ready_for_manual_alpha_review")
            self.assertEqual(manifest["transformations"]["crop"], False)
            self.assertEqual(manifest["selected"][0]["size"], [1024, 1024])

    def test_sheet_ingestion_rejects_size_mismatch_without_resizing(self) -> None:
        data = valid_job_dict()
        data["generation"]["mode"] = "sheet"  # type: ignore[index]
        spec = JobSpec.from_dict(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_sheet.jinja2").write_text(
                "{{ animation }} {{ direction }}", encoding="utf-8"
            )
            request = prepare_requests(
                spec,
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )[0]
            source = root / "wrong-size.png"
            Image.new("RGBA", (512, 512), (0, 0, 0, 0)).save(source)
            with self.assertRaisesRegex(ConfigurationError, "SHEET_NATIVE_SIZE_MISMATCH"):
                ingest_candidate(request, source, workspace=root)

    def test_ingests_png_without_overwrite(self) -> None:
        data = valid_job_dict()
        data["generation"]["source_size"] = [256, 256]  # type: ignore[index]
        spec = JobSpec.from_dict(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_sheet.jinja2").write_text(
                "{{ character_description }}", encoding="utf-8"
            )
            request = prepare_requests(
                spec,
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )[0]
            generated = root / "generated.png"
            Image.new("RGB", (256, 256), "#00FF00").save(generated)
            record = ingest_candidate(request, generated, workspace=root)
            self.assertEqual(record.width, 256)
            self.assertTrue((root / record.workspace_path).is_file())
            self.assertTrue((root / record.workspace_path).with_suffix(".ingest.json").is_file())

    def test_transparency_failure_prepares_two_retries_then_manual_ui_session(self) -> None:
        data = valid_job_dict()
        data["animation"]["frame_count"] = 1  # type: ignore[index]
        data["animation"]["phases"] = ["idle"]  # type: ignore[index]
        data["generation"]["source_size"] = [128, 128]  # type: ignore[index]
        data["generation"]["background"] = {  # type: ignore[index]
            "mode": "transparent_preferred",
            "fallback": "manual_ui",
            "color": "#00FF00",
            "max_attempts": 3,
        }
        spec = JobSpec.from_dict(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_sheet.jinja2").write_text(
                "{{ character_description }} {{ background_instruction }}", encoding="utf-8"
            )
            request = prepare_requests(
                spec,
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )[0]
            self.assertEqual(request.attempt_number, 1)
            self.assertEqual(request.max_attempts, 3)
            opaque = root / "opaque.png"
            Image.new("RGB", (128, 128), "#00FF00").save(opaque)

            first = ingest_candidate(request, opaque, workspace=root)
            self.assertEqual(first.status, "alpha_retry_required")
            self.assertEqual(ingest_candidate(request, opaque, workspace=root), first)
            retry_one = self._load_request(root / str(first.retry_request_path))
            self.assertEqual(retry_one.alpha_retry_index, 1)
            self.assertEqual(retry_one.attempt_number, 2)
            self.assertEqual(retry_one.max_attempts, 3)
            retry_prompt = (root / retry_one.prompt_path).read_text(encoding="utf-8")
            self.assertTrue(retry_prompt.startswith("ALPHA OUTPUT CONTRACT"))
            self.assertIn("Attempt 2 of 3", retry_prompt)
            self.assertNotIn("structured provider parameters", retry_prompt)
            first_index = json.loads(
                (root / "jobs/hero-walk/generation/requests/index.json").read_text()
            )
            parent_position = first_index["request_ids"].index(request.request_id)
            self.assertEqual(
                first_index["request_ids"][parent_position + 1], retry_one.request_id
            )
            prepare_requests(
                spec,
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )
            index = json.loads(
                (root / "jobs/hero-walk/generation/requests/index.json").read_text()
            )
            self.assertIn(retry_one.request_id, index["request_ids"])

            second = ingest_candidate(retry_one, opaque, workspace=root)
            self.assertEqual(second.status, "alpha_retry_required")
            retry_two = self._load_request(root / str(second.retry_request_path))
            self.assertEqual(retry_two.alpha_retry_index, 2)
            self.assertEqual(retry_two.attempt_number, 3)

            third = ingest_candidate(retry_two, opaque, workspace=root)
            self.assertEqual(third.status, "manual_review")
            self.assertIsNotNone(third.manual_session_id)
            self.assertTrue((root / "sheet_sessions" / str(third.manual_session_id)).is_dir())
            manual = self._load_request(root / str(third.manual_request_path))
            self.assertEqual(manual.status, "manual_review")
            self.assertEqual(manual.source_kind, "manual_alpha")
            self.assertEqual(manual.manual_session_id, third.manual_session_id)

    def test_valid_native_alpha_ingests_without_retry(self) -> None:
        data = valid_job_dict()
        data["animation"]["frame_count"] = 1  # type: ignore[index]
        data["animation"]["phases"] = ["idle"]  # type: ignore[index]
        data["generation"]["source_size"] = [128, 128]  # type: ignore[index]
        data["generation"]["background"] = {  # type: ignore[index]
            "mode": "transparent_required",
            "fallback": "manual_ui",
            "color": "#00FF00",
            "max_alpha_retries": 2,
        }
        spec = JobSpec.from_dict(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_sheet.jinja2").write_text(
                "{{ character_description }}", encoding="utf-8"
            )
            request = prepare_requests(
                spec,
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )[0]
            transparent = root / "transparent.png"
            image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((40, 24, 87, 112), fill=(180, 90, 30, 255))
            image.save(transparent)
            record = ingest_candidate(request, transparent, workspace=root)
            self.assertEqual(record.status, "ingested")
            self.assertIsNone(record.retry_request_path)

    def test_transparent_prompt_does_not_prime_checkerboard_visual(self) -> None:
        data = valid_job_dict()
        data["generation"]["background"] = {  # type: ignore[index]
            "mode": "transparent_required",
            "fallback": "manual_ui",
        }
        spec = JobSpec.from_dict(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bible = root / "characters/hero/bible.yaml"
            bible.parent.mkdir(parents=True)
            bible.write_text(
                "identity:\n"
                "  description: Hero\n"
                "  forbidden_changes:\n"
                "    - text, checkerboard, fake transparency, watermark\n"
                "visual_rules: {}\n",
                encoding="utf-8",
            )
            context = build_character_context(spec, workspace=root)
            combined = " ".join(str(value) for value in context.values()).lower()
            self.assertNotIn("checkerboard", combined)
            self.assertNotIn("fake transparency", combined)

    def test_non_idle_requires_an_approved_idle_scale_profile(self) -> None:
        spec = JobSpec.from_dict(valid_job_dict())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bible = root / "characters/hero/bible.yaml"
            bible.parent.mkdir(parents=True)
            bible.write_text(
                "identity:\n"
                "  description: Hero\n"
                "visual_rules: {}\n"
                "scale_profile:\n"
                "  reference_animation: idle\n"
                "  status: pending_idle_approval\n"
                "  target_body_height_px: null\n"
                "  exclude_from_measurement: [weapons, staffs, vfx]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigurationError, "IDLE_SCALE_PROFILE_REQUIRED"):
                build_character_context(spec, workspace=root)

    def test_idle_can_establish_a_pending_scale_profile(self) -> None:
        data = valid_job_dict()
        data["animation"]["name"] = "idle"  # type: ignore[index]
        spec = JobSpec.from_dict(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bible = root / "characters/hero/bible.yaml"
            bible.parent.mkdir(parents=True)
            bible.write_text(
                "identity:\n"
                "  description: Hero\n"
                "visual_rules: {}\n"
                "scale_profile:\n"
                "  reference_animation: idle\n"
                "  status: pending_idle_approval\n"
                "  target_body_height_px: null\n"
                "  exclude_from_measurement: [weapons, staffs, vfx]\n",
                encoding="utf-8",
            )
            context = build_character_context(spec, workspace=root)
            self.assertIn("authoritative character-scale reference", context["scale_contract"])

    def test_non_idle_must_match_the_approved_idle_target(self) -> None:
        data = valid_job_dict()
        spec = JobSpec.from_dict(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bible = root / "characters/hero/bible.yaml"
            bible.parent.mkdir(parents=True)
            bible.write_text(
                "identity:\n"
                "  description: Hero\n"
                "visual_rules: {}\n"
                "scale_profile:\n"
                "  reference_animation: idle\n"
                "  status: approved\n"
                "  target_body_height_px: 70\n"
                "  tolerance_px: 1\n"
                "  exclude_from_measurement: [weapons, staffs, vfx]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigurationError, "IDLE_SCALE_PROFILE_MISMATCH"):
                build_character_context(spec, workspace=root)
            data["render"]["target_body_height_px"] = 70  # type: ignore[index]
            matching = JobSpec.from_dict(data)
            context = build_character_context(matching, workspace=root)
            self.assertIn("Idle is the authoritative scale reference", context["scale_contract"])
            self.assertIn("70px", context["scale_contract"])


if __name__ == "__main__":
    unittest.main()
