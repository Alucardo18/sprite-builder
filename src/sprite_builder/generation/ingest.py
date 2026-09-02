"""Ingest images created by Codex's built-in image tool."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sprite_builder.domain.errors import ConfigurationError
from sprite_builder.generation.queue import (
    GenerationRequest,
    prepare_alpha_retry,
    prepare_manual_alpha_request,
)
from sprite_builder.orchestration.artifacts import sha256_file
from sprite_builder.postprocess import inspect_native_sheet_alpha


@dataclass(frozen=True, slots=True)
class IngestedImage:
    schema_version: str
    request_id: str
    source_path: str
    workspace_path: str
    sha256: str
    width: int
    height: int
    mode: str
    status: str = "ingested"
    alpha_inspection: dict[str, Any] | None = None
    retry_request_path: str | None = None
    manual_session_id: str | None = None
    manual_request_path: str | None = None
    request_kind: str = "sheet"
    native_size_verified: bool = False


def ingest_candidate(
    request: GenerationRequest,
    generated_path: str | Path,
    *,
    workspace: str | Path,
) -> IngestedImage:
    """Validate and copy one generated native sheet into immutable raw job storage."""

    source = Path(generated_path).resolve()
    if not source.is_file() or source.suffix.lower() != ".png":
        raise ConfigurationError(f"Generated candidate must be an existing PNG: {source}")
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to ingest generated images") from exc
    with Image.open(source) as image:
        image.verify()
    with Image.open(source) as image:
        width, height = image.size
        mode = image.mode
    if width < 64 or height < 64:
        raise ConfigurationError(f"Generated image is unexpectedly small: {width}x{height}")
    if (width, height) != request.source_size:
        raise ConfigurationError(
            "SHEET_NATIVE_SIZE_MISMATCH: GPT Image 2 returned "
            f"{width}x{height}, expected the configured native sheet canvas "
            f"{request.source_size[0]}x{request.source_size[1]}; no crop or resize is allowed"
        )
    native_size_verified = True

    root = Path(workspace).resolve()
    destination_dir = root / "jobs" / request.job_id / "raw"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / request.output_filename
    if destination.exists():
        if sha256_file(destination) != sha256_file(source):
            raise FileExistsError(f"Refusing to overwrite a different candidate: {destination}")
    else:
        shutil.copy2(source, destination)
    metadata_path = destination.with_suffix(".ingest.json")
    if metadata_path.is_file():
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        if existing.get("sha256") == sha256_file(destination):
            return IngestedImage(**existing)

    status = "ingested"
    alpha_payload: dict[str, Any] | None = None
    retry_request_path: str | None = None
    manual_session_id: str | None = None
    manual_request_path: str | None = None
    if request.background_mode != "chroma":
        inspection = inspect_native_sheet_alpha(
            destination,
            rows=request.sheet_rows,
            columns=request.sheet_columns,
            gutter_px=request.sheet_gutter_px,
            frame_count=request.sheet_frame_count,
        )
        alpha_payload = inspection.to_dict()
        acceptable = inspection.status == "pass" or (
            inspection.status == "review"
            and set(inspection.reasons) <= {"hidden_rgb_under_transparency"}
        )
        if not acceptable:
            from sprite_builder.generation.review import record_request_decision

            record_request_decision(
                request,
                "rejected",
                workspace=root,
                notes=(
                    f"alpha gate {inspection.status}: {', '.join(inspection.reasons)}"
                ),
            )
            if (
                request.source_kind != "manual_alpha"
                and request.alpha_retry_index < request.max_alpha_retries
            ):
                _retry, retry_path = prepare_alpha_retry(
                    request,
                    workspace=root,
                    max_retries=request.max_alpha_retries,
                )
                status = "alpha_retry_required"
                retry_request_path = str(retry_path.relative_to(root))
            elif request.background_fallback != "reject":
                from sprite_builder.sheets import SheetSessionStore

                session = SheetSessionStore(root).create(
                    destination,
                    source_name=f"{request.request_id}-alpha-review.png",
                )
                _manual, manual_path = prepare_manual_alpha_request(
                    request,
                    workspace=root,
                    session_id=session.session_id,
                )
                status = "manual_review"
                manual_session_id = session.session_id
                manual_request_path = str(manual_path.relative_to(root))
            else:
                status = "alpha_rejected"

    record = IngestedImage(
        schema_version="1.0",
        request_id=request.request_id,
        source_path=str(source),
        workspace_path=str(destination.relative_to(root)),
        sha256=sha256_file(destination),
        width=width,
        height=height,
        mode=mode,
        status=status,
        alpha_inspection=alpha_payload,
        retry_request_path=retry_request_path,
        manual_session_id=manual_session_id,
        manual_request_path=manual_request_path,
        request_kind=request.request_kind,
        native_size_verified=native_size_verified,
    )
    metadata_path.write_text(
        json.dumps(asdict(record), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record
