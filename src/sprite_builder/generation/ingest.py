"""Ingest images created by Codex's built-in image tool."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from sprite_builder.domain.errors import ConfigurationError
from sprite_builder.generation.queue import GenerationRequest
from sprite_builder.orchestration.artifacts import sha256_file


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


def ingest_candidate(
    request: GenerationRequest,
    generated_path: str | Path,
    *,
    workspace: str | Path,
) -> IngestedImage:
    """Validate and copy one generated PNG into immutable raw job storage."""

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
    if request.source_kind != "seed" and (width < 64 or height < 64):
        raise ConfigurationError(f"Generated image is unexpectedly small: {width}x{height}")

    root = Path(workspace).resolve()
    destination_dir = root / "jobs" / request.job_id / "raw"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / request.output_filename
    if destination.exists():
        if sha256_file(destination) != sha256_file(source):
            raise FileExistsError(f"Refusing to overwrite a different candidate: {destination}")
    else:
        shutil.copy2(source, destination)

    record = IngestedImage(
        schema_version="1.0",
        request_id=request.request_id,
        source_path=str(source),
        workspace_path=str(destination.relative_to(root)),
        sha256=sha256_file(destination),
        width=width,
        height=height,
        mode=mode,
    )
    metadata_path = destination.with_suffix(".ingest.json")
    metadata_path.write_text(
        json.dumps(asdict(record), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record
