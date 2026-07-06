"""Content-addressed artifact records and atomic manifests."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sprite_builder.domain.errors import ArtifactIntegrityError


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def stable_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def atomic_write_json(
    path: str | Path,
    value: Mapping[str, Any],
    *,
    sort_keys: bool = True,
) -> Path:
    """Write a JSON object without exposing a partially-written file."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False, default=str) + "\n"
    )
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    path: str
    sha256: str
    size_bytes: int
    media_type: str = "application/octet-stream"
    role: str = "output"

    @classmethod
    def from_path(
        cls, path: str | Path, *, root: str | Path | None = None, media_type: str = ""
    ) -> ArtifactRecord:
        source = Path(path)
        stored = str(source.relative_to(root)) if root is not None else str(source)
        return cls(
            path=stored,
            sha256=sha256_file(source),
            size_bytes=source.stat().st_size,
            media_type=media_type or _guess_media_type(source),
        )


def _guess_media_type(path: Path) -> str:
    return {
        ".png": "image/png",
        ".json": "application/json",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
        ".txt": "text/plain",
    }.get(path.suffix.lower(), "application/octet-stream")


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    schema_version: str
    job_id: str
    stage: str
    status: str
    cache_key: str
    inputs: tuple[ArtifactRecord, ...] = ()
    outputs: tuple[ArtifactRecord, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    manual_review: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["inputs"] = [asdict(item) for item in self.inputs]
        value["outputs"] = [asdict(item) for item in self.outputs]
        value["warnings"] = list(self.warnings)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ArtifactManifest:
        return cls(
            schema_version=str(value["schema_version"]),
            job_id=str(value["job_id"]),
            stage=str(value["stage"]),
            status=str(value["status"]),
            cache_key=str(value["cache_key"]),
            inputs=tuple(ArtifactRecord(**item) for item in value.get("inputs", ())),
            outputs=tuple(ArtifactRecord(**item) for item in value.get("outputs", ())),
            metrics=dict(value.get("metrics", {})),
            warnings=tuple(value.get("warnings", ())),
            manual_review=bool(value.get("manual_review", False)),
            created_at=str(value["created_at"]),
        )


def build_cache_key(
    *, stage: str, config: Mapping[str, Any], inputs: Iterable[ArtifactRecord], version: str = "1"
) -> str:
    return stable_digest(
        {
            "stage": stage,
            "stage_version": version,
            "config": config,
            "inputs": [{"sha256": item.sha256, "role": item.role} for item in inputs],
        }
    )


class ArtifactStore:
    """Read/write job manifests without exposing partially-written state."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def job_dir(self, job_id: str) -> Path:
        return self.root / "jobs" / job_id

    def manifest_path(self, job_id: str, stage: str) -> Path:
        return self.job_dir(job_id) / "manifests" / f"{stage}.json"

    def write_manifest(self, manifest: ArtifactManifest) -> Path:
        target = self.manifest_path(manifest.job_id, manifest.stage)
        return atomic_write_json(target, manifest.to_dict())

    def read_manifest(self, job_id: str, stage: str) -> ArtifactManifest | None:
        path = self.manifest_path(job_id, stage)
        if not path.exists():
            return None
        return ArtifactManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def verify(self, record: ArtifactRecord) -> bool:
        path = Path(record.path)
        if not path.is_absolute():
            path = self.root / path
        if not path.is_file():
            return False
        return path.stat().st_size == record.size_bytes and sha256_file(path) == record.sha256

    def require_valid(self, manifest: ArtifactManifest) -> None:
        invalid = [record.path for record in manifest.outputs if not self.verify(record)]
        if invalid:
            raise ArtifactIntegrityError(f"Invalid artifacts: {', '.join(invalid)}")

    def cache_hit(self, job_id: str, stage: str, cache_key: str) -> bool:
        manifest = self.read_manifest(job_id, stage)
        if manifest is None or manifest.status != "passed" or manifest.cache_key != cache_key:
            return False
        return all(self.verify(record) for record in manifest.outputs)
