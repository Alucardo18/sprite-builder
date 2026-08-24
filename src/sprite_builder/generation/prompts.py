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
    semantic = job.quality_gates.semantic_integrity
    semantic_contract = (
        "Keep every foot visible in the pose complete, including heels, soles, and readable toe "
        "silhouettes inside the frame. "
        "Transparent padding below a limb does not prove that the limb is complete. "
        "Preserve a stable ground-support row across frames. Never repair anatomy by pasting, "
        "stretching, or scaling a rectangular crop from another pose; reconstruct it in the "
        "current pose while leaving the accepted torso, head, equipment, and canvas scale fixed."
    )
    if semantic.enabled:
        semantic_contract += (
            f" Deterministic review uses body ROI {semantic.body_roi_x}, at least "
            f"{semantic.min_bottom_gutter_px}px bottom gutter, "
            f"{semantic.required_support_components} support component(s), and no more than "
            f"{semantic.max_support_y_jitter_px:g}px support-row jitter."
        )
    return {
        "character_description": identity.get(
            "description", identity.get("name", job.character.id)
        ),
        "immutable_features": "\n".join(
            f"- {item}" for item in identity.get("immutable_features", ())
        ),
        "pose_rules": (
            f"Readable {job.animation.name} pose; stable torso and ground plane; "
            "move only anatomy and equipment required by the named phase."
        ),
        "style_rules": "; ".join(f"{key}: {item}" for key, item in visual.items()),
        "prohibited_changes": "\n".join(
            f"- {item}" for item in identity.get("forbidden_changes", ())
        ),
        "semantic_contract": semantic_contract,
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
