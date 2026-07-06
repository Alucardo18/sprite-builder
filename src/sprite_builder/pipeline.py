"""End-to-end deterministic stages used after Codex has generated raw images."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import median
from typing import Any, Literal

import numpy as np
from PIL import Image

from sprite_builder.alignment import (
    align_frames_by_anchor,
    calibrate_torso_automatically,
    detect_torso_anchor,
    load_anchor_overrides,
)
from sprite_builder.consistency import validate_sprite_consistency
from sprite_builder.domain.models import JobSpec
from sprite_builder.export import build_spritesheet, export_godot_bundle
from sprite_builder.orchestration import atomic_write_json
from sprite_builder.postprocess import autocut_sprite, normalize_sprite, remove_background
from sprite_builder.preview import (
    create_anchor_overlay,
    create_animation_gif,
    create_contact_sheet,
)


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    return atomic_write_json(path, value, sort_keys=False)


def _load_palette(path: Path) -> list[tuple[int, int, int]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    colors = value.get("colors", value) if isinstance(value, dict) else value
    result: list[tuple[int, int, int]] = []
    for item in colors:
        raw = item.get("hex", item.get("color")) if isinstance(item, dict) else item
        if isinstance(raw, str):
            raw = raw.lstrip("#")
            result.append(
                (
                    int(raw[0:2], 16),
                    int(raw[2:4], 16),
                    int(raw[4:6], 16),
                )
            )
        elif isinstance(raw, Sequence) and len(raw) >= 3:
            result.append((int(raw[0]), int(raw[1]), int(raw[2])))
    if not result:
        raise ValueError(f"No usable colors in {path}")
    return result


def _raw_candidates(root: Path, job: JobSpec) -> list[Path]:
    raw = root / "jobs" / job.job_id / "raw"
    selected: list[Path] = []
    for direction in job.animation.directions:
        for frame_index in range(job.animation.frame_count):
            matches = sorted(
                raw.glob(f"{job.animation.name}_{direction}_{frame_index:03d}_candidate_*.png")
            )
            if not matches:
                raise FileNotFoundError(
                    f"Missing generated frame {direction}/{frame_index}; "
                    "run the sprite-builder Codex skill and ingest its request first"
                )
            reviewed: list[tuple[Path, str]] = []
            for match in matches:
                request_id = match.stem.rsplit("_", 1)[-1]
                decision = (
                    root
                    / "jobs"
                    / job.job_id
                    / "generation"
                    / "decisions"
                    / f"{request_id}.latest.json"
                )
                if decision.is_file():
                    status = str(
                        json.loads(decision.read_text(encoding="utf-8")).get("status")
                    )
                    reviewed.append((match, status))
            if reviewed:
                accepted = [path for path, status in reviewed if status == "accepted"]
                if not accepted:
                    raise ValueError(
                        f"No accepted candidate for {direction}/{frame_index}; "
                        "review or generate a new attempt"
                    )
                selected.append(accepted[0])
            else:
                selected.append(matches[0])
    return selected


def _alpha_height(image: Image.Image) -> int:
    alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
    rows = np.where(alpha > 8)[0]
    if not len(rows):
        raise ValueError("Generated candidate contains no foreground")
    return int(rows.max() - rows.min() + 1)


def postprocess_job(
    job: JobSpec,
    *,
    workspace: str | Path,
    palette_path: str | Path,
) -> list[Path]:
    """Remove chroma, crop, scale once, and lock the character palette."""

    root = Path(workspace).resolve()
    sources = _raw_candidates(root, job)
    removed: list[Image.Image] = []
    records: list[dict[str, Any]] = []
    for source in sources:
        # The built-in generator approximates the requested chroma and can
        # introduce a slight gradient. Use the dominant border colour of each
        # candidate instead of the literal configured hex value.
        result = remove_background(source)
        cut = autocut_sprite(result.image, padding=max(2, result.image.height // 100))
        removed.append(cut.image)
        records.append(
            {
                "source": str(source.relative_to(root)),
                "background_rgb": list(result.background_rgb),
                "background_confidence": result.confidence,
                "source_bbox": list(cut.bbox),
            }
        )

    canonical_source_height = max(1, round(median(_alpha_height(image) for image in removed)))
    palette = _load_palette(root / palette_path)
    destination = root / "jobs" / job.job_id / "processed"
    destination.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index, image in enumerate(removed):
        normalized = normalize_sprite(
            image,
            target_body_height=job.render.target_body_height_px,
            source_body_height=canonical_source_height,
            palette=palette if job.render.palette_lock else None,
        )
        output = destination / f"frame_{index:03d}.png"
        normalized.save(output, format="PNG")
        records[index]["output"] = str(output.relative_to(root))
        records[index]["logical_size"] = list(normalized.size)
        outputs.append(output)
    _write_json(
        root / "jobs" / job.job_id / "manifests" / "postprocess.json",
        {
            "schema_version": "1.0",
            "job_id": job.job_id,
            "canonical_source_body_height": canonical_source_height,
            "target_body_height": job.render.target_body_height_px,
            "frames": records,
        },
    )
    return outputs


def _provisional_canvas(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    if image.width > size[0] or image.height > size[1]:
        raise OverflowError(f"CELL_OVERFLOW image={image.size} canvas={size}")
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def align_job(
    job: JobSpec,
    *,
    workspace: str | Path,
    overrides_path: str | Path | None = None,
) -> tuple[list[Path], list[dict[str, Any]]]:
    """Estimate torso anchors, apply overrides, and align every fixed-size frame."""

    root = Path(workspace).resolve()
    processed = sorted((root / "jobs" / job.job_id / "processed").glob("frame_*.png"))
    expected = job.animation.frame_count * len(job.animation.directions)
    if len(processed) != expected:
        raise FileNotFoundError(f"Expected {expected} processed frames, found {len(processed)}")
    canvases = [
        _provisional_canvas(Image.open(path).convert("RGBA"), job.render.cell_size)
        for path in processed
    ]
    overrides = (
        load_anchor_overrides(root / overrides_path)
        if overrides_path and (root / overrides_path).exists()
        else {}
    )
    detections = []
    for direction_index, _direction in enumerate(job.animation.directions):
        start = direction_index * job.animation.frame_count
        direction_frames = canvases[start : start + job.animation.frame_count]
        calibration, _ = calibrate_torso_automatically(direction_frames[0])
        previous_frame = None
        previous_anchor = None
        for local_index, frame in enumerate(direction_frames):
            index = start + local_index
            detection = detect_torso_anchor(
                frame,
                calibration,
                previous_frame=previous_frame,
                previous_anchor=previous_anchor,
                override=overrides.get(index),
            )
            detections.append(detection)
            previous_frame = frame
            previous_anchor = detection.anchor
    aligned_images = align_frames_by_anchor(
        canvases,
        detections,
        canvas_size=job.render.cell_size,
        target_anchor=job.alignment.canonical_canvas_anchor,
    )
    destination = root / "jobs" / job.job_id / "aligned"
    destination.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    frame_records: list[dict[str, Any]] = []
    for index, (image, detection) in enumerate(zip(aligned_images, detections, strict=True)):
        output = destination / f"frame_{index:03d}.png"
        image.save(output, format="PNG")
        output_paths.append(output)
        alpha = np.asarray(image)[:, :, 3]
        ys, xs = np.where(alpha > 8)
        foreground_bbox = [
            int(xs.min()),
            int(ys.min()),
            int(xs.max()) + 1,
            int(ys.max()) + 1,
        ]
        bottom = int(ys.max())
        bottom_xs = xs[ys >= bottom - 1]
        foot_anchor = [
            float(np.median(bottom_xs)),
            float(bottom),
        ]
        frame_records.append(
            {
                "frame": index,
                "direction": job.animation.directions[index // job.animation.frame_count],
                "direction_frame": index % job.animation.frame_count,
                "auto": list(detection.anchor),
                "torso_anchor": list(job.alignment.canonical_canvas_anchor),
                "canvas_pivot": list(job.alignment.canonical_canvas_anchor),
                "godot_offset": [
                    job.render.cell_size[0] / 2
                    - job.alignment.canonical_canvas_anchor[0],
                    job.render.cell_size[1] / 2
                    - job.alignment.canonical_canvas_anchor[1],
                ],
                "foot_anchor": foot_anchor,
                "foreground_bbox": foreground_bbox,
                "weapon_excluded_from_anchor": True,
                "confidence": detection.confidence,
                "template_score": detection.template_score,
                "flow_inlier_ratio": detection.flow_inlier_ratio,
                "source": detection.source,
                "manual_review": detection.confidence < job.alignment.confidence_review_threshold,
            }
        )
    _write_json(
        root / "jobs" / job.job_id / "manifests" / "anchors.json",
        {"schema_version": "1.0", "job_id": job.job_id, "frames": frame_records},
    )
    return output_paths, frame_records


def validate_job(
    job: JobSpec,
    *,
    workspace: str | Path,
    palette_path: str | Path,
) -> dict[str, Any]:
    root = Path(workspace).resolve()
    frames = sorted((root / "jobs" / job.job_id / "aligned").glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError("No aligned frames to validate")
    palette = _load_palette(root / palette_path)
    directions: dict[str, Any] = {}
    statuses: list[str] = []
    drifts: list[float] = []
    for direction_index, direction in enumerate(job.animation.directions):
        start = direction_index * job.animation.frame_count
        subset = frames[start : start + job.animation.frame_count]
        report = validate_sprite_consistency(
            subset,
            canonical=subset[0],
            palette=palette,
        )
        directions[direction] = report.to_dict()
        statuses.append(report.status)
        drifts.append(report.mean_drift)
    status = "reject" if "reject" in statuses else "review" if "review" in statuses else "pass"
    value = {
        "schema_version": "1.0",
        "job_id": job.job_id,
        "status": status,
        "mean_drift": float(np.mean(drifts)),
        "directions": directions,
    }
    _write_json(root / "jobs" / job.job_id / "reports" / "consistency.json", value)
    return value


def preview_job(job: JobSpec, *, workspace: str | Path) -> dict[str, str]:
    root = Path(workspace).resolve()
    frames = sorted((root / "jobs" / job.job_id / "aligned").glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError("No aligned frames to preview")
    destination = root / "jobs" / job.job_id / "reports"
    anchors_path = root / "jobs" / job.job_id / "manifests" / "anchors.json"
    anchors = json.loads(anchors_path.read_text(encoding="utf-8"))["frames"]
    outputs: dict[str, str] = {}
    for direction_index, direction in enumerate(job.animation.directions):
        start = direction_index * job.animation.frame_count
        stop = start + job.animation.frame_count
        subset = frames[start:stop]
        subset_anchors = anchors[start:stop]
        prefix = "" if len(job.animation.directions) == 1 else f"{direction}."
        outputs[f"{prefix}gif"] = str(
            create_animation_gif(
                subset,
                destination / f"{job.animation.name}_{direction}.gif",
                fps=job.animation.fps,
            )
        )
        outputs[f"{prefix}contact_sheet"] = str(
            create_contact_sheet(
                subset,
                destination / f"{job.animation.name}_{direction}_contact.png",
            )
        )
        outputs[f"{prefix}anchors"] = str(
            create_anchor_overlay(
                subset,
                subset_anchors,
                destination / f"{job.animation.name}_{direction}_anchors.png",
            )
        )
    return outputs


def export_job(job: JobSpec, *, workspace: str | Path) -> dict[str, str]:
    root = Path(workspace).resolve()
    frames = sorted((root / "jobs" / job.job_id / "aligned").glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError("No aligned frames to export")
    base_destination = root / job.export.output_dir
    base_destination.mkdir(parents=True, exist_ok=True)
    anchors_file = root / "jobs" / job.job_id / "manifests" / "anchors.json"
    anchors = json.loads(anchors_file.read_text(encoding="utf-8"))["frames"]
    outputs: dict[str, str] = {}
    layout: Literal["horizontal", "grid"] = "grid" if "grid" in job.export.formats else "horizontal"
    for direction_index, direction in enumerate(job.animation.directions):
        start = direction_index * job.animation.frame_count
        stop = start + job.animation.frame_count
        subset = frames[start:stop]
        subset_anchors = anchors[start:stop]
        destination = (
            base_destination if len(job.animation.directions) == 1 else base_destination / direction
        )
        destination.mkdir(parents=True, exist_ok=True)
        frames_dir = destination / "frames"
        frames_dir.mkdir(exist_ok=True)
        exported_frames: list[Path] = []
        for local_index, source in enumerate(subset):
            target = frames_dir / f"{job.animation.name}_{direction}_{local_index:03d}.png"
            shutil.copy2(source, target)
            exported_frames.append(target)
        sheet_path = destination / f"{job.animation.name}_{direction}.png"
        sheet = build_spritesheet(
            exported_frames,
            sheet_path,
            layout=layout,
            cell_size=job.render.cell_size,
        )
        prefix = "" if len(job.animation.directions) == 1 else f"{direction}."
        outputs[f"{prefix}sheet"] = str(sheet.output_path)
        if "godot" in job.export.formats:
            resource_dir = (job.export.godot_resource_dir or "res://assets/generated").rstrip("/")
            metadata, tres = export_godot_bundle(
                sheet=sheet,
                frame_paths=exported_frames,
                output_directory=destination,
                texture_resource_path=f"{resource_dir}/{sheet_path.name}",
                animation=f"{job.animation.name}_{direction}",
                fps=job.animation.fps,
                loop=job.animation.loop,
                anchors=subset_anchors,
            )
            outputs[f"{prefix}metadata"] = str(metadata)
            outputs[f"{prefix}tres"] = str(tres)
    return outputs
