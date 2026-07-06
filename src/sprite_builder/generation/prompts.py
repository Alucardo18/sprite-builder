"""Compile stable character prompts while varying only animation phase."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sprite_builder.domain.config import load_mapping
from sprite_builder.domain.errors import ConfigurationError
from sprite_builder.domain.models import JobSpec


class PromptCompiler:
    def __init__(self, template_dir: str | Path) -> None:
        self.template_dir = Path(template_dir)

    def render(self, template_name: str, context: Mapping[str, Any]) -> str:
        template = (self.template_dir / template_name).read_text(encoding="utf-8")
        try:
            from jinja2 import Environment, StrictUndefined
        except ImportError:
            return _minimal_render(template, context)
        environment = Environment(undefined=StrictUndefined, autoescape=False)
        return environment.from_string(template).render(**context).strip() + "\n"

    def animation_frame(self, context: Mapping[str, Any]) -> str:
        return self.render("animation_frame.jinja2", context)


def build_character_context(
    job: JobSpec,
    *,
    workspace: str | Path,
) -> dict[str, object]:
    """Build the canonical prompt context shared by individual and batch jobs."""

    root = Path(workspace).resolve()
    bible = load_mapping(root / job.character.bible)
    identity = bible.get("identity", {})
    visual = bible.get("visual_rules", {})
    if not isinstance(identity, Mapping) or not isinstance(visual, Mapping):
        raise ConfigurationError(f"Invalid Character Bible: {job.character.bible}")
    return {
        "character_description": identity.get(
            "description", identity.get("name", job.character.id)
        ),
        "immutable_features": "\n".join(
            f"- {item}" for item in identity.get("immutable_features", ())
        ),
        "pose_rules": (
            "Readable walk-cycle pose; stable upright torso; move only limbs required by the phase."
        ),
        "style_rules": "; ".join(f"{key}: {item}" for key, item in visual.items()),
        "prohibited_changes": "\n".join(
            f"- {item}" for item in identity.get("forbidden_changes", ())
        ),
    }


def _minimal_render(template: str, context: Mapping[str, Any]) -> str:
    """Small offline fallback for templates containing only scalar substitutions."""

    result = template
    for key, value in context.items():
        result = result.replace("{{ " + key + " }}", str(value))
        result = result.replace("{{" + key + "}}", str(value))
    if "{{" in result or "{%" in result:
        raise RuntimeError("Install Jinja2 to render this prompt template")
    return result.strip() + "\n"
