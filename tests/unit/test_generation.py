from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from sprite_builder.domain.models import JobSpec
from sprite_builder.generation.ingest import ingest_candidate
from sprite_builder.generation.prompts import PromptCompiler
from sprite_builder.generation.queue import prepare_requests
from sprite_builder.generation.review import (
    latest_request_decision,
    record_request_decision,
)
from tests.unit.test_domain import valid_job_dict


class GenerationBoundaryTests(unittest.TestCase):
    def test_prepares_one_request_per_frame_and_candidate(self) -> None:
        spec = JobSpec.from_dict(valid_job_dict())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_frame.jinja2").write_text(
                "{{ character_description }} {{ direction }} {{ phase }} {{ background_color }}",
                encoding="utf-8",
            )
            requests = prepare_requests(
                spec,
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )
            self.assertEqual(len(requests), 4)
            self.assertEqual(len({item.request_id for item in requests}), 4)
            self.assertTrue((root / "jobs/hero-walk/generation/requests/index.json").is_file())

    def test_ingests_png_without_overwrite(self) -> None:
        spec = JobSpec.from_dict(valid_job_dict())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_frame.jinja2").write_text(
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

    def test_frame_zero_seed_uses_ingest_and_immutable_review(self) -> None:
        data = valid_job_dict()
        data["generation"]["seed"] = {  # type: ignore[index]
            "path": "frame0.png",
            "frame_index": 0,
        }
        spec = JobSpec.from_dict(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_frame.jinja2").write_text(
                "{{ character_description }}", encoding="utf-8"
            )
            seed = root / "frame0.png"
            Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(seed)
            requests = prepare_requests(
                spec,
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )
            seed_request = requests[0]
            self.assertEqual(seed_request.source_kind, "seed")
            self.assertEqual(seed_request.seed_source_path, "frame0.png")
            ingest_candidate(seed_request, seed, workspace=root)
            decision = record_request_decision(
                seed_request,
                "accepted",
                workspace=root,
                notes="canonical frame",
            )
            self.assertEqual(decision.status, "accepted")
            self.assertEqual(
                latest_request_decision(
                    seed_request.request_id,
                    job_id=seed_request.job_id,
                    workspace=root,
                ),
                decision,
            )
            with self.assertRaises(FileExistsError):
                record_request_decision(seed_request, "rejected", workspace=root)


if __name__ == "__main__":
    unittest.main()
