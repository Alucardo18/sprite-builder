"""Native full-sheet source validation for the sprite generation pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from sprite_builder.domain.models import JobSpec
from sprite_builder.orchestration import atomic_write_json, sha256_file


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    return atomic_write_json(path, value, sort_keys=False)


def validate_sheet_sources(job: JobSpec, *, workspace: str | Path) -> dict[str, Any]:
    """Validate complete sheet inputs without cropping, resizing, or splitting pixels."""

    root = Path(workspace).resolve()
    request_dir = root / "jobs" / job.job_id / "generation" / "requests"
    index_path = request_dir / "index.json"
    if not index_path.is_file():
        raise FileNotFoundError(f"Missing generation request index: {index_path}")
    request_ids = json.loads(index_path.read_text(encoding="utf-8")).get("request_ids", [])
    records: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for request_id in request_ids:
        if not isinstance(request_id, str):
            continue
        request_path = request_dir / f"{request_id}.json"
        if not request_path.is_file():
            raise FileNotFoundError(f"Missing generation request: {request_path}")
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if request.get("request_kind") != "sheet":
            raise ValueError(
                f"LEGACY_REQUEST_REJECTED: {request_path.name} is not a native sheet request"
            )
        raw_path = root / "jobs" / job.job_id / "raw" / str(request["output_filename"])
        record: dict[str, Any] = {
            "request_id": request_id,
            "direction": str(request.get("direction", "")),
            "candidate_index": int(request.get("candidate_index", 0)),
            "source_kind": str(request.get("source_kind", "generated")),
            "alpha_retry_index": int(request.get("alpha_retry_index", 0)),
            "request": str(request_path.relative_to(root)),
            "source": str(raw_path.relative_to(root)),
            "exists": raw_path.is_file(),
        }
        decision_path = (
            root
            / "jobs"
            / job.job_id
            / "generation"
            / "decisions"
            / f"{request_id}.latest.json"
        )
        if decision_path.is_file():
            record["decision"] = str(
                json.loads(decision_path.read_text(encoding="utf-8")).get("status", "")
            )
        if raw_path.is_file():
            with Image.open(raw_path) as image:
                image.verify()
            with Image.open(raw_path) as image:
                record["size"] = list(image.size)
                record["mode"] = image.mode
                if image.size != job.generation.source_size:
                    raise ValueError(
                        "SHEET_NATIVE_SIZE_MISMATCH: "
                        f"{raw_path.name} is {image.size}, expected {job.generation.source_size}; "
                        "the source must remain native and must not be cropped or resized"
                    )
            record["sha256"] = sha256_file(raw_path)
            selected.append(record)
        records.append(record)

    selected_by_direction: dict[str, dict[str, Any]] = {}
    for direction in job.animation.directions:
        candidates = [item for item in selected if item["direction"] == direction]
        accepted = [item for item in candidates if item.get("decision") == "accepted"]
        if accepted:
            selected_by_direction[direction] = accepted[-1]
        elif candidates:
            # Request index order is lineage order, so the last available source is
            # the newest retry/manual-alpha artifact for this direction.
            selected_by_direction[direction] = candidates[-1]
    missing = [
        direction
        for direction in job.animation.directions
        if direction not in selected_by_direction
    ]
    if missing:
        raise FileNotFoundError(
            "Missing native sheet source for direction(s): "
            + ", ".join(missing)
            + "; ingest one complete sheet per direction first"
        )
    selected_sources = [selected_by_direction[direction] for direction in job.animation.directions]
    manifest = {
        "schema_version": "1.0",
        "job_id": job.job_id,
        "mode": "sheet",
        "source_size": list(job.generation.source_size),
        "frame_count": job.animation.frame_count,
        "sheet": job.generation.sheet.to_dict(),
        "selected": selected_sources,
        "candidates": records,
        "transformations": {
            "crop": False,
            "resize": False,
            "resample": False,
            "pixel_split": False,
            "alpha_removal": "manual_or_provider_only",
        },
        "status": "ready_for_manual_alpha_review",
    }
    manifest_path = root / "jobs" / job.job_id / "manifests" / "sheet-source.json"
    _write_json(manifest_path, manifest)
    return {**manifest, "manifest": str(manifest_path.relative_to(root))}
