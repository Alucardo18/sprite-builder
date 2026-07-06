"""Prepare deterministic requests for Codex-mediated image generation."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from sprite_builder.domain.models import JobSpec
from sprite_builder.generation.prompts import PromptCompiler
from sprite_builder.orchestration.artifacts import stable_digest


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    schema_version: str
    request_id: str
    job_id: str
    character_id: str
    animation: str
    direction: str
    frame_index: int
    phase: str
    candidate_index: int
    prompt_path: str
    reference_paths: tuple[str, ...]
    output_filename: str
    source_size: tuple[int, int]
    quality: str
    status: str = "prepared"
    source_kind: str = "generated"
    seed_source_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["reference_paths"] = list(self.reference_paths)
        result["source_size"] = list(self.source_size)
        return result


def prepare_requests(
    job: JobSpec,
    *,
    workspace: str | Path,
    prompt_compiler: PromptCompiler,
    character_context: dict[str, object],
) -> tuple[GenerationRequest, ...]:
    """Write prompts and queue records; never invoke an image service."""

    root = Path(workspace).resolve()
    queue_dir = root / "jobs" / job.job_id / "generation" / "requests"
    prompt_dir = root / "jobs" / job.job_id / "generation" / "prompts"
    queue_dir.mkdir(parents=True, exist_ok=True)
    prompt_dir.mkdir(parents=True, exist_ok=True)
    requests: list[GenerationRequest] = []
    canonical_references = [str(path) for path in job.character.references]
    if job.generation.seed_frame is not None:
        canonical_references.append(str(job.generation.seed_frame))
    for direction in job.animation.directions:
        for frame_index in range(job.animation.frame_count):
            phase = (
                job.animation.phases[frame_index]
                if job.animation.phases
                else f"frame_{frame_index:03d}"
            )
            context = {
                **character_context,
                "animation": job.animation.name,
                "direction": direction,
                "frame_number": frame_index + 1,
                "frame_count": job.animation.frame_count,
                "phase": phase,
                "background_color": job.generation.background_color,
            }
            prompt = prompt_compiler.animation_frame(context)
            prompt_digest = stable_digest({"prompt": prompt})[:12]
            prompt_path = prompt_dir / f"{direction}_{frame_index:03d}_{prompt_digest}.txt"
            if not prompt_path.exists():
                prompt_path.write_text(prompt, encoding="utf-8")
            for candidate_index in range(job.generation.candidates_per_frame):
                identity = {
                    "job": job.job_id,
                    "direction": direction,
                    "frame": frame_index,
                    "candidate": candidate_index,
                    "prompt": prompt,
                    "references": canonical_references,
                }
                request_id = stable_digest(identity)[:20]
                filename = (
                    f"{job.animation.name}_{direction}_{frame_index:03d}"
                    f"_candidate_{candidate_index:02d}_{request_id}.png"
                )
                request = GenerationRequest(
                    schema_version="1.0",
                    request_id=request_id,
                    job_id=job.job_id,
                    character_id=job.character.id,
                    animation=job.animation.name,
                    direction=direction,
                    frame_index=frame_index,
                    phase=phase,
                    candidate_index=candidate_index,
                    prompt_path=str(prompt_path.relative_to(root)),
                    reference_paths=tuple(canonical_references),
                    output_filename=filename,
                    source_size=job.generation.source_size,
                    quality=job.generation.quality,
                    source_kind=(
                        "seed"
                        if job.generation.seed_frame is not None
                        and frame_index == job.generation.seed_frame_index
                        else "generated"
                    ),
                    seed_source_path=(
                        str(job.generation.seed_frame)
                        if job.generation.seed_frame is not None
                        and frame_index == job.generation.seed_frame_index
                        else None
                    ),
                )
                request_path = queue_dir / f"{request_id}.json"
                payload = json.dumps(request.to_dict(), indent=2, sort_keys=True) + "\n"
                if request_path.exists() and request_path.read_text(encoding="utf-8") != payload:
                    raise FileExistsError(f"Request id collision: {request_path}")
                if not request_path.exists():
                    request_path.write_text(payload, encoding="utf-8")
                requests.append(request)
    index = {
        "schema_version": "1.0",
        "job_id": job.job_id,
        "request_count": len(requests),
        "request_ids": [request.request_id for request in requests],
    }
    (queue_dir / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return tuple(requests)


def pending_requests(requests: Iterable[GenerationRequest]) -> tuple[GenerationRequest, ...]:
    return tuple(request for request in requests if request.status == "prepared")
