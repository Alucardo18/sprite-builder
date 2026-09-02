"""End-to-end coverage for the canonical native-sheet generation path."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from sprite_builder.domain.models import JobSpec
from sprite_builder.export import (
    export_native_godot_bundle,
    preserve_native_sheet,
    write_native_manifest,
)
from sprite_builder.generation import PromptCompiler, ingest_candidate, prepare_requests
from sprite_builder.pipeline import validate_sheet_sources


def _job() -> JobSpec:
    return JobSpec.from_dict(
        {
            "schema_version": "1.0",
            "job": {"id": "synthetic-walk"},
            "character": {"id": "synthetic", "bible": "characters/synthetic/bible.yaml"},
            "animation": {
                "name": "walk",
                "directions": ["right"],
                "frame_count": 4,
                "fps": 8,
                "loop": True,
                "phases": ["contact_left", "passing_left", "contact_right", "recovery"],
            },
            "generation": {
                "source_size": [192, 160],
                "mode": "sheet",
                "candidates_per_sheet": 1,
                "sheet": {"layout": "horizontal", "rows": 1, "columns": 4},
                "background": {
                    "mode": "transparent_required",
                    "fallback": "manual_ui",
                },
            },
            "render": {
                "cell_size": [48, 160],
                "target_body_height_px": 80,
            },
            "alignment": {
                "method": "torso_hybrid_v1",
                "canonical_canvas_anchor": [24, 120],
            },
            "export": {
                "formats": ["godot"],
                "output_dir": "exports/synthetic",
                "godot": {
                    "project_root": ".",
                    "resource_dir": "res://assets/generated/walk.png",
                },
            },
        }
    )


def _native_sheet(job: JobSpec) -> Image.Image:
    image = Image.new("RGBA", job.generation.source_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for frame_index in range(job.animation.frame_count):
        x0 = frame_index * 48
        bob = (0, 2, 1, 0)[frame_index]
        draw.rectangle((x0 + 10, 34 + bob, x0 + 36, 108 + bob), fill=(180, 90, 30, 255))
        draw.rectangle((x0 + 15, 45 + bob, x0 + 31, 89 + bob), fill=(230, 160, 45, 255))
        draw.rectangle((x0 + 12, 109 + bob, x0 + 19, 134 + bob), fill=(60, 30, 20, 255))
        draw.rectangle((x0 + 27, 109 + bob, x0 + 34, 134 + bob), fill=(60, 30, 20, 255))
    return image


def test_native_sheet_generation_ingestion_validation_and_godot_export(tmp_path: Path) -> None:
    job = _job()
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "animation_sheet.jinja2").write_text(
        "{{ animation }} {{ direction }} {{ frame_count }} "
        "{% for item in frame_plan %}{{ item.phase }} {% endfor %}",
        encoding="utf-8",
    )

    requests = prepare_requests(
        job,
        workspace=tmp_path,
        prompt_compiler=PromptCompiler(prompt_dir),
        character_context={"character_description": "Synthetic hero"},
    )
    assert len(requests) == 1
    request = requests[0]
    assert request.request_kind == "sheet"
    assert request.sheet_frame_count == 4

    source = tmp_path / "manual-clean-sheet.png"
    _native_sheet(job).save(source, format="PNG")
    ingested = ingest_candidate(request, source, workspace=tmp_path)
    assert ingested.native_size_verified is True
    assert ingested.status == "ingested"

    source_manifest = validate_sheet_sources(job, workspace=tmp_path)
    assert source_manifest["status"] == "ready_for_manual_alpha_review"
    assert source_manifest["transformations"] == {
        "crop": False,
        "resize": False,
        "resample": False,
        "pixel_split": False,
        "alpha_removal": "manual_or_provider_only",
    }
    selected = source_manifest["selected"][0]
    selected_path = tmp_path / selected["source"]
    regions = tuple((index * 48, 0, 48, 160) for index in range(4))
    native = preserve_native_sheet(
        selected_path,
        tmp_path / "exports/native/walk.png",
        regions=regions,
    )
    metadata_path, tres_path = export_native_godot_bundle(
        sheet=native,
        output_directory=tmp_path / "exports/native",
        texture_resource_path="res://assets/generated/walk.png",
        animation="walk",
        fps=job.animation.fps,
        loop=job.animation.loop,
        frame_indices=tuple(range(4)),
    )
    manifest_path = write_native_manifest(
        native,
        tmp_path / "exports/native/walk.native-export.json",
        animation="walk",
        metadata_path=metadata_path,
        tres_path=tres_path,
        texture_resource_path="res://assets/generated/walk.png",
        frame_indices=tuple(range(4)),
    )

    assert native.output_path.read_bytes() == selected_path.read_bytes()
    assert native.source_sha256 == native.output_sha256
    assert metadata_path.is_file()
    assert tres_path.is_file()
    assert manifest_path.is_file()
    assert tres_path.read_text(encoding="utf-8").count(
        '[sub_resource type="AtlasTexture"'
    ) == 4
    exported_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert exported_manifest["invariants"]["physical_crops_written"] is False
