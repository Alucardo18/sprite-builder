"""Versioned models for local sprite-sheet processing sessions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

Orientation = Literal["horizontal", "vertical", "grid"]
CenterMethod = Literal["body", "bounding_box"]
StageStatus = Literal["pending", "passed", "manual_review", "failed"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _pair(value: object, default: tuple[int, int]) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return default
    return int(value[0]), int(value[1])


@dataclass(frozen=True, slots=True)
class SheetInspection:
    width: int
    height: int
    mode: str
    has_alpha: bool
    uses_transparency: bool
    top_left_rgb: tuple[int, int, int]
    border_rgb: tuple[int, int, int]
    solid_background_likely: bool
    background_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SegmentationConfig:
    frame_count: int = 1
    orientation: Orientation = "horizontal"
    rows: int = 1
    columns: int = 1
    cell_width: int | None = None
    cell_height: int | None = None
    offset_x: int = 0
    offset_y: int = 0
    spacing_x: int = 0
    spacing_y: int = 0
    manual_cut_positions: tuple[int, ...] = ()
    manual_cut_positions_x: tuple[int, ...] = ()
    manual_cut_positions_y: tuple[int, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SegmentationConfig:
        width = value.get("cell_width")
        height = value.get("cell_height")
        raw_cuts = value.get("manual_cut_positions", ())
        raw_cuts_x = value.get("manual_cut_positions_x", ())
        raw_cuts_y = value.get("manual_cut_positions_y", ())
        if isinstance(raw_cuts, (list, tuple)):
            manual_cut_positions = tuple(int(item) for item in raw_cuts)
        else:
            manual_cut_positions = ()
        if isinstance(raw_cuts_x, (list, tuple)):
            manual_cut_positions_x = tuple(int(item) for item in raw_cuts_x)
        else:
            manual_cut_positions_x = ()
        if isinstance(raw_cuts_y, (list, tuple)):
            manual_cut_positions_y = tuple(int(item) for item in raw_cuts_y)
        else:
            manual_cut_positions_y = ()
        return cls(
            frame_count=int(value.get("frame_count", 1)),
            orientation=str(value.get("orientation", "horizontal")),  # type: ignore[arg-type]
            rows=int(value.get("rows", 1)),
            columns=int(value.get("columns", 1)),
            cell_width=int(width) if width is not None else None,
            cell_height=int(height) if height is not None else None,
            offset_x=int(value.get("offset_x", 0)),
            offset_y=int(value.get("offset_y", 0)),
            spacing_x=int(value.get("spacing_x", 0)),
            spacing_y=int(value.get("spacing_y", 0)),
            manual_cut_positions=manual_cut_positions,
            manual_cut_positions_x=manual_cut_positions_x,
            manual_cut_positions_y=manual_cut_positions_y,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BackgroundRemovalConfig:
    mode: Literal["chroma"] = "chroma"
    color: tuple[int, int, int] = (0, 255, 0)
    tolerance: float = 24.0
    color_space: Literal["rgb", "lab"] = "rgb"
    border_connected_only: bool = True
    cleanup_enabled: bool = True
    fringe_cleanup_strength: int = 1
    remove_near_transparent: bool = True
    near_transparent_threshold: int = 8
    preserve_outline: bool = True

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BackgroundRemovalConfig:
        color = value.get("color")
        if not isinstance(color, (list, tuple)) or len(color) != 3:
            color = (0, 255, 0)
        return cls(
            mode="chroma",
            color=(int(color[0]), int(color[1]), int(color[2])),
            tolerance=float(value.get("tolerance", 24.0)),
            color_space=str(value.get("color_space", "rgb")),  # type: ignore[arg-type]
            border_connected_only=bool(value.get("border_connected_only", True)),
            cleanup_enabled=bool(value.get("cleanup_enabled", True)),
            fringe_cleanup_strength=int(value.get("fringe_cleanup_strength", 1)),
            remove_near_transparent=bool(value.get("remove_near_transparent", True)),
            near_transparent_threshold=int(value.get("near_transparent_threshold", 8)),
            preserve_outline=bool(value.get("preserve_outline", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["color"] = list(self.color)
        return value


@dataclass(frozen=True, slots=True)
class ExportCropConfig:
    enabled: bool = False
    padding: int = 0
    alpha_threshold: int = 8

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ExportCropConfig:
        return cls(
            enabled=bool(value.get("enabled", False)),
            padding=int(value.get("padding", 0)),
            alpha_threshold=int(value.get("alpha_threshold", 8)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AutoCenterConfig:
    method: CenterMethod = "body"
    canvas_width: int = 128
    canvas_height: int = 128
    canonical_anchor: tuple[int, int] = (64, 68)
    confidence_threshold: float = 0.65
    ignore_outliers: bool = True
    anchor_strategy: str = "distance_core_percentiles"

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AutoCenterConfig:
        return cls(
            method=str(value.get("method", "body")),  # type: ignore[arg-type]
            canvas_width=int(value.get("canvas_width", 128)),
            canvas_height=int(value.get("canvas_height", 128)),
            canonical_anchor=_pair(value.get("canonical_anchor"), (64, 68)),
            confidence_threshold=float(value.get("confidence_threshold", 0.65)),
            ignore_outliers=bool(value.get("ignore_outliers", True)),
            anchor_strategy=str(value.get("anchor_strategy", "distance_core_percentiles")),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["canonical_anchor"] = list(self.canonical_anchor)
        return value


@dataclass(frozen=True, slots=True)
class FrameAdjustment:
    frame_index: int
    auto_anchor: tuple[float, float] = (0.0, 0.0)
    auto_confidence: float = 0.0
    manual_offset_x: int = 0
    manual_offset_y: int = 0
    final_anchor: tuple[float, float] = (0.0, 0.0)
    applied_translation: tuple[int, int] = (0, 0)
    body_bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    locked: bool = False
    notes: str = ""
    manual_review: bool = False

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FrameAdjustment:
        bbox = value.get("body_bbox", (0, 0, 0, 0))
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            bbox = (0, 0, 0, 0)
        auto = value.get("auto_anchor", (0, 0))
        final = value.get("final_anchor", (0, 0))
        translation = value.get("applied_translation", (0, 0))
        return cls(
            frame_index=int(value["frame_index"]),
            auto_anchor=tuple(map(float, auto)),  # type: ignore[arg-type]
            auto_confidence=float(value.get("auto_confidence", 0)),
            manual_offset_x=int(value.get("manual_offset_x", 0)),
            manual_offset_y=int(value.get("manual_offset_y", 0)),
            final_anchor=tuple(map(float, final)),  # type: ignore[arg-type]
            applied_translation=tuple(map(int, translation)),  # type: ignore[arg-type]
            body_bbox=tuple(map(int, bbox)),  # type: ignore[arg-type]
            locked=bool(value.get("locked", False)),
            notes=str(value.get("notes", "")),
            manual_review=bool(value.get("manual_review", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("auto_anchor", "final_anchor", "applied_translation", "body_bbox"):
            value[key] = list(value[key])
        return value


@dataclass(slots=True)
class SheetProcessingSession:
    schema_version: str
    session_id: str
    source_image_path: str
    source_sha256: str
    created_at: str
    updated_at: str
    current_stage: str
    output_dir: str
    inspection: SheetInspection
    segmentation_config: SegmentationConfig
    background_removal_config: BackgroundRemovalConfig
    export_crop_config: ExportCropConfig
    auto_center_config: AutoCenterConfig
    frame_adjustments: list[FrameAdjustment] = field(default_factory=list)
    layer_document: dict[str, Any] | None = None
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    export_manifest: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SheetProcessingSession:
        raw_inspection = value.get("inspection", {})
        if not isinstance(raw_inspection, Mapping):
            raise ValueError("Session inspection must be an object")
        inspection = SheetInspection(
            width=int(raw_inspection["width"]),
            height=int(raw_inspection["height"]),
            mode=str(raw_inspection["mode"]),
            has_alpha=bool(raw_inspection["has_alpha"]),
            uses_transparency=bool(raw_inspection["uses_transparency"]),
            top_left_rgb=tuple(map(int, raw_inspection["top_left_rgb"])),  # type: ignore[arg-type]
            border_rgb=tuple(map(int, raw_inspection["border_rgb"])),  # type: ignore[arg-type]
            solid_background_likely=bool(raw_inspection["solid_background_likely"]),
            background_confidence=float(raw_inspection["background_confidence"]),
        )
        adjustments = value.get("frame_adjustments", ())
        return cls(
            schema_version=str(value.get("schema_version", "1.0")),
            session_id=str(value["session_id"]),
            source_image_path=str(value["source_image_path"]),
            source_sha256=str(value["source_sha256"]),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
            current_stage=str(value.get("current_stage", "source")),
            output_dir=str(value["output_dir"]),
            inspection=inspection,
            segmentation_config=SegmentationConfig.from_dict(
                value.get("segmentation_config", {})
            ),
            background_removal_config=BackgroundRemovalConfig.from_dict(
                value.get("background_removal_config", {})
            ),
            export_crop_config=ExportCropConfig.from_dict(
                value.get("export_crop_config", {})
            ),
            auto_center_config=AutoCenterConfig.from_dict(
                value.get("auto_center_config", {})
            ),
            frame_adjustments=[
                FrameAdjustment.from_dict(item)
                for item in adjustments
            ],
            layer_document=(
                dict(value["layer_document"])
                if isinstance(value.get("layer_document"), Mapping)
                else None
            ),
            stages=dict(value.get("stages", {})),
            export_manifest=(
                dict(value["export_manifest"])
                if value.get("export_manifest")
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "source_image_path": self.source_image_path,
            "source_sha256": self.source_sha256,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_stage": self.current_stage,
            "output_dir": self.output_dir,
            "inspection": self.inspection.to_dict(),
            "segmentation_config": self.segmentation_config.to_dict(),
            "background_removal_config": self.background_removal_config.to_dict(),
            "export_crop_config": self.export_crop_config.to_dict(),
            "auto_center_config": self.auto_center_config.to_dict(),
            "frame_adjustments": [item.to_dict() for item in self.frame_adjustments],
            "layer_document": self.layer_document,
            "stages": self.stages,
            "export_manifest": self.export_manifest,
        }

    @property
    def directory(self) -> Path:
        return Path(self.output_dir)
