"""Offline forward test of the public deterministic pipeline."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from sprite_builder.domain.models import JobSpec
from sprite_builder.pipeline import (
    align_job,
    export_job,
    postprocess_job,
    preview_job,
    validate_job,
)


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
            },
            "generation": {
                "source_size": [192, 160],
                "background": {"color": "#00FF00"},
            },
            "render": {
                "cell_size": [128, 128],
                "target_body_height_px": 64,
                "palette_lock": True,
            },
            "alignment": {
                "method": "torso_hybrid_v1",
                "canonical_canvas_anchor": [64, 60],
                "confidence_review_threshold": 0.55,
                "allow_manual_override": True,
            },
            "export": {
                "formats": ["individual", "horizontal", "godot"],
                "output_dir": "exports/synthetic",
                "godot": {
                    "project_root": ".",
                    "resource_dir": "res://assets/generated",
                },
            },
        }
    )


def _raw_frame(index: int) -> Image.Image:
    image = Image.new("RGB", (192, 160), (0, 255, 0))
    draw = ImageDraw.Draw(image)
    bob = (0, 3, 1, 0)[index]
    # Stable torso colors and silhouette.
    draw.rectangle((68, 34 + bob, 116, 104 + bob), fill=(180, 90, 30))
    draw.rectangle((76, 48 + bob, 108, 88 + bob), fill=(230, 160, 45))
    draw.rectangle((72, 105 + bob, 84, 136 + bob), fill=(60, 30, 20))
    draw.rectangle((99, 105 + bob, 111, 136 + bob), fill=(60, 30, 20))
    # Same chroma enclosed in the torso: flood-fill must preserve it.
    draw.rectangle((89, 63 + bob, 94, 68 + bob), fill=(0, 255, 0))
    if index == 2:
        # A connected spear changes the full bounding box substantially.
        draw.rectangle((116, 67 + bob, 181, 72 + bob), fill=(100, 70, 20))
        draw.polygon(((181, 64 + bob), (191, 70 + bob), (181, 76 + bob)), fill=(100, 70, 20))
    return image


def test_offline_pipeline_chroma_weapon_and_godot_export(tmp_path: Path) -> None:
    job = _job()
    raw = tmp_path / "jobs" / job.job_id / "raw"
    raw.mkdir(parents=True)
    for index in range(4):
        _raw_frame(index).save(raw / f"walk_right_{index:03d}_candidate_00.png")

    palette_path = Path("characters/synthetic/palette.json")
    palette_file = tmp_path / palette_path
    palette_file.parent.mkdir(parents=True)
    palette_file.write_text(
        json.dumps(
            {
                "colors": [
                    "#B45A1E",
                    "#E6A02D",
                    "#3C1E14",
                    "#644614",
                    "#00FF00",
                ]
            }
        ),
        encoding="utf-8",
    )

    processed = postprocess_job(job, workspace=tmp_path, palette_path=palette_path)
    assert len(processed) == 4
    # Enclosed green survives as foreground while the outside becomes alpha 0.
    weapon_alpha_width = np.ptp(np.where(np.asarray(Image.open(processed[2]))[:, :, 3] > 0)[1]) + 1
    normal_alpha_width = np.ptp(np.where(np.asarray(Image.open(processed[1]))[:, :, 3] > 0)[1]) + 1
    assert weapon_alpha_width > normal_alpha_width * 1.7

    aligned, anchors = align_job(job, workspace=tmp_path)
    assert len(aligned) == len(anchors) == 4
    assert all(Image.open(path).size == (128, 128) for path in aligned)
    assert all(record["torso_anchor"] == [64, 60] for record in anchors)

    report = validate_job(job, workspace=tmp_path, palette_path=palette_path)
    assert report["status"] in {"pass", "review"}
    previews = preview_job(job, workspace=tmp_path)
    assert all(Path(path).is_file() for path in previews.values())

    exported = export_job(job, workspace=tmp_path)
    assert {"sheet", "metadata", "tres"} <= exported.keys()
    assert Image.open(exported["sheet"]).size == (512, 128)
    assert all(Path(path).is_file() for path in exported.values())
    assert "res://assets/generated/walk_right.png" in Path(exported["tres"]).read_text()


def test_multidirection_jobs_are_validated_and_exported_separately(
    tmp_path: Path,
) -> None:
    base = _job()
    job = replace(
        base,
        job_id="synthetic-multidirection",
        animation=replace(
            base.animation,
            directions=("left", "right"),
            frame_count=2,
        ),
        export=replace(
            base.export,
            formats=("individual", "grid", "godot"),
            output_dir=Path("exports/multidirection"),
        ),
    )
    raw = tmp_path / "jobs" / job.job_id / "raw"
    raw.mkdir(parents=True)
    for direction_index, direction in enumerate(job.animation.directions):
        for frame_index in range(job.animation.frame_count):
            _raw_frame(frame_index + direction_index).save(
                raw / f"walk_{direction}_{frame_index:03d}_candidate_00.png"
            )

    palette_path = Path("characters/synthetic/palette.json")
    palette_file = tmp_path / palette_path
    palette_file.parent.mkdir(parents=True)
    palette_file.write_text(
        json.dumps(
            {
                "colors": [
                    "#B45A1E",
                    "#E6A02D",
                    "#3C1E14",
                    "#644614",
                    "#00FF00",
                ]
            }
        ),
        encoding="utf-8",
    )

    postprocess_job(job, workspace=tmp_path, palette_path=palette_path)
    _, anchors = align_job(job, workspace=tmp_path)
    assert [item["direction"] for item in anchors] == [
        "left",
        "left",
        "right",
        "right",
    ]
    report = validate_job(job, workspace=tmp_path, palette_path=palette_path)
    assert set(report["directions"]) == {"left", "right"}
    previews = preview_job(job, workspace=tmp_path)
    assert {"left.gif", "right.gif"} <= previews.keys()
    exported = export_job(job, workspace=tmp_path)
    assert {"left.sheet", "left.tres", "right.sheet", "right.tres"} <= exported.keys()
    assert all(Path(path).is_file() for path in exported.values())
