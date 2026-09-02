"""Prepare deterministic GPT Image 2 requests for complete native sheets."""

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
    candidate_index: int
    prompt_path: str
    reference_paths: tuple[str, ...]
    output_filename: str
    source_size: tuple[int, int]
    quality: str
    request_kind: str = "sheet"
    sheet_layout: str = "horizontal"
    sheet_rows: int = 1
    sheet_columns: int = 1
    sheet_gutter_px: int = 0
    sheet_frame_count: int = 1
    background_mode: str = "chroma"
    background_color: str = "#00FF00"
    background_fallback: str = "strict_chroma"
    max_alpha_retries: int = 2
    alpha_retry_index: int = 0
    parent_request_id: str | None = None
    manual_session_id: str | None = None
    status: str = "prepared"
    source_kind: str = "generated"

    def __post_init__(self) -> None:
        if self.request_kind != "sheet":
            raise ValueError("Only request_kind=sheet is supported")
        if self.source_kind not in {"generated", "manual_alpha"}:
            raise ValueError(f"Unsupported sheet source_kind: {self.source_kind}")

    @property
    def attempt_number(self) -> int:
        """One-based generation attempt number, including the initial request."""

        return self.alpha_retry_index + 1

    @property
    def max_attempts(self) -> int:
        """Total permitted attempts, including the initial request."""

        return self.max_alpha_retries + 1

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["reference_paths"] = list(self.reference_paths)
        result["source_size"] = list(self.source_size)
        return result


