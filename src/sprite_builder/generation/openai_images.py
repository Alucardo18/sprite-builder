"""Opt-in GPT Image 2 executor for prepared generation requests."""

from __future__ import annotations

import base64
import json
import os
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sprite_builder.domain.errors import ConfigurationError
from sprite_builder.generation.ingest import IngestedImage, ingest_candidate
from sprite_builder.generation.queue import GenerationRequest
from sprite_builder.orchestration.artifacts import sha256_file

GPT_IMAGE_MODEL = "gpt-image-2"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True)
class OpenAIImageGeneration:
    schema_version: str
    request_id: str
    model: str
    endpoint: str
    background: str
    output_format: str
    quality: str
    size: str
    output_path: str
    sha256: str
    request_kind: str
    sheet_frame_count: int
    native_source_size: tuple[int, int]
    response_background: str | None
    response_output_format: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OpenAIGenerationResult:
    generation: OpenAIImageGeneration
    ingest: IngestedImage


@dataclass(frozen=True, slots=True)
class OpenAIImageRequestPlan:
    model: str
    endpoint: str
    background: str
    output_format: str
    quality: str
    size: str
    reference_count: int
    request_kind: str
    sheet_frame_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def plan_openai_request(
    request: GenerationRequest,
    *,
    model: str = GPT_IMAGE_MODEL,
) -> OpenAIImageRequestPlan:
    """Return the non-secret structured provider payload for one request."""

    if model != GPT_IMAGE_MODEL:
        raise ConfigurationError(
            f"This executor is pinned to {GPT_IMAGE_MODEL}; received {model}"
        )
    return OpenAIImageRequestPlan(
        model=model,
        endpoint="images.edit" if request.reference_paths else "images.generate",
        background="opaque" if request.background_mode == "chroma" else "transparent",
        output_format="png",
        quality=request.quality,
        size=f"{request.source_size[0]}x{request.source_size[1]}",
        reference_count=len(request.reference_paths),
        request_kind=request.request_kind,
        sheet_frame_count=request.sheet_frame_count,
    )


def generate_openai_candidate(
    request: GenerationRequest,
    *,
    workspace: str | Path,
    client: Any | None = None,
    model: str = GPT_IMAGE_MODEL,
) -> OpenAIGenerationResult:
    """Generate one complete sheet through the Image API and run ingestion gates."""

    plan = plan_openai_request(request, model=model)
    if request.source_kind == "manual_alpha":
        raise ConfigurationError(f"Request {request.request_id} is not an API generation request")

    root = Path(workspace).resolve()
    prompt_path = root / request.prompt_path
    if not prompt_path.is_file():
        raise ConfigurationError(f"Prompt is missing: {prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8")

    references = tuple(_resolve_reference(path, root) for path in request.reference_paths)
    missing = [path for path in references if not path.is_file()]
    if missing:
        raise ConfigurationError(f"Reference image is missing: {missing[0]}")

    api = client if client is not None else _openai_client()
    common: dict[str, object] = {
        "model": plan.model,
        "prompt": prompt,
        "background": plan.background,
        "output_format": plan.output_format,
        "quality": plan.quality,
        "size": plan.size,
    }

    if references:
        with ExitStack() as stack:
            images = [stack.enter_context(path.open("rb")) for path in references]
            response = api.images.edit(image=images, **common)
        endpoint = plan.endpoint
    else:
        response = api.images.generate(**common)
        endpoint = plan.endpoint

    encoded = _first_image_base64(response)
    try:
        png_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ConfigurationError("GPT Image 2 returned invalid base64 image data") from exc
    if not png_bytes.startswith(PNG_SIGNATURE):
        raise ConfigurationError("GPT Image 2 did not return PNG bytes")

    destination = root / "jobs" / request.job_id / "raw" / request.output_filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite generated candidate: {destination}")
    destination.write_bytes(png_bytes)

    response_background = _response_value(response, "background")
    response_output_format = _response_value(response, "output_format")
    generation = OpenAIImageGeneration(
        schema_version="1.0",
        request_id=request.request_id,
        model=model,
        endpoint=endpoint,
        background=plan.background,
        output_format=plan.output_format,
        quality=plan.quality,
        size=plan.size,
        output_path=str(destination.relative_to(root)),
        sha256=sha256_file(destination),
        request_kind=request.request_kind,
        sheet_frame_count=request.sheet_frame_count,
        native_source_size=request.source_size,
        response_background=response_background,
        response_output_format=response_output_format,
    )
    destination.with_suffix(".provider.json").write_text(
        json.dumps(generation.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    ingest = ingest_candidate(request, destination, workspace=root)
    return OpenAIGenerationResult(generation=generation, ingest=ingest)


def _openai_client() -> Any:
    if not os.environ.get("OPENAI_API_KEY"):
        raise ConfigurationError(
            "OPENAI_API_KEY is required for generate-openai; no credential was found"
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ConfigurationError(
            "OpenAI image support is not installed; install sprite-builder[image-api]"
        ) from exc
    return OpenAI()


def _resolve_reference(value: str, root: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _first_image_base64(response: Any) -> str:
    data = _response_value(response, "data")
    if not isinstance(data, (list, tuple)) or not data:
        raise ConfigurationError("GPT Image 2 response did not contain image data")
    encoded = _response_value(data[0], "b64_json")
    if not isinstance(encoded, str) or not encoded:
        raise ConfigurationError("GPT Image 2 response did not contain b64_json")
    return encoded


def _response_value(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)
