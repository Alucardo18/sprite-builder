"""Immutable artifact storage for local sprite-sheet editing sessions."""

from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from sprite_builder.domain.errors import ArtifactIntegrityError
from sprite_builder.orchestration import (
    ArtifactRecord,
    atomic_write_json,
    sha256_file,
    stable_digest,
)
from sprite_builder.sheets.engine import export_sheet, render_contact_sheet
from sprite_builder.sheets.engine import trim_transparent_frames
from sprite_builder.sheets.inspect import inspect_sheet
from sprite_builder.sheets.models import (
    AutoCenterConfig,
    BackgroundRemovalConfig,
    ExportCropConfig,
    FrameAdjustment,
    SegmentationConfig,
    SheetProcessingSession,
    utc_now,
)


def _atomic_save_png(image: Image.Image, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".png",
        dir=destination.parent,
    )
    os.close(fd)
    try:
        image.convert("RGBA").save(temporary, format="PNG", optimize=False)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def _source_bytes(source: str | Path | bytes) -> bytes:
    return source if isinstance(source, bytes) else Path(source).read_bytes()


class SheetSessionStore:
    """Create, resume, and version processing sessions under ``sheet_sessions``."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.root = self.workspace / "sheet_sessions"
        self.root.mkdir(parents=True, exist_ok=True)

    def list_sessions(self) -> tuple[str, ...]:
        return tuple(
            path.parent.name
            for path in sorted(self.root.glob("*/session.json"), reverse=True)
        )

    def session_path(self, session_id: str) -> Path:
        return self.root / session_id / "session.json"

    def create(
        self,
        source: str | Path | bytes,
        *,
        source_name: str = "uploaded.png",
    ) -> SheetProcessingSession:
        data = _source_bytes(source)
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG":
                    raise ValueError("Sheet source must be a PNG")
                rgba = image.convert("RGBA")
                inspection = inspect_sheet(image)
        except OSError as exc:
            raise ValueError("Sheet source must be a readable PNG") from exc

        digest = __import__("hashlib").sha256(data).hexdigest()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        session_id = f"sheet-{stamp}-{digest[:8]}-{uuid.uuid4().hex[:4]}"
        directory = self.root / session_id
        source_path = directory / "source" / f"{digest}.png"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.exists():
            if sha256_file(source_path) != digest:
                raise ArtifactIntegrityError(f"Source collision: {source_path}")
        else:
            fd, temporary = tempfile.mkstemp(
                prefix=f".{source_name}.",
                suffix=".png",
                dir=source_path.parent,
            )
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, source_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        if sha256_file(source_path) != digest:
            raise ArtifactIntegrityError("Stored source SHA-256 does not match upload")

        now = utc_now()
        segmentation = SegmentationConfig(
            frame_count=1,
            orientation="horizontal",
            rows=1,
            columns=1,
            cell_width=None,
            cell_height=None,
        )
        background = BackgroundRemovalConfig(color=inspection.border_rgb)
        export_crop = ExportCropConfig()
        auto_center = AutoCenterConfig(
            canvas_width=rgba.width,
            canvas_height=rgba.height,
            canonical_anchor=(rgba.width // 2, rgba.height // 2),
        )
        session = SheetProcessingSession(
            schema_version="1.0",
            session_id=session_id,
            source_image_path=str(source_path.relative_to(self.workspace)),
            source_sha256=digest,
            created_at=now,
            updated_at=now,
            current_stage="source",
            output_dir=str(directory.relative_to(self.workspace)),
            inspection=inspection,
            segmentation_config=segmentation,
            background_removal_config=background,
            export_crop_config=export_crop,
            auto_center_config=auto_center,
            stages={
                "source": {
                    "status": "passed",
                    "path": str(source_path.relative_to(self.workspace)),
                    "sha256": digest,
                }
            },
        )
        self.save(session)
        return session

    def load(self, session_id: str) -> SheetProcessingSession:
        path = self.session_path(session_id)
        if not path.is_file():
            raise FileNotFoundError(path)
        session = SheetProcessingSession.from_dict(
            json.loads(path.read_text(encoding="utf-8"))
        )
        source = self.workspace / session.source_image_path
        if not source.is_file() or sha256_file(source) != session.source_sha256:
            raise ArtifactIntegrityError(
                f"Session source failed SHA-256 verification: {source}"
            )
        return session

    def save(self, session: SheetProcessingSession) -> Path:
        session.updated_at = utc_now()
        return atomic_write_json(self.session_path(session.session_id), session.to_dict())

    def source_path(self, session: SheetProcessingSession) -> Path:
        source = self.workspace / session.source_image_path
        if sha256_file(source) != session.source_sha256:
            raise ArtifactIntegrityError(f"Invalid session source: {source}")
        return source

    @staticmethod
    def _invalidate_downstream(
        session: SheetProcessingSession,
        stage: str,
    ) -> None:
        downstream = {
            "source": ("background", "segmentation", "alignment", "export"),
            "background": ("segmentation", "alignment", "export"),
            "segmentation": ("alignment", "export"),
            "alignment": ("export",),
            "export": (),
        }
        invalidated = downstream.get(stage, ())
        for name in invalidated:
            session.stages.pop(name, None)
        if "export" in invalidated:
            session.export_manifest = None

    def commit_stage(
        self,
        session: SheetProcessingSession,
        stage: str,
        images: Sequence[Image.Image],
        *,
        config: Mapping[str, Any],
        status: str = "passed",
        metrics: Mapping[str, float] | None = None,
        warnings: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[Path, ...]:
        if status not in {"passed", "manual_review", "failed"}:
            raise ValueError(f"Invalid stage status: {status}")
        if not images:
            raise ValueError("A stage must publish at least one output image")
        cache_key = stable_digest(
            {
                "session_id": session.session_id,
                "source_sha256": session.source_sha256,
                "stage": stage,
                "config": config,
                "metadata": metadata or {},
            }
        )
        directory = self.workspace / session.output_dir / "attempts" / stage / cache_key
        manifest_path = directory / "manifest.json"
        previous_key = session.stages.get(stage, {}).get("cache_key")
        changed = previous_key != cache_key
        if manifest_path.exists():
            cached_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached_outputs = tuple(
                self.workspace / item["path"] for item in cached_manifest["outputs"]
            )
            if all(
                path.is_file()
                and path.stat().st_size == item["size_bytes"]
                and sha256_file(path) == item["sha256"]
                for path, item in zip(
                    cached_outputs,
                    cached_manifest["outputs"],
                    strict=True,
                )
            ):
                if changed:
                    self._invalidate_downstream(session, stage)
                pointer = (
                    self.workspace
                    / session.output_dir
                    / "manifests"
                    / f"{stage}.json"
                )
                atomic_write_json(pointer, cached_manifest)
                session.stages[stage] = {
                    "status": status,
                    "cache_key": cache_key,
                    "manifest": str(manifest_path.relative_to(self.workspace)),
                    "outputs": [
                        str(path.relative_to(self.workspace))
                        for path in cached_outputs
                    ],
                }
                session.current_stage = stage
                self.save(session)
                return cached_outputs
            raise ArtifactIntegrityError(f"Cached stage is corrupt: {manifest_path}")

        published_outputs: list[Path] = []
        for index, image in enumerate(images):
            output = directory / f"frame_{index:03d}.png"
            if output.exists():
                raise FileExistsError(f"Refusing to overwrite stage output: {output}")
            _atomic_save_png(image, output)
            published_outputs.append(output)

        output_records = [
            asdict(
                ArtifactRecord.from_path(
                    path,
                    root=self.workspace,
                    media_type="image/png",
                )
            )
            for path in published_outputs
        ]
        stage_manifest: dict[str, Any] = {
            "schema_version": "1.0",
            "session_id": session.session_id,
            "stage": stage,
            "status": status,
            "cache_key": cache_key,
            "inputs": [
                {
                    "path": session.source_image_path,
                    "sha256": session.source_sha256,
                    "size_bytes": (self.workspace / session.source_image_path).stat().st_size,
                    "media_type": "image/png",
                    "role": "source",
                }
            ],
            "outputs": output_records,
            "config": dict(config),
            "metrics": dict(metrics or {}),
            "warnings": list(warnings),
            "metadata": dict(metadata or {}),
            "created_at": utc_now(),
        }
        # Publish the immutable attempt only after every output exists.
        atomic_write_json(manifest_path, stage_manifest)
        pointer = self.workspace / session.output_dir / "manifests" / f"{stage}.json"
        atomic_write_json(pointer, stage_manifest)
        if changed:
            self._invalidate_downstream(session, stage)
        session.stages[stage] = {
            "status": status,
            "cache_key": cache_key,
            "manifest": str(manifest_path.relative_to(self.workspace)),
            "outputs": [
                str(path.relative_to(self.workspace)) for path in published_outputs
            ],
        }
        session.current_stage = stage
        self.save(session)
        return tuple(published_outputs)

    def stage_paths(
        self,
        session: SheetProcessingSession,
        stage: str,
    ) -> tuple[Path, ...]:
        stage_record = session.stages.get(stage)
        if not stage_record:
            return ()
        paths = tuple(self.workspace / path for path in stage_record.get("outputs", ()))
        manifest_value = stage_record.get("manifest")
        if not manifest_value:
            return ()
        manifest = json.loads(
            (self.workspace / str(manifest_value)).read_text(encoding="utf-8")
        )
        for path, record in zip(paths, manifest["outputs"], strict=True):
            if (
                not path.is_file()
                or path.stat().st_size != record["size_bytes"]
                or sha256_file(path) != record["sha256"]
            ):
                raise ArtifactIntegrityError(f"Invalid cached stage artifact: {path}")
        return paths

    def save_adjustments(
        self,
        session: SheetProcessingSession,
        adjustments: Sequence[FrameAdjustment],
    ) -> Path:
        overrides = self.workspace / session.output_dir / "overrides"
        overrides.mkdir(parents=True, exist_ok=True)
        version = len(tuple(overrides.glob("frame-adjustments.v*.json"))) + 1
        path = overrides / f"frame-adjustments.v{version:03d}.json"
        atomic_write_json(
            path,
            {
                "schema_version": "1.0",
                "session_id": session.session_id,
                "created_at": utc_now(),
                "frames": [item.to_dict() for item in adjustments],
            },
        )
        session.frame_adjustments = list(adjustments)
        self.save(session)
        return path

    def export(
        self,
        session: SheetProcessingSession,
        frames: Sequence[Image.Image],
        *,
        layout: str = "horizontal",
        columns: int | None = None,
        export_frames: bool = True,
        export_contact_sheet: bool = True,
        export_gif: bool = False,
        fps: float = 8.0,
    ) -> dict[str, Any]:
        if any(item.manual_review for item in session.frame_adjustments):
            raise ValueError("Cannot export while frame anchors require manual review")
        cropped = trim_transparent_frames(frames, session.export_crop_config)
        identity = stable_digest(
            {
                "session": session.session_id,
                "updated_at": session.updated_at,
                "layout": layout,
                "columns": columns,
                "frame_count": len(cropped.frames),
                "crop_bbox": cropped.bbox,
                "crop_enabled": session.export_crop_config.enabled,
                "crop_padding": session.export_crop_config.padding,
                "crop_alpha_threshold": session.export_crop_config.alpha_threshold,
            }
        )[:12]
        attempt_id = f"export-{identity}"
        directory = self.workspace / session.output_dir / "exports" / attempt_id
        if directory.exists():
            raise FileExistsError(f"Export attempt already exists: {directory}")
        sheet_path = directory / "sprite-sheet.png"
        result = export_sheet(
            cropped.frames,
            sheet_path,
            layout=layout,
            columns=columns,
            cell_size=(
                max(frame.width for frame in cropped.frames),
                max(frame.height for frame in cropped.frames),
            ),
        )
        outputs = [result.output_path]
        frames_dir: Path | None = None
        if export_frames:
            frames_dir = directory / "frames"
            for index, frame in enumerate(cropped.frames):
                path = frames_dir / f"frame_{index:03d}.png"
                _atomic_save_png(frame, path)
                outputs.append(path)
        contact_path: Path | None = None
        if export_contact_sheet:
            contact_path = directory / "contact-sheet.png"
            contact = render_contact_sheet(
                cropped.frames,
                adjustments=session.frame_adjustments or None,
                origin_offset=(cropped.bbox[0], cropped.bbox[1]),
            )
            _atomic_save_png(contact, contact_path)
            outputs.append(contact_path)
        gif_path: Path | None = None
        if export_gif:
            if fps <= 0:
                raise ValueError("FPS must be positive")
            gif_path = directory / "preview.gif"
            rendered = [
                frame.convert("RGBA").resize(
                    (frame.width * 4, frame.height * 4),
                    Image.Resampling.NEAREST,
                )
                for frame in cropped.frames
            ]
            gif_path.parent.mkdir(parents=True, exist_ok=True)
            rendered[0].save(
                gif_path,
                save_all=True,
                append_images=rendered[1:],
                duration=max(1, round(1000 / fps)),
                loop=0,
                disposal=2,
                optimize=False,
            )
            outputs.append(gif_path)

        records = [
            asdict(ArtifactRecord.from_path(path, root=self.workspace))
            for path in outputs
        ]
        manifest = {
            "schema_version": "1.0",
            "session_id": session.session_id,
            "attempt_id": attempt_id,
            "output_png": str(result.output_path.relative_to(self.workspace)),
            "output_frames_dir": (
                str(frames_dir.relative_to(self.workspace)) if frames_dir else None
            ),
            "contact_sheet": (
                str(contact_path.relative_to(self.workspace)) if contact_path else None
            ),
            "preview_gif": str(gif_path.relative_to(self.workspace)) if gif_path else None,
            "exported_at": utc_now(),
            "layout": layout,
            "cell_size": list(result.cell_size),
            "frame_count": len(cropped.frames),
            "alpha": True,
            "sha256": sha256_file(result.output_path),
            "crop": {
                "enabled": session.export_crop_config.enabled,
                "padding": session.export_crop_config.padding,
                "alpha_threshold": session.export_crop_config.alpha_threshold,
                "bbox": list(cropped.bbox),
                "source_size": list(cropped.source_size),
            },
            "godot_notes": (
                f"{result.columns} column(s), {result.rows} row(s); "
                "use nearest filtering and lossless compression"
            ),
            "outputs": records,
        }
        atomic_write_json(directory / "manifest.json", manifest)
        atomic_write_json(
            self.workspace / session.output_dir / "manifests" / "export.json",
            manifest,
        )
        session.export_manifest = manifest
        session.current_stage = "export"
        session.stages["export"] = {
            "status": "passed",
            "manifest": str((directory / "manifest.json").relative_to(self.workspace)),
            "outputs": [record["path"] for record in records],
        }
        self.save(session)
        return manifest