def _request_stem(request: GenerationRequest) -> str:
    return f"{request.animation}_{request.direction}_sheet"


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
    raw_dir = root / "jobs" / job.job_id / "raw"
    queue_dir.mkdir(parents=True, exist_ok=True)
    prompt_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    requests: list[GenerationRequest] = []
    canonical_references = [str(path) for path in job.character.references]
    sheet_rows, sheet_columns = job.generation.resolved_sheet_grid(
        job.animation.frame_count
    )
    if (
        job.generation.source_size[0]
        <= job.generation.sheet.gutter_px * (sheet_columns - 1)
        or job.generation.source_size[1]
        <= job.generation.sheet.gutter_px * (sheet_rows - 1)
    ):
        raise ValueError("SHEET_LAYOUT_INVALID: gutter leaves no positive native cell area")
    for direction in job.animation.directions:
        frame_plan = [
            {
                "number": index + 1,
                "phase": phase,
                "directive": phase.replace("_", " "),
            }
            for index, phase in enumerate(
                job.animation.phases
                or tuple(f"frame_{index:03d}" for index in range(job.animation.frame_count))
            )
        ]
        context = {
            **character_context,
            "animation": job.animation.name,
            "direction": direction,
            "frame_count": job.animation.frame_count,
            "frame_plan": frame_plan,
            "source_width": job.generation.source_size[0],
            "source_height": job.generation.source_size[1],
            "sheet_layout": job.generation.sheet.layout,
            "sheet_rows": sheet_rows,
            "sheet_columns": sheet_columns,
            "sheet_gutter_px": job.generation.sheet.gutter_px,
            "sheet_cell_width": (
                job.generation.source_size[0]
                - job.generation.sheet.gutter_px * (sheet_columns - 1)
            )
            / sheet_columns,
            "sheet_cell_height": (
                job.generation.source_size[1]
                - job.generation.sheet.gutter_px * (sheet_rows - 1)
            )
            / sheet_rows,
            "sheet_order": (
                "left-to-right"
                if job.generation.sheet.layout == "horizontal"
                else "top-to-bottom"
                if job.generation.sheet.layout == "vertical"
                else "row-major, left-to-right"
            ),
            "background_color": job.generation.background_color,
            "background_instruction": character_context.get(
                "background_instruction",
                "One character only on a flat uniform "
                f"{job.generation.background_color} background.",
            ),
        }
        prompt = prompt_compiler.animation_sheet(context)
        prompt_digest = stable_digest({"prompt": prompt})[:12]
        prompt_path = prompt_dir / f"{direction}_sheet_{prompt_digest}.txt"
        if not prompt_path.exists():
            prompt_path.write_text(prompt, encoding="utf-8")
        for candidate_index in range(job.generation.candidates_per_sheet):
            identity = {
                "job": job.job_id,
                "direction": direction,
                "request_kind": "sheet",
                "frame_count": job.animation.frame_count,
                "candidate": candidate_index,
                "prompt": prompt,
                "references": canonical_references,
            }
            request_id = stable_digest(identity)[:20]
            filename = (
                f"{job.animation.name}_{direction}_sheet"
                f"_candidate_{candidate_index:02d}_{request_id}.png"
            )
            request = GenerationRequest(
                schema_version="1.0",
                request_id=request_id,
                job_id=job.job_id,
                character_id=job.character.id,
                animation=job.animation.name,
                direction=direction,
                candidate_index=candidate_index,
                prompt_path=str(prompt_path.relative_to(root)),
                reference_paths=tuple(canonical_references),
                output_filename=filename,
                source_size=job.generation.source_size,
                quality=job.generation.quality,
                request_kind="sheet",
                sheet_layout=job.generation.sheet.layout,
                sheet_rows=sheet_rows,
                sheet_columns=sheet_columns,
                sheet_gutter_px=job.generation.sheet.gutter_px,
                sheet_frame_count=job.animation.frame_count,
                background_mode=job.generation.background_mode,
                background_color=job.generation.background_color,
                background_fallback=job.generation.background_fallback,
                max_alpha_retries=job.generation.max_alpha_retries,
            )
            request_path = queue_dir / f"{request_id}.json"
            payload = json.dumps(request.to_dict(), indent=2, sort_keys=True) + "\n"
            if request_path.exists() and request_path.read_text(encoding="utf-8") != payload:
                raise FileExistsError(f"Request id collision: {request_path}")
            if not request_path.exists():
                request_path.write_text(payload, encoding="utf-8")
            requests.append(request)
    index_path = queue_dir / "index.json"
    existing_ids = (
        json.loads(index_path.read_text(encoding="utf-8")).get("request_ids", [])
        if index_path.is_file()
        else []
    )
    base_ids = {request.request_id for request in requests}
    active_ids = set(base_ids)
    preserved_dynamic: list[str] = []
    pending_existing = [
        item for item in existing_ids if isinstance(item, str) and item not in base_ids
    ]
    while pending_existing:
        progress = False
        for request_id in tuple(pending_existing):
            path = queue_dir / f"{request_id}.json"
            if not path.is_file():
                pending_existing.remove(request_id)
                continue
            dynamic = json.loads(path.read_text(encoding="utf-8"))
            if dynamic.get("request_kind") != "sheet":
                # Keep obsolete request files as evidence, but never carry them
                # into the active native-sheet queue.
                pending_existing.remove(request_id)
                continue
            parent = dynamic.get("parent_request_id")
            if parent in active_ids:
                active_ids.add(request_id)
                preserved_dynamic.append(request_id)
                pending_existing.remove(request_id)
                progress = True
        if not progress:
            break
    index = {
        "schema_version": "1.0",
        "job_id": job.job_id,
        "request_count": len(requests) + len(preserved_dynamic),
        "request_ids": [request.request_id for request in requests] + preserved_dynamic,
    }
    index_path.write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return tuple(requests)


def pending_requests(requests: Iterable[GenerationRequest]) -> tuple[GenerationRequest, ...]:
    return tuple(request for request in requests if request.status == "prepared")


def _append_request(root: Path, request: GenerationRequest) -> Path:
    request_dir = root / "jobs" / request.job_id / "generation" / "requests"
    request_dir.mkdir(parents=True, exist_ok=True)
    request_path = request_dir / f"{request.request_id}.json"
    payload = json.dumps(request.to_dict(), indent=2, sort_keys=True) + "\n"
    if request_path.exists() and request_path.read_text(encoding="utf-8") != payload:
        raise FileExistsError(f"Request id collision: {request_path}")
    if not request_path.exists():
        request_path.write_text(payload, encoding="utf-8")
    index_path = request_dir / "index.json"
    index = (
        json.loads(index_path.read_text(encoding="utf-8"))
        if index_path.is_file()
        else {"schema_version": "1.0", "job_id": request.job_id, "request_ids": []}
    )
    request_ids = [item for item in index.get("request_ids", []) if isinstance(item, str)]
    if request.request_id not in request_ids:
        if request.parent_request_id in request_ids:
            parent_index = request_ids.index(request.parent_request_id)
            request_ids.insert(parent_index + 1, request.request_id)
        else:
            request_ids.append(request.request_id)
    index["request_ids"] = request_ids
    index["request_count"] = len(request_ids)
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return request_path


