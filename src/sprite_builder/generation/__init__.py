"""Prompt compilation, generation-request queueing, and image ingestion."""

from sprite_builder.generation.ingest import IngestedImage, ingest_candidate
from sprite_builder.generation.prompts import PromptCompiler, build_character_context
from sprite_builder.generation.queue import GenerationRequest, prepare_requests
from sprite_builder.generation.review import (
    RequestDecision,
    latest_request_decision,
    record_request_decision,
)

__all__ = [
    "GenerationRequest",
    "IngestedImage",
    "PromptCompiler",
    "RequestDecision",
    "build_character_context",
    "ingest_candidate",
    "latest_request_decision",
    "prepare_requests",
    "record_request_decision",
]
