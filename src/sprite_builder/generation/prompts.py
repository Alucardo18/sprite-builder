"""Compile stable prompts for complete native-resolution animation sheets."""

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

    def animation_sheet(self, context: Mapping[str, Any]) -> str:
        """Compile one deterministic prompt for a complete animation sheet."""

        return self.render("animation_sheet.jinja2", context)


def build_character_context(
    job: JobSpec,
    *,
    workspace: str | Path,
) -> dict[str, object]:
    """Build the canonical prompt context shared by sheet and batch jobs."""

    root = Path(workspace).resolve()
    bible = load_mapping(root / job.character.bible)
    identity = bible.get("identity", {})
    visual = bible.get("visual_rules", {})
    if not isinstance(identity, Mapping) or not isinstance(visual, Mapping):
        raise ConfigurationError(f"Invalid Character Bible: {job.character.bible}")
    scale_profile = bible.get("scale_profile")
    scale_contract = _build_idle_scale_contract(job, scale_profile)
    semantic = job.quality_gates.semantic_integrity
    forbidden_changes = [str(item) for item in identity.get("forbidden_changes", ())]
    if job.generation.background_mode != "chroma":
        forbidden_changes = [
            item.replace("checkerboard, ", "").replace("fake transparency, ", "")
            for item in forbidden_changes
        ]
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
    if job.generation.background_mode == "chroma":
        background_instruction = (
            f"One character only on a perfectly flat uniform "
            f"{job.generation.background_color} background."
        )
    else:
        shadow_clause = (
            "A compact authored contact shadow may remain part of the isolated RGBA sprite, "
            "but there must be no opaque floor or ambient scene shadow."
            if job.render.integrated_shadow
            else "Do not include a floor or cast shadow."
        )
        requirement = (
            "Create one isolated character cutout with generous empty canvas around it. "
            f"Do not include scenery, a floor, a panel, or an ambient backdrop. {shadow_clause} "
            "Native output transparency is controlled by the image provider."
        )
        background_instruction = (
            requirement
            + (
                " Transparency is mandatory; an opaque result will be rejected."
                if job.generation.background_mode == "transparent_required"
                else " Transparency is preferred and will be verified before post-processing."
            )
        )
    prompt_negative = job.generation.prompt.negative
    if job.generation.background_mode != "chroma":
        prompt_negative = (
            prompt_negative.replace("transparent checkerboard, ", "")
            .replace("checkerboard, ", "")
            .replace("checkerboard", "")
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
            f"- {item}" for item in forbidden_changes
        ),
        "semantic_contract": semantic_contract,
        "scale_contract": scale_contract,
        "background_instruction": background_instruction,
        "shadow_instruction": (
            "Show the complete character and its compact integrated contact shadow without "
            "cropping."
            if job.render.integrated_shadow
            else "Show the complete character without cropping and do not add a shadow."
        ),
        "prompt_style": job.generation.prompt.style,
        "pixel_language": job.generation.prompt.pixel_language,
        "prompt_camera": job.generation.prompt.camera,
        "prompt_palette": job.generation.prompt.palette,
        "prompt_lighting": job.generation.prompt.lighting,
        "prompt_identity": job.generation.prompt.identity,
        "prompt_animation": job.generation.prompt.animation,
        "prompt_negative": prompt_negative,
    }


def _build_idle_scale_contract(job: JobSpec, value: object) -> str:
    """Resolve the character's approved idle scale for generation prompts.

    New Character Bibles carry this profile from creation. Idle is allowed to
    establish the profile; every other animation must consume an approved one.
    Legacy Bibles without the field retain their existing behavior so old jobs
    remain readable, but they do not claim the new canonical guarantee.
    """

    if value is None:
        return (
            "Legacy scale contract: keep body scale consistent with the approved character "
            "reference and require visual review against idle before integration."
        )
    if not isinstance(value, Mapping):
        raise ConfigurationError("Character Bible scale_profile must be an object")
    reference_animation = str(value.get("reference_animation", "")).strip()
    if reference_animation != "idle":
        raise ConfigurationError("scale_profile.reference_animation must be idle")
    status = str(value.get("status", "pending_idle_approval"))
    target_value = value.get("target_body_height_px")
    exclusions = tuple(str(item) for item in value.get("exclude_from_measurement", ()))
    exclusion_text = ", ".join(exclusions) or "weapons, staffs, detached effects, and VFX"
    if job.animation.name == "idle":
        return (
            "This idle animation is the authoritative character-scale reference. Measure and "
            "approve stable head/torso/body anatomy and the support anchor; exclude "
            f"{exclusion_text}. Record the approved Scale Profile before another animation."
        )
    if status != "approved" or target_value is None:
        raise ConfigurationError(
            "IDLE_SCALE_PROFILE_REQUIRED: approve scale_profile from the character idle "
            f"before generating animation {job.animation.name}"
        )
    target = int(target_value)
    if target <= 0:
        raise ConfigurationError("scale_profile.target_body_height_px must be positive")
    if job.render.target_body_height_px != target:
        raise ConfigurationError(
            "IDLE_SCALE_PROFILE_MISMATCH: render.target_body_height_px "
            f"{job.render.target_body_height_px} != approved idle target {target}"
        )
    tolerance = float(value.get("tolerance_px", 1.0))
    if tolerance < 0:
        raise ConfigurationError("scale_profile.tolerance_px must be non-negative")
    return (
        f"Idle is the authoritative scale reference: normalize visible body anatomy to "
        f"{target}px with tolerance ±{tolerance:g}px and preserve the approved support anchor. "
        f"Exclude {exclusion_text} from measurement; those elements may extend beyond the body "
        "without making the character smaller or larger."
    )


def _minimal_render(template: str, context: Mapping[str, Any]) -> str:
    """Small offline fallback for templates containing only scalar substitutions."""

    result = template
    for key, value in context.items():
        result = result.replace("{{ " + key + " }}", str(value))
        result = result.replace("{{" + key + "}}", str(value))
    if "{{" in result or "{%" in result:
        raise RuntimeError("Install Jinja2 to render this prompt template")
    return result.strip() + "\n"
