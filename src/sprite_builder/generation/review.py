"""Immutable human review decisions for ingested generation requests."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sprite_builder.generation.queue import GenerationRequest
from sprite_builder.orchestration import atomic_write_json, sha256_file, stable_digest
from sprite_builder.sheets.models import utc_now


@dataclass(frozen=True, slots=True)
class RequestDecision:
    schema_version: str
    request_id: str
    job_id: str
    status: Literal["accepted", "rejected"]
    raw_path: str
    raw_sha256: str
    notes: str
    created_at: str
    decision_id: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def latest_request_decision(
    request_id: str,
    *,
    job_id: str,
    workspace: str | Path,
) -> RequestDecision | None:
    root = Path(workspace).resolve()
    pointer = (
        root
        / "jobs"
        / job_id
        / "generation"
        / "decisions"
        / f"{request_id}.latest.json"
    )
    if not pointer.is_file():
        return None
    return RequestDecision(**json.loads(pointer.read_text(encoding="utf-8")))


def record_request_decision(
    request: GenerationRequest,
    status: Literal["accepted", "rejected"],
    *,
    workspace: str | Path,
    notes: str = "",
) -> RequestDecision:
    root = Path(workspace).resolve()
    raw = root / "jobs" / request.job_id / "raw" / request.output_filename
    if not raw.is_file():
        raise FileNotFoundError(f"Cannot review a request before ingestion: {raw}")
    existing = latest_request_decision(
        request.request_id,
        job_id=request.job_id,
        workspace=root,
    )
    if existing is not None:
        if existing.status == status and existing.notes == notes:
            return existing
        raise FileExistsError(
            f"Request {request.request_id} already has terminal decision "
            f"{existing.status}; create a new candidate attempt"
        )

    raw_sha = sha256_file(raw)
    identity = {
        "request_id": request.request_id,
        "status": status,
        "raw_sha256": raw_sha,
        "notes": notes,
    }
    decision_id = stable_digest(identity)[:20]
    decision = RequestDecision(
        schema_version="1.0",
        request_id=request.request_id,
        job_id=request.job_id,
        status=status,
        raw_path=str(raw.relative_to(root)),
        raw_sha256=raw_sha,
        notes=notes,
        created_at=utc_now(),
        decision_id=decision_id,
    )
    directory = root / "jobs" / request.job_id / "generation" / "decisions"
    immutable = directory / f"{request.request_id}.{decision_id}.json"
    pointer = directory / f"{request.request_id}.latest.json"
    atomic_write_json(immutable, decision.to_dict())
    atomic_write_json(pointer, decision.to_dict())
    return decision