def prepare_alpha_retry(
    request: GenerationRequest,
    *,
    workspace: str | Path,
    max_retries: int = 2,
) -> tuple[GenerationRequest, Path]:
    """Prepare one immutable transparent-alpha retry without invoking image generation."""

    if request.alpha_retry_index >= max_retries:
        raise ValueError(f"Alpha retry limit reached for {request.request_id}")
    root = Path(workspace).resolve()
    retry_index = request.alpha_retry_index + 1
    original_prompt = root / request.prompt_path
    retry_prompt = original_prompt.with_name(
        f"{original_prompt.stem}.alpha_retry_{retry_index:02d}{original_prompt.suffix}"
    )
    if not retry_prompt.exists():
        alpha_contract = (
            "ALPHA OUTPUT CONTRACT - HIGHEST PRIORITY\n"
            f"Attempt {retry_index + 1} of {max_retries + 1}. The preceding output was "
            "opaque. Return one complete native-resolution sprite sheet on a genuinely "
            "transparent canvas. Keep the "
            "canvas outside the subject visually empty; do not add scenery, a floor, panel, "
            "border, or ambient backdrop. If any later instruction conflicts with this "
            "contract, this contract wins.\n\n"
        )
        retry_prompt.write_text(
            alpha_contract + original_prompt.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    identity = {
        "parent": request.request_id,
        "alpha_retry": retry_index,
        "prompt": retry_prompt.read_text(encoding="utf-8"),
        "references": request.reference_paths,
    }
    request_id = stable_digest(identity)[:20]
    filename = (
        f"{_request_stem(request)}_candidate_{request.candidate_index:02d}"
        f"_alpha_retry_{retry_index:02d}_{request_id}.png"
    )
    retry = GenerationRequest(
        schema_version=request.schema_version,
        request_id=request_id,
        job_id=request.job_id,
        character_id=request.character_id,
        animation=request.animation,
        direction=request.direction,
        candidate_index=request.candidate_index,
        prompt_path=str(retry_prompt.relative_to(root)),
        reference_paths=request.reference_paths,
        output_filename=filename,
        source_size=request.source_size,
        quality=request.quality,
        request_kind="sheet",
        sheet_layout=request.sheet_layout,
        sheet_rows=request.sheet_rows,
        sheet_columns=request.sheet_columns,
        sheet_gutter_px=request.sheet_gutter_px,
        sheet_frame_count=request.sheet_frame_count,
        background_mode=request.background_mode,
        background_color=request.background_color,
        background_fallback=request.background_fallback,
        max_alpha_retries=max_retries,
        alpha_retry_index=retry_index,
        parent_request_id=request.request_id,
    )
    return retry, _append_request(root, retry)


def prepare_manual_alpha_request(
    request: GenerationRequest,
    *,
    workspace: str | Path,
    session_id: str,
) -> tuple[GenerationRequest, Path]:
    """Create a queue record that points to a UI session instead of image generation."""

    root = Path(workspace).resolve()
    identity = {
        "parent": request.request_id,
        "manual_alpha_session": session_id,
    }
    request_id = stable_digest(identity)[:20]
    filename = (
        f"{_request_stem(request)}_candidate_{request.candidate_index:02d}"
        f"_manual_alpha_{request_id}.png"
    )
    manual = GenerationRequest(
        schema_version=request.schema_version,
        request_id=request_id,
        job_id=request.job_id,
        character_id=request.character_id,
        animation=request.animation,
        direction=request.direction,
        candidate_index=request.candidate_index,
        prompt_path=request.prompt_path,
        reference_paths=request.reference_paths,
        output_filename=filename,
        source_size=request.source_size,
        quality=request.quality,
        request_kind="sheet",
        sheet_layout=request.sheet_layout,
        sheet_rows=request.sheet_rows,
        sheet_columns=request.sheet_columns,
        sheet_gutter_px=request.sheet_gutter_px,
        sheet_frame_count=request.sheet_frame_count,
        status="manual_review",
        source_kind="manual_alpha",
        background_mode="transparent_required",
        background_color=request.background_color,
        background_fallback="manual_ui",
        max_alpha_retries=request.max_alpha_retries,
        alpha_retry_index=request.alpha_retry_index,
        parent_request_id=request.request_id,
        manual_session_id=session_id,
    )
    return manual, _append_request(root, manual)
