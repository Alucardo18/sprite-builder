"""Dependency-light, versioned public configuration models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from sprite_builder.domain.errors import ConfigurationError

VALID_DIRECTIONS = frozenset(
    {"up", "down", "left", "right", "up_left", "up_right", "down_left", "down_right"}
)
VALID_LAYOUTS = frozenset({"individual", "horizontal", "grid", "godot"})
VALID_QUALITIES = frozenset({"low", "medium", "high", "auto"})
VALID_GENERATION_MODES = frozenset({"sheet"})
VALID_SHEET_LAYOUTS = frozenset({"horizontal", "vertical", "grid"})
VALID_BACKGROUND_MODES = frozenset({"chroma", "transparent_preferred", "transparent_required"})
VALID_BACKGROUND_FALLBACKS = frozenset(
    {"strict_chroma", "manual_ui", "manual_review", "reject"}
)
VALID_RESAMPLE_METHODS = frozenset(
    {"legacy", "premultiplied_area", "premultiplied_lanczos", "pixel_majority", "edge_aware"}
)


def _pair(value: Any, name: str) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigurationError(f"{name} must contain exactly two integers")
    result = (int(value[0]), int(value[1]))
    if min(result) <= 0:
        raise ConfigurationError(f"{name} values must be positive")
    return result


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{name} must be an object")
    return value


def _fraction_pair(value: Any, name: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigurationError(f"{name} must contain exactly two numbers")
    result = (float(value[0]), float(value[1]))
    if not 0 <= result[0] < result[1] <= 1:
        raise ConfigurationError(f"{name} must satisfy 0 <= left < right <= 1")
    return result


@dataclass(frozen=True, slots=True)
class CharacterSpec:
    id: str
    bible: Path
    references: tuple[Path, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CharacterSpec:
        character_id = str(data.get("id", "")).strip()
        if not character_id:
            raise ConfigurationError("character.id is required")
        references = tuple(Path(str(path)) for path in data.get("references", ()))
        return cls(
            id=character_id,
            bible=Path(str(data.get("bible", f"characters/{character_id}/bible.yaml"))),
            references=references,
        )


@dataclass(frozen=True, slots=True)
class AnimationSpec:
    name: str
    directions: tuple[str, ...]
    frame_count: int
    fps: float = 8.0
    loop: bool = True
    phases: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AnimationSpec:
        directions = tuple(str(item) for item in data.get("directions", ()))
        invalid = set(directions) - VALID_DIRECTIONS
        if not directions or invalid:
            raise ConfigurationError(f"animation.directions invalid: {sorted(invalid)}")
        frame_count = int(data.get("frame_count", 0))
        if frame_count < 1:
            raise ConfigurationError("animation.frame_count must be >= 1")
        phases = tuple(str(item) for item in data.get("phases", ()))
        if phases and len(phases) != frame_count:
            raise ConfigurationError("animation.phases must match frame_count")
        fps = float(data.get("fps", 8))
        if fps <= 0:
            raise ConfigurationError("animation.fps must be positive")
        name = str(data.get("name", "")).strip()
        if not name:
            raise ConfigurationError("animation.name is required")
        return cls(name, directions, frame_count, fps, bool(data.get("loop", True)), phases)


@dataclass(frozen=True, slots=True)
class PromptSpec:
    """Stable creative contract appended to every generated animation sheet."""

    style: str = (
        "16-bit pixel art for a top-down action RPG, authored at the requested source resolution; "
        "hard pixel clusters, crisp stepped silhouettes, no anti-aliasing, no vector smoothness, "
        "no painterly texture, no photorealism"
    )
    pixel_language: str = (
        "Use deliberate 1-pixel and 2-pixel clusters, readable dark outline hierarchy, controlled "
        "selective dithering only when it improves a material, and nearest-neighbor pixel logic"
    )
    camera: str = (
        "Keep one consistent orthographic top-down three-quarter camera, identical scale, crop, "
        "ground line, and facing convention in every cell"
    )
    palette: str = (
        "Use the locked Character Bible palette and material roles; preserve hue families for "
        "skin, "
        "cloth, hair, wood, metal, magic, and shadow instead of inventing new colors"
    )
    lighting: str = (
        "Keep one stable light direction and value hierarchy across the sheet; animate only the "
        "light changes explicitly required by the named phase"
    )
    identity: str = (
        "Treat the first approved reference as the identity anchor: same head shape, torso width, "
        "hair mass, clothing construction, equipment proportions, outline weight, and body scale"
    )
    animation: str = (
        "Change pose only between adjacent cells as required by the phase list; preserve anatomy, "
        "equipment ownership, contact points, and a stable support/ground row"
    )
    negative: str = (
        "No text, labels, numbers, watermark, UI, borders, panels, scenery, extra characters, "
        "duplicate limbs, missing feet, floating body, collage, contact sheet preview, perspective "
        "drift, frame captions, transparent checkerboard, or cropped body parts"
    )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PromptSpec:
        defaults = cls()
        values: dict[str, str] = {}
        for key in (
            "style",
            "pixel_language",
            "camera",
            "palette",
            "lighting",
            "identity",
            "animation",
            "negative",
        ):
            raw = data.get(key, getattr(defaults, key))
            value = str(raw).strip()
            if not value:
                raise ConfigurationError(f"generation.prompt.{key} must not be empty")
            values[key] = value
        return cls(**values)

    def to_dict(self) -> dict[str, str]:
        return {
            "style": self.style,
            "pixel_language": self.pixel_language,
            "camera": self.camera,
            "palette": self.palette,
            "lighting": self.lighting,
            "identity": self.identity,
            "animation": self.animation,
            "negative": self.negative,
        }


@dataclass(frozen=True, slots=True)
class SheetLayoutSpec:
    """Layout contract for the one native-resolution image returned by the model."""

    layout: str = "horizontal"
    rows: int = 0
    columns: int = 0
    gutter_px: int = 0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SheetLayoutSpec:
        layout = str(data.get("layout", "horizontal"))
        if layout not in VALID_SHEET_LAYOUTS:
            raise ConfigurationError(
                f"generation.sheet.layout must be one of {sorted(VALID_SHEET_LAYOUTS)}"
            )
        rows = int(data.get("rows", 0))
        columns = int(data.get("columns", 0))
        gutter = int(data.get("gutter_px", 0))
        if rows < 0 or columns < 0:
            raise ConfigurationError("generation.sheet.rows/columns must be non-negative")
        if gutter < 0:
            raise ConfigurationError("generation.sheet.gutter_px must be non-negative")
        return cls(layout=layout, rows=rows, columns=columns, gutter_px=gutter)

    def resolve(self, frame_count: int) -> tuple[int, int]:
        if frame_count < 1:
            raise ConfigurationError("generation.sheet requires at least one frame")
        if self.layout == "horizontal":
            rows, columns = 1, self.columns or frame_count
        elif self.layout == "vertical":
            rows, columns = self.rows or frame_count, 1
        else:
            columns = self.columns or max(1, int(frame_count**0.5))
            if not self.columns:
                while columns * columns < frame_count:
                    columns += 1
            rows = self.rows or (frame_count + columns - 1) // columns
        if rows * columns < frame_count:
            raise ConfigurationError(
                "generation.sheet rows*columns must cover animation.frame_count"
            )
        return rows, columns

    def to_dict(self) -> dict[str, int | str]:
        return {
            "layout": self.layout,
            "rows": self.rows,
            "columns": self.columns,
            "gutter_px": self.gutter_px,
        }


@dataclass(frozen=True, slots=True)
class GenerationSpec:
    source_size: tuple[int, int] = (1024, 1024)
    quality: str = "medium"
    mode: str = "sheet"
    candidates_per_sheet: int = 1
    sheet: SheetLayoutSpec = field(default_factory=SheetLayoutSpec)
    prompt: PromptSpec = field(default_factory=PromptSpec)
    background_color: str = "#00FF00"
    background_mode: str = "chroma"
    background_fallback: str = "strict_chroma"
    max_alpha_retries: int = 2

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GenerationSpec:
        quality = str(data.get("quality", data.get("final_quality", "medium")))
        if quality not in VALID_QUALITIES:
            raise ConfigurationError(f"generation.quality must be one of {sorted(VALID_QUALITIES)}")
        generation_mode = str(data.get("mode", "sheet"))
        if generation_mode not in VALID_GENERATION_MODES:
            raise ConfigurationError(
                "Only generation.mode=sheet is supported; frame_sequence has been removed"
            )
        removed_fields = {
            "candidates_per_frame": "use candidates_per_sheet",
            "use_previous_accepted_frame": "the complete sheet prompt",
            "seed": "character.references with a full-sheet reference",
        }
        for removed_field, replacement in removed_fields.items():
            if removed_field in data:
                raise ConfigurationError(
                    f"generation.{removed_field} is no longer supported; use {replacement}"
                )
        candidates_per_sheet_value = data.get("candidates_per_sheet")
        candidates_per_sheet = int(
            candidates_per_sheet_value if candidates_per_sheet_value is not None else 1
        )
        if not 1 <= candidates_per_sheet <= 8:
            raise ConfigurationError("generation.candidates_per_sheet must be between 1 and 8")
        sheet_data = data.get("sheet", {})
        sheet_data = sheet_data if isinstance(sheet_data, Mapping) else {}
        sheet = SheetLayoutSpec.from_dict(sheet_data)
        prompt_data = data.get("prompt", {})
        prompt = PromptSpec.from_dict(
            prompt_data if isinstance(prompt_data, Mapping) else {}
        )
        background = data.get("background", {})
        color = (
            str(background.get("color", "#00FF00"))
            if isinstance(background, Mapping)
            else "#00FF00"
        )
        if len(color) != 7 or not color.startswith("#"):
            raise ConfigurationError("generation.background_color must be #RRGGBB")
        mode = (
            str(background.get("mode", "chroma"))
            if isinstance(background, Mapping)
            else "chroma"
        )
        fallback = (
            str(
                background.get(
                    "fallback",
                    "strict_chroma" if mode == "chroma" else "manual_ui",
                )
            )
            if isinstance(background, Mapping)
            else "strict_chroma"
        )
        if mode not in VALID_BACKGROUND_MODES:
            raise ConfigurationError(
                f"generation.background.mode must be one of {sorted(VALID_BACKGROUND_MODES)}"
            )
        if fallback not in VALID_BACKGROUND_FALLBACKS:
            raise ConfigurationError(
                "generation.background.fallback must be one of "
                f"{sorted(VALID_BACKGROUND_FALLBACKS)}"
            )
        max_attempts_value = (
            background.get("max_attempts") if isinstance(background, Mapping) else None
        )
        legacy_retries_value = (
            background.get("max_alpha_retries") if isinstance(background, Mapping) else None
        )
        if max_attempts_value is not None:
            max_attempts = int(max_attempts_value)
            if not 1 <= max_attempts <= 3:
                raise ConfigurationError("generation.background.max_attempts must be 1..3")
            max_alpha_retries = max_attempts - 1
            if (
                legacy_retries_value is not None
                and int(legacy_retries_value) != max_alpha_retries
            ):
                raise ConfigurationError(
                    "generation.background.max_attempts conflicts with max_alpha_retries"
                )
        else:
            max_alpha_retries = (
                int(legacy_retries_value) if legacy_retries_value is not None else 2
            )
        if not 0 <= max_alpha_retries <= 2:
            raise ConfigurationError("generation.background.max_alpha_retries must be 0..2")
        return cls(
            source_size=_pair(
                data.get("source_size", data.get("size", (1024, 1024))), "source_size"
            ),
            quality=quality,
            mode=generation_mode,
            candidates_per_sheet=candidates_per_sheet,
            sheet=sheet,
            prompt=prompt,
            background_color=color.upper(),
            background_mode=mode,
            background_fallback=fallback,
            max_alpha_retries=max_alpha_retries,
        )

    @property
    def is_sheet(self) -> bool:
        return self.mode == "sheet"

    def resolved_sheet_grid(self, frame_count: int) -> tuple[int, int]:
        return self.sheet.resolve(frame_count)


@dataclass(frozen=True, slots=True)
class RenderSpec:
    cell_size: tuple[int, int]
    target_body_height_px: int
    palette_lock: bool = True
    dithering: bool = False
    integrated_shadow: bool = True
    resample_methods: tuple[str, ...] = ("legacy",)
    resample_selection: str = "auto"
    save_resize_variants: bool = False
    palette_max_delta_e00: float | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RenderSpec:
        cell_size = _pair(data.get("cell_size", (128, 128)), "render.cell_size")
        height = int(data.get("target_body_height_px", 0))
        if not 1 <= height <= cell_size[1]:
            raise ConfigurationError("target_body_height_px must fit inside cell height")
        resampling = data.get("resampling", {})
        resampling = resampling if isinstance(resampling, Mapping) else {}
        methods = tuple(str(item) for item in resampling.get("methods", ("legacy",)))
        invalid_methods = set(methods) - VALID_RESAMPLE_METHODS
        if not methods or invalid_methods:
            raise ConfigurationError(
                f"render.resampling.methods invalid: {sorted(invalid_methods)}"
            )
        selection = str(resampling.get("selection", "auto"))
        if selection != "auto" and selection not in methods:
            raise ConfigurationError(
                "render.resampling.selection must be auto or a configured method"
            )
        palette_max = data.get("palette_max_delta_e00")
        palette_max = float(palette_max) if palette_max is not None else None
        if palette_max is not None and palette_max <= 0:
            raise ConfigurationError("render.palette_max_delta_e00 must be positive")
        return cls(
            cell_size,
            height,
            bool(data.get("palette_lock", True)),
            bool(data.get("dithering", False)),
            bool(data.get("integrated_shadow", True)),
            methods,
            selection,
            bool(resampling.get("save_variants", False)),
            palette_max,
        )


@dataclass(frozen=True, slots=True)
class AlignmentSpec:
    method: str
    canonical_canvas_anchor: tuple[int, int]
    confidence_review_threshold: float = 0.65
    allow_manual_override: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AlignmentSpec:
        threshold = float(data.get("confidence_review_threshold", 0.65))
        if not 0 <= threshold <= 1:
            raise ConfigurationError("alignment confidence threshold must be between 0 and 1")
        return cls(
            str(data.get("method", "torso_hybrid_v1")),
            _pair(data.get("canonical_canvas_anchor", (64, 68)), "canonical_canvas_anchor"),
            threshold,
            bool(data.get("allow_manual_override", True)),
        )


@dataclass(frozen=True, slots=True)
class SemanticIntegritySpec:
    """Opt-in geometry gates for complete, grounded character silhouettes."""

    enabled: bool = False
    alpha_threshold: int = 8
    body_roi_x: tuple[float, float] = (0.18, 0.82)
    min_bottom_gutter_px: int = 1
    support_band_height_px: int = 4
    required_support_components: int = 1
    max_support_y_jitter_px: float = 1.0
    max_terminal_taper_ratio: float = 0.80
    runtime_preview_scales: tuple[float, ...] = (1.0, 0.5)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SemanticIntegritySpec:
        alpha_threshold = int(data.get("alpha_threshold", 8))
        if not 0 <= alpha_threshold <= 254:
            raise ConfigurationError("quality_gates.semantic_integrity.alpha_threshold invalid")
        min_gutter = int(data.get("min_bottom_gutter_px", 1))
        band_height = int(data.get("support_band_height_px", 4))
        component_count = int(data.get("required_support_components", 1))
        jitter = float(data.get("max_support_y_jitter_px", 1.0))
        taper = float(data.get("max_terminal_taper_ratio", 0.80))
        scales = tuple(float(item) for item in data.get("runtime_preview_scales", (1.0, 0.5)))
        if min_gutter < 0:
            raise ConfigurationError("min_bottom_gutter_px must be non-negative")
        if band_height < 2:
            raise ConfigurationError("support_band_height_px must be >= 2")
        if component_count < 1:
            raise ConfigurationError("required_support_components must be >= 1")
        if jitter < 0:
            raise ConfigurationError("max_support_y_jitter_px must be non-negative")
        if not 0 < taper <= 1:
            raise ConfigurationError("max_terminal_taper_ratio must be in (0, 1]")
        if not scales or any(scale <= 0 for scale in scales):
            raise ConfigurationError("runtime_preview_scales must contain positive values")
        return cls(
            enabled=bool(data.get("enabled", False)),
            alpha_threshold=alpha_threshold,
            body_roi_x=_fraction_pair(data.get("body_roi_x", (0.18, 0.82)), "body_roi_x"),
            min_bottom_gutter_px=min_gutter,
            support_band_height_px=band_height,
            required_support_components=component_count,
            max_support_y_jitter_px=jitter,
            max_terminal_taper_ratio=taper,
            runtime_preview_scales=scales,
        )


@dataclass(frozen=True, slots=True)
class AlphaIntegritySpec:
    """Thresholds for accepting native or fallback-produced transparency."""

    min_transparent_ratio: float = 0.05
    min_border_transparent_ratio: float = 0.98
    max_foreground_border_ratio: float = 0.01
    alpha_threshold: int = 8

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AlphaIntegritySpec:
        transparent = float(data.get("min_transparent_ratio", 0.05))
        border = float(data.get("min_border_transparent_ratio", 0.98))
        spill = float(data.get("max_foreground_border_ratio", 0.01))
        threshold = int(data.get("alpha_threshold", 8))
        if not 0 <= transparent < 1:
            raise ConfigurationError("alpha_integrity.min_transparent_ratio invalid")
        if not 0 <= border <= 1:
            raise ConfigurationError("alpha_integrity.min_border_transparent_ratio invalid")
        if not 0 <= spill <= 1:
            raise ConfigurationError("alpha_integrity.max_foreground_border_ratio invalid")
        if not 0 <= threshold <= 254:
            raise ConfigurationError("alpha_integrity.alpha_threshold invalid")
        return cls(transparent, border, spill, threshold)


@dataclass(frozen=True, slots=True)
class QualityGatesSpec:
    semantic_integrity: SemanticIntegritySpec = field(default_factory=SemanticIntegritySpec)
    alpha_integrity: AlphaIntegritySpec = field(default_factory=AlphaIntegritySpec)
    block_export_on_review: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> QualityGatesSpec:
        semantic = data.get("semantic_integrity", {})
        alpha = data.get("alpha_integrity", {})
        return cls(
            semantic_integrity=SemanticIntegritySpec.from_dict(
                _mapping(semantic, "quality_gates.semantic_integrity")
            ),
            alpha_integrity=AlphaIntegritySpec.from_dict(
                _mapping(alpha, "quality_gates.alpha_integrity")
            ),
            block_export_on_review=bool(data.get("block_export_on_review", True)),
        )


@dataclass(frozen=True, slots=True)
class ExportSpec:
    formats: tuple[str, ...]
    output_dir: Path
    godot_project_root: Path | None = None
    godot_resource_dir: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExportSpec:
        formats = tuple(str(item) for item in data.get("formats", ("individual",)))
        invalid = set(formats) - VALID_LAYOUTS
        if not formats or invalid:
            raise ConfigurationError(f"export.formats invalid: {sorted(invalid)}")
        godot = data.get("godot", {})
        godot = godot if isinstance(godot, Mapping) else {}
        root = godot.get("project_root")
        resource_dir = godot.get("resource_dir")
        if "godot" in formats and (not root or not str(resource_dir).startswith("res://")):
            raise ConfigurationError("Godot export requires project_root and a res:// resource_dir")
        return cls(
            formats,
            Path(str(data.get("output_dir", "exports"))),
            Path(str(root)) if root else None,
            str(resource_dir) if resource_dir else None,
        )


@dataclass(frozen=True, slots=True)
class JobSpec:
    """Complete, versioned input contract for one sprite-production job."""

    CURRENT_SCHEMA_VERSION: ClassVar[str] = "1.0"

    schema_version: str
    job_id: str
    character: CharacterSpec
    animation: AnimationSpec
    generation: GenerationSpec
    render: RenderSpec
    alignment: AlignmentSpec
    export: ExportSpec
    quality_gates: QualityGatesSpec = field(default_factory=QualityGatesSpec)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JobSpec:
        version = str(data.get("schema_version", ""))
        if version != cls.CURRENT_SCHEMA_VERSION:
            raise ConfigurationError(
                f"Unsupported schema_version {version!r}; expected {cls.CURRENT_SCHEMA_VERSION}"
            )
        job_data = _mapping(data.get("job", {}), "job")
        job_id = str(job_data.get("id", "")).strip()
        if not job_id:
            raise ConfigurationError("job.id is required")
        return cls(
            schema_version=version,
            job_id=job_id,
            character=CharacterSpec.from_dict(_mapping(data.get("character", {}), "character")),
            animation=AnimationSpec.from_dict(_mapping(data.get("animation", {}), "animation")),
            generation=GenerationSpec.from_dict(_mapping(data.get("generation", {}), "generation")),
            render=RenderSpec.from_dict(_mapping(data.get("render", {}), "render")),
            alignment=AlignmentSpec.from_dict(_mapping(data.get("alignment", {}), "alignment")),
            export=ExportSpec.from_dict(_mapping(data.get("export", {}), "export")),
            quality_gates=QualityGatesSpec.from_dict(
                _mapping(data.get("quality_gates", {}), "quality_gates")
            ),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        godot: dict[str, str] = {}
        if self.export.godot_project_root:
            godot["project_root"] = str(self.export.godot_project_root)
        if self.export.godot_resource_dir:
            godot["resource_dir"] = self.export.godot_resource_dir
        return {
            "schema_version": self.schema_version,
            "job": {"id": self.job_id},
            "character": {
                "id": self.character.id,
                "bible": str(self.character.bible),
                "references": [str(path) for path in self.character.references],
            },
            "animation": {
                "name": self.animation.name,
                "directions": list(self.animation.directions),
                "frame_count": self.animation.frame_count,
                "fps": self.animation.fps,
                "loop": self.animation.loop,
                "phases": list(self.animation.phases),
            },
            "generation": {
                "source_size": list(self.generation.source_size),
                "quality": self.generation.quality,
                "mode": self.generation.mode,
                "candidates_per_sheet": self.generation.candidates_per_sheet,
                "sheet": self.generation.sheet.to_dict(),
                "prompt": self.generation.prompt.to_dict(),
                "background": {
                    "color": self.generation.background_color,
                    "mode": self.generation.background_mode,
                    "fallback": self.generation.background_fallback,
                    "max_attempts": self.generation.max_alpha_retries + 1,
                    "max_alpha_retries": self.generation.max_alpha_retries,
                },
            },
            "render": {
                "cell_size": list(self.render.cell_size),
                "target_body_height_px": self.render.target_body_height_px,
                "palette_lock": self.render.palette_lock,
                "dithering": self.render.dithering,
                "integrated_shadow": self.render.integrated_shadow,
                "resampling": {
                    "methods": list(self.render.resample_methods),
                    "selection": self.render.resample_selection,
                    "save_variants": self.render.save_resize_variants,
                },
                "palette_max_delta_e00": self.render.palette_max_delta_e00,
            },
            "alignment": {
                "method": self.alignment.method,
                "canonical_canvas_anchor": list(self.alignment.canonical_canvas_anchor),
                "confidence_review_threshold": self.alignment.confidence_review_threshold,
                "allow_manual_override": self.alignment.allow_manual_override,
            },
            "export": {
                "formats": list(self.export.formats),
                "output_dir": str(self.export.output_dir),
                **({"godot": godot} if godot else {}),
            },
            "quality_gates": {
                "block_export_on_review": self.quality_gates.block_export_on_review,
                "alpha_integrity": {
                    "min_transparent_ratio": (
                        self.quality_gates.alpha_integrity.min_transparent_ratio
                    ),
                    "min_border_transparent_ratio": (
                        self.quality_gates.alpha_integrity.min_border_transparent_ratio
                    ),
                    "max_foreground_border_ratio": (
                        self.quality_gates.alpha_integrity.max_foreground_border_ratio
                    ),
                    "alpha_threshold": self.quality_gates.alpha_integrity.alpha_threshold,
                },
                "semantic_integrity": {
                    "enabled": self.quality_gates.semantic_integrity.enabled,
                    "alpha_threshold": self.quality_gates.semantic_integrity.alpha_threshold,
                    "body_roi_x": list(self.quality_gates.semantic_integrity.body_roi_x),
                    "min_bottom_gutter_px": (
                        self.quality_gates.semantic_integrity.min_bottom_gutter_px
                    ),
                    "support_band_height_px": (
                        self.quality_gates.semantic_integrity.support_band_height_px
                    ),
                    "required_support_components": (
                        self.quality_gates.semantic_integrity.required_support_components
                    ),
                    "max_support_y_jitter_px": (
                        self.quality_gates.semantic_integrity.max_support_y_jitter_px
                    ),
                    "max_terminal_taper_ratio": (
                        self.quality_gates.semantic_integrity.max_terminal_taper_ratio
                    ),
                    "runtime_preview_scales": list(
                        self.quality_gates.semantic_integrity.runtime_preview_scales
                    ),
                },
            },
            "metadata": dict(self.metadata),
        }
