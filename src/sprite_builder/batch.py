"""Validated multi-character, multi-animation batch coordination."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from sprite_builder.domain.config import load_job, load_mapping
from sprite_builder.domain.errors import ConfigurationError
from sprite_builder.domain.models import JobSpec
from sprite_builder.generation import (
    PromptCompiler,
    build_character_context,
    prepare_requests,
)


@dataclass(frozen=True, slots=True)
class BatchCharacter:
    """One character and the animation JobSpecs requested for it."""

    character_id: str
    jobs: tuple[Path, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BatchCharacter:
        character_id = str(value.get("id", "")).strip()
        if not character_id:
            raise ConfigurationError("batch character id is required")
        raw_jobs = value.get("jobs", ())
        if not isinstance(raw_jobs, list) or not raw_jobs:
            raise ConfigurationError(f"batch character {character_id!r} requires at least one job")
        jobs = tuple(Path(str(item)) for item in raw_jobs)
        if len(jobs) != len(set(jobs)):
            raise ConfigurationError(f"batch character {character_id!r} contains duplicate jobs")
        return cls(character_id=character_id, jobs=jobs)


@dataclass(frozen=True, slots=True)
class BatchSpec:
    """Versioned batch whose counts are derived exclusively from its lists."""

    CURRENT_SCHEMA_VERSION: ClassVar[str] = "1.0"

    schema_version: str
    batch_id: str
    characters: tuple[BatchCharacter, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BatchSpec:
        version = str(value.get("schema_version", ""))
        if version != cls.CURRENT_SCHEMA_VERSION:
            raise ConfigurationError(
                f"Unsupported batch schema_version {version!r}; "
                f"expected {cls.CURRENT_SCHEMA_VERSION}"
            )
        batch = value.get("batch", {})
        if not isinstance(batch, Mapping):
            raise ConfigurationError("batch must be an object")
        batch_id = str(batch.get("id", "")).strip()
        if not batch_id:
            raise ConfigurationError("batch.id is required")
        raw_characters = value.get("characters", ())
        if not isinstance(raw_characters, list) or not raw_characters:
            raise ConfigurationError("batch requires at least one character")
        characters = tuple(BatchCharacter.from_dict(item) for item in raw_characters)
        ids = [item.character_id for item in characters]
        if len(ids) != len(set(ids)):
            raise ConfigurationError("batch character ids must be unique")
        all_jobs = [job for character in characters for job in character.jobs]
        if len(all_jobs) != len(set(all_jobs)):
            raise ConfigurationError("a job YAML may appear only once in a batch")
        return cls(schema_version=version, batch_id=batch_id, characters=characters)

    @property
    def character_count(self) -> int:
        return len(self.characters)

    @property
    def animation_count(self) -> int:
        return sum(len(character.jobs) for character in self.characters)

    def load_jobs(self, workspace: str | Path) -> tuple[tuple[BatchCharacter, Path, JobSpec], ...]:
        """Load every job and verify character ownership and globally unique job ids."""

        root = Path(workspace).resolve()
        loaded: list[tuple[BatchCharacter, Path, JobSpec]] = []
        job_ids: set[str] = set()
        for character in self.characters:
            for configured_path in character.jobs:
                job_path = (
                    configured_path if configured_path.is_absolute() else root / configured_path
                )
                if not job_path.is_file():
                    raise ConfigurationError(f"batch job does not exist: {job_path}")
                job = load_job(job_path)
                if job.character.id != character.character_id:
                    raise ConfigurationError(
                        f"{job_path}: character {job.character.id!r} does not match "
                        f"batch entry {character.character_id!r}"
                    )
                if job.job_id in job_ids:
                    raise ConfigurationError(f"duplicate job.id in batch: {job.job_id}")
                job_ids.add(job.job_id)
                loaded.append((character, job_path, job))
        if len(loaded) != self.animation_count:
            raise ConfigurationError("derived animation count does not match loaded jobs")
        return tuple(loaded)


def load_batch(path: str | Path) -> BatchSpec:
    return BatchSpec.from_dict(load_mapping(path))


def prepare_batch(spec: BatchSpec, *, workspace: str | Path) -> dict[str, object]:
    """Prepare each job's deterministic queue without generating any image."""

    root = Path(workspace).resolve()
    compiler = PromptCompiler(root / "prompts")
    jobs: list[dict[str, object]] = []
    total_requests = 0
    for character, job_path, job in spec.load_jobs(root):
        requests = prepare_requests(
            job,
            workspace=root,
            prompt_compiler=compiler,
            character_context=build_character_context(job, workspace=root),
        )
        total_requests += len(requests)
        jobs.append(
            {
                "character_id": character.character_id,
                "job_id": job.job_id,
                "job": str(job_path),
                "animation": job.animation.name,
                "prepared": len(requests),
            }
        )
    return {
        "schema_version": spec.schema_version,
        "batch_id": spec.batch_id,
        "character_count": spec.character_count,
        "animation_count": spec.animation_count,
        "request_count": total_requests,
        "jobs": jobs,
    }


def batch_status(spec: BatchSpec, *, workspace: str | Path) -> dict[str, object]:
    """Summarize pending/ingested candidates using queue indexes and raw artifacts."""

    root = Path(workspace).resolve()
    jobs: list[dict[str, object]] = []
    total_pending = 0
    total_ingested = 0
    for character, job_path, job in spec.load_jobs(root):
        request_dir = root / "jobs" / job.job_id / "generation" / "requests"
        index_path = request_dir / "index.json"
        request_paths: list[Path] = []
        if index_path.is_file():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            request_paths = [
                request_dir / f"{request_id}.json" for request_id in index.get("request_ids", ())
            ]
        pending = 0
        ingested = 0
        for request_path in request_paths:
            if not request_path.is_file():
                raise ConfigurationError(f"batch request is missing: {request_path}")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            output_filename = str(request.get("output_filename", ""))
            if not output_filename:
                raise ConfigurationError(f"request has no output_filename: {request_path}")
            if (root / "jobs" / job.job_id / "raw" / output_filename).is_file():
                ingested += 1
            else:
                pending += 1
        total_pending += pending
        total_ingested += ingested
        jobs.append(
            {
                "character_id": character.character_id,
                "job_id": job.job_id,
                "job": str(job_path),
                "animation": job.animation.name,
                "prepared": index_path.is_file(),
                "pending": pending,
                "ingested": ingested,
                "total": pending + ingested,
            }
        )
    return {
        "schema_version": spec.schema_version,
        "batch_id": spec.batch_id,
        "character_count": spec.character_count,
        "animation_count": spec.animation_count,
        "pending": total_pending,
        "ingested": total_ingested,
        "total": total_pending + total_ingested,
        "jobs": jobs,
    }
