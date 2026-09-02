from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PIL import Image, ImageDraw

from sprite_builder.domain.errors import ConfigurationError
from sprite_builder.domain.models import JobSpec
from sprite_builder.generation.openai_images import (
    generate_openai_candidate,
    plan_openai_request,
)
from sprite_builder.generation.prompts import PromptCompiler
from sprite_builder.generation.queue import GenerationRequest, prepare_requests
from tests.unit.test_domain import valid_job_dict


class _FakeImages:
    def __init__(self, png: bytes, *, background: str = "transparent") -> None:
        self.png = png
        self.background = background
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def edit(self, **kwargs: Any) -> Any:
        self.calls.append(("edit", kwargs))
        return self._response()

    def generate(self, **kwargs: Any) -> Any:
        self.calls.append(("generate", kwargs))
        return self._response()

    def _response(self) -> Any:
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(self.png).decode("ascii"))],
            background=self.background,
            output_format="png",
        )


class OpenAIImageGenerationTests(unittest.TestCase):
    def test_sheet_request_uses_one_gpt_image_2_call_for_all_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_sheet.jinja2").write_text(
                "{{ animation }} {{ direction }} {{ frame_count }}", encoding="utf-8"
            )
            data = valid_job_dict()
            data["character"]["references"] = []  # type: ignore[index]
            data["generation"]["mode"] = "sheet"  # type: ignore[index]
            data["generation"]["candidates_per_sheet"] = 1  # type: ignore[index]
            data["generation"]["background"] = {  # type: ignore[index]
                "mode": "transparent_required",
                "fallback": "manual_ui",
            }
            request = prepare_requests(
                JobSpec.from_dict(data),
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )[0]
            self.assertEqual(request.request_kind, "sheet")
            source = root / "sheet.png"
            image = Image.new("RGBA", request.source_size, (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((200, 120, 823, 900), fill=(180, 90, 30, 255))
            image.save(source)
            images = _FakeImages(source.read_bytes())

            result = generate_openai_candidate(
                request,
                workspace=root,
                client=SimpleNamespace(images=images),
            )

            self.assertEqual(len(images.calls), 1)
            self.assertEqual(images.calls[0][0], "generate")
            self.assertEqual(images.calls[0][1]["model"], "gpt-image-2")
            self.assertEqual(result.generation.request_kind, "sheet")
            self.assertEqual(result.generation.native_source_size, (1024, 1024))
            self.assertTrue(result.ingest.native_size_verified)

    def test_uses_structured_transparency_and_preserves_png_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference.png"
            Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(reference)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_sheet.jinja2").write_text(
                "One isolated sprite.", encoding="utf-8"
            )
            data = valid_job_dict()
            data["character"]["references"] = [str(reference)]  # type: ignore[index]
            data["animation"]["frame_count"] = 1  # type: ignore[index]
            data["animation"]["phases"] = ["idle"]  # type: ignore[index]
            data["generation"]["source_size"] = [96, 96]  # type: ignore[index]
            data["generation"]["background"] = {  # type: ignore[index]
                "mode": "transparent_required",
                "fallback": "manual_ui",
                "max_alpha_retries": 2,
            }
            request = prepare_requests(
                JobSpec.from_dict(data),
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )[0]
            plan = plan_openai_request(request)
            self.assertEqual(plan.endpoint, "images.edit")
            self.assertEqual(plan.background, "transparent")
            self.assertEqual(plan.output_format, "png")
            self.assertEqual(plan.size, "96x96")
            source = root / "source.png"
            image = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((24, 12, 71, 84), fill=(180, 90, 30, 255))
            image.save(source)
            png = source.read_bytes()
            images = _FakeImages(png)

            result = generate_openai_candidate(
                request,
                workspace=root,
                client=SimpleNamespace(images=images),
            )

            self.assertEqual(len(images.calls), 1)
            endpoint, kwargs = images.calls[0]
            self.assertEqual(endpoint, "edit")
            self.assertEqual(kwargs["model"], "gpt-image-2")
            self.assertEqual(kwargs["background"], "transparent")
            self.assertEqual(kwargs["output_format"], "png")
            self.assertEqual(kwargs["quality"], "medium")
            self.assertEqual(kwargs["size"], "96x96")
            self.assertEqual(result.ingest.status, "ingested")
            output = root / result.generation.output_path
            self.assertEqual(output.read_bytes(), png)
            provider = json.loads(output.with_suffix(".provider.json").read_text())
            self.assertEqual(provider["response_background"], "transparent")
            self.assertEqual(provider["response_output_format"], "png")

    def test_rejects_non_generation_request(self) -> None:
        request = GenerationRequest(
            schema_version="1.0",
            request_id="manual",
            job_id="job",
            character_id="hero",
            animation="idle",
            direction="down",
            candidate_index=0,
            prompt_path="prompt.txt",
            reference_paths=(),
            output_filename="manual.png",
            source_size=(1024, 1024),
            quality="high",
            source_kind="manual_alpha",
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaisesRegex(ConfigurationError, "not an API generation request"),
        ):
            generate_openai_candidate(
                request,
                workspace=temporary,
                client=SimpleNamespace(),
            )

    def test_opaque_api_result_enters_existing_retry_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "prompts"
            template_dir.mkdir()
            (template_dir / "animation_sheet.jinja2").write_text(
                "One isolated sprite.", encoding="utf-8"
            )
            data = valid_job_dict()
            data["character"]["references"] = []  # type: ignore[index]
            data["generation"]["source_size"] = [96, 96]  # type: ignore[index]
            data["generation"]["background"] = {  # type: ignore[index]
                "mode": "transparent_required",
                "fallback": "manual_ui",
                "max_alpha_retries": 2,
            }
            request = prepare_requests(
                JobSpec.from_dict(data),
                workspace=root,
                prompt_compiler=PromptCompiler(template_dir),
                character_context={"character_description": "Hero"},
            )[0]
            source = root / "opaque.png"
            Image.new("RGB", (96, 96), (245, 245, 245)).save(source)
            images = _FakeImages(source.read_bytes(), background="opaque")

            result = generate_openai_candidate(
                request,
                workspace=root,
                client=SimpleNamespace(images=images),
            )

            self.assertEqual(images.calls[0][0], "generate")
            self.assertEqual(result.ingest.status, "alpha_retry_required")
            self.assertIsNotNone(result.ingest.retry_request_path)
            self.assertEqual(result.generation.response_background, "opaque")


if __name__ == "__main__":
    unittest.main()
