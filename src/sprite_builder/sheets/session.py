"""Immutable artifact storage for local sprite-sheet editing sessions."""

from __future__ import annotations

import hashlib
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
from sprite_builder.sheets.engine import (
    export_sheet,
    render_contact_sheet,
    trim_transparent_frames,
)
from sprite_builder.sheets.inspect import inspect_sheet
from sprite_builder.sheets.layers import (
    LayeredSpriteDocument,
    SpriteCel,
    SpriteLayer,
    composite_document_frames,
)
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


def _image_digest(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.convert("RGBA").save(buffer, format="PNG", optimize=False)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


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

    def create_blank_sprite(
        self,
        *,
        canvas_width: int,
        canvas_height: int,
        frame_count: int = 1,
        source_name: str = "nuevo-sprite.png",
    ) -> SheetProcessingSession:
        """Create a transparent source sheet suitable for drawing from scratch."""

        width = max(1, int(canvas_width))
        height = max(1, int(canvas_height))
        count = max(1, int(frame_count))
        source = Image.new("RGBA", (width * count, height))
        buffer = io.BytesIO()
        source.save(buffer, format="PNG", optimize=False)
        session = self.create(buffer.getvalue(), source_name=source_name)
        session.segmentation_config = SegmentationConfig(
            frame_count=count,
            orientation="horizontal",
            rows=1,
            columns=1,
            cell_width=width,
            cell_height=height,
        )
        session.auto_center_config = AutoCenterConfig(
            canvas_width=width,
            canvas_height=height,
            canonical_anchor=(width // 2, height // 2),
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

    def _workspace_artifact_path(self, value: object, *, label: str) -> Path:
        """Resolve a stored artifact path without allowing it to escape the workspace."""

        candidate = Path(str(value))
        if candidate.is_absolute():
            raise ArtifactIntegrityError(f"{label} must be relative to the workspace")
        path = (self.workspace / candidate).resolve()
        try:
            path.relative_to(self.workspace)
        except ValueError as exc:
            raise ArtifactIntegrityError(
                f"{label} escapes the workspace: {candidate}"
            ) from exc
        return path

    def _artifact_record(
        self,
        path: Path,
        *,
        media_type: str,
        role: str,
    ) -> ArtifactRecord:
        record = ArtifactRecord.from_path(
            path,
            root=self.workspace,
            media_type=media_type,
        )
        return ArtifactRecord(
            path=record.path,
            sha256=record.sha256,
            size_bytes=record.size_bytes,
            media_type=record.media_type,
            role=role,
        )

    def _verify_artifact_record(
        self,
        record: ArtifactRecord,
        *,
        label: str,
    ) -> Path:
        path = self._workspace_artifact_path(record.path, label=label)
        if (
            not path.is_file()
            or path.stat().st_size != record.size_bytes
            or sha256_file(path) != record.sha256
        ):
            raise ArtifactIntegrityError(f"{label} failed SHA-256 verification: {path}")
        return path

    def _layer_document_pointer(
        self,
        manifest_path: Path,
        document: LayeredSpriteDocument,
        *,
        cache_key: str,
    ) -> dict[str, Any]:
        manifest_record = self._artifact_record(
            manifest_path,
            media_type="application/json",
            role="layer_document_manifest",
        )
        return {
            "cache_key": cache_key,
            "manifest": manifest_record.path,
            "manifest_sha256": manifest_record.sha256,
            "document_id": document.document_id,
            "revision": document.revision,
        }

    def _load_layer_document_attempt(
        self,
        session: SheetProcessingSession,
        pointer: Mapping[str, Any],
    ) -> tuple[LayeredSpriteDocument, dict[tuple[str, int], Image.Image]]:
        """Load one immutable layer attempt and verify its complete lineage."""

        manifest_value = pointer.get("manifest")
        cache_key = str(pointer.get("cache_key", ""))
        if not manifest_value or not cache_key:
            raise ArtifactIntegrityError("Layer document pointer is malformed")
        manifest_path = self._workspace_artifact_path(
            manifest_value,
            label="Layer document manifest",
        )
        attempt_root = (
            self.workspace / session.output_dir / "attempts" / "layers" / cache_key
        ).resolve()
        if manifest_path != attempt_root / "manifest.json":
            raise ArtifactIntegrityError(
                "Layer document manifest does not belong to the referenced attempt"
            )
        expected_manifest_sha = pointer.get("manifest_sha256")
        if expected_manifest_sha and (
            not manifest_path.is_file()
            or sha256_file(manifest_path) != str(expected_manifest_sha)
        ):
            raise ArtifactIntegrityError(
                f"Layer document manifest failed SHA-256 verification: {manifest_path}"
            )
        if not manifest_path.is_file():
            raise ArtifactIntegrityError(
                f"Layer document manifest is missing: {manifest_path}"
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError(
                f"Layer document manifest is unreadable: {manifest_path}"
            ) from exc
        if not isinstance(manifest, Mapping):
            raise ArtifactIntegrityError("Layer document manifest is malformed")
        if (
            manifest.get("schema_version") != "1.0"
            or manifest.get("session_id") != session.session_id
            or manifest.get("stage") != "layers"
            or manifest.get("cache_key") != cache_key
        ):
            raise ArtifactIntegrityError("Layer document manifest lineage does not match")

        document_raw = manifest.get("document")
        if not isinstance(document_raw, Mapping):
            raise ArtifactIntegrityError("Layer document manifest has no document payload")
        document_record_raw = manifest.get("document_artifact")
        if document_record_raw is not None:
            if not isinstance(document_record_raw, Mapping):
                raise ArtifactIntegrityError("Layer document artifact record is malformed")
            try:
                document_record = ArtifactRecord(**document_record_raw)
            except TypeError as exc:
                raise ArtifactIntegrityError(
                    "Layer document artifact record is malformed"
                ) from exc
            document_path = self._verify_artifact_record(
                document_record,
                label="Layer document",
            )
            if document_path.parent != attempt_root:
                raise ArtifactIntegrityError(
                    "Layer document artifact does not belong to the referenced attempt"
                )
            try:
                stored_document = json.loads(document_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ArtifactIntegrityError(
                    f"Layer document artifact is unreadable: {document_path}"
                ) from exc
            if stored_document != document_raw:
                raise ArtifactIntegrityError(
                    "Layer document artifact differs from its published manifest"
                )

        try:
            document = LayeredSpriteDocument.from_dict(document_raw)
            document.validate_complete_cels()
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactIntegrityError("Layer document payload is invalid") from exc
        if (
            pointer.get("document_id") not in (None, document.document_id)
            or pointer.get("revision") not in (None, document.revision)
        ):
            raise ArtifactIntegrityError("Layer document pointer does not match its payload")

        images: dict[tuple[str, int], Image.Image] = {}
        for cel in document.cels:
            path = self._workspace_artifact_path(cel.image_path, label="Layer cel")
            try:
                path.relative_to(attempt_root)
            except ValueError as exc:
                raise ArtifactIntegrityError(
                    "Layer cel does not belong to the referenced attempt"
                ) from exc
            if not path.is_file() or sha256_file(path) != cel.sha256:
                raise ArtifactIntegrityError(f"Layer cel failed SHA-256 verification: {path}")
            try:
                with Image.open(path) as image:
                    images[(cel.layer_id, cel.frame_index)] = image.convert("RGBA")
            except OSError as exc:
                raise ArtifactIntegrityError(f"Layer cel is unreadable: {path}") from exc
        return document, images

    def create_layer_document(
        self,
        session: SheetProcessingSession,
        frames: Sequence[Image.Image],
        *,
        source_name: str = "Fuente IA",
    ) -> LayeredSpriteDocument:
        """Create the initial locked source and editable retouch tracks.

        The document is based on the currently segmented/cleaned frames.  It is
        independent from the original upload so the source upload remains
        immutable and the document can be versioned through layer attempts.
        """

        if not frames:
            raise ValueError("A layer document needs at least one frame")
        rgba_frames = tuple(frame.convert("RGBA") for frame in frames)
        canvas_width = max(frame.width for frame in rgba_frames)
        canvas_height = max(frame.height for frame in rgba_frames)
        source_layer = SpriteLayer(
            layer_id="source",
            name=source_name,
            role="source",
            locked=True,
        )
        retouch_layer = SpriteLayer(
            layer_id="retouch",
            name="Retoque",
            role="retouch",
        )
        document = LayeredSpriteDocument(
            schema_version="1.0",
            document_id=f"sprite-{uuid.uuid4().hex[:12]}",
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            frame_count=len(rgba_frames),
            layers=(source_layer, retouch_layer),
            cels=(),
        )
        images: dict[tuple[str, int], Image.Image] = {}
        for index, frame in enumerate(rgba_frames):
            images[(source_layer.layer_id, index)] = frame
            images[(retouch_layer.layer_id, index)] = Image.new(
                "RGBA",
                (canvas_width, canvas_height),
            )
        return self.save_layer_document(session, document, images, reason="create")

    def load_layer_document(
        self,
        session: SheetProcessingSession,
    ) -> tuple[LayeredSpriteDocument, dict[tuple[str, int], Image.Image]]:
        pointer = session.layer_document
        if not pointer:
            raise FileNotFoundError("This session has no layer document")
        return self._load_layer_document_attempt(session, pointer)

    def restore_layer_document_attempt(
        self,
        session: SheetProcessingSession,
        pointer: Mapping[str, Any],
    ) -> LayeredSpriteDocument:
        """Restore an immutable layer attempt after verifying all of its artifacts.

        Undo/redo moves the session pointer between existing immutable attempts.  The
        attempt loader verifies the manifest and every cel SHA-256 before the pointer
        is published, so history never turns an unchecked cache entry into live state.
        """

        restored, _ = self._load_layer_document_attempt(session, pointer)
        manifest_value = pointer.get("manifest")
        cache_key = str(pointer.get("cache_key", ""))
        if not isinstance(manifest_value, str) or not manifest_value or not cache_key:
            raise ArtifactIntegrityError("Layer history pointer is incomplete")
        manifest_path = self._workspace_artifact_path(
            manifest_value,
            label="Layer history manifest",
        )
        session.layer_document = self._layer_document_pointer(
            manifest_path,
            restored,
            cache_key=cache_key,
        )
        self.save(session)
        return restored

    def save_layer_document(
        self,
        session: SheetProcessingSession,
        document: LayeredSpriteDocument,
        images: Mapping[tuple[str, int], Image.Image],
        *,
        reason: str,
    ) -> LayeredSpriteDocument:
        """Publish a self-contained immutable document attempt before its manifest."""

        document.validate()
        normalized_images: dict[tuple[str, int], Image.Image] = {}
        cels: list[SpriteCel] = []
        identity_cels: list[dict[str, Any]] = []
        for layer in document.layers:
            for frame_index in range(document.frame_count):
                key = (layer.layer_id, frame_index)
                image = images.get(key)
                if image is None:
                    image = Image.new("RGBA", (document.canvas_width, document.canvas_height))
                rgba = image.convert("RGBA")
                normalized_images[key] = rgba
                previous = document.cel(layer.layer_id, frame_index)
                cels.append(
                    SpriteCel(
                        layer_id=layer.layer_id,
                        frame_index=frame_index,
                        image_path="",
                        sha256="",
                        offset_x=previous.offset_x if previous else 0,
                        offset_y=previous.offset_y if previous else 0,
                    )
                )
                identity_cels.append(
                    {
                        "layer_id": layer.layer_id,
                        "frame_index": frame_index,
                        "offset_x": previous.offset_x if previous else 0,
                        "offset_y": previous.offset_y if previous else 0,
                        "image_sha256": _image_digest(rgba),
                    }
                )
        cache_key = stable_digest(
            {
                "session_id": session.session_id,
                "source_sha256": session.source_sha256,
                "document_id": document.document_id,
                "canvas": [document.canvas_width, document.canvas_height],
                "frame_count": document.frame_count,
                "layers": [layer.to_dict() for layer in document.layers],
                "cels": identity_cels,
                "reason": reason,
            }
        )
        directory = self.workspace / session.output_dir / "attempts" / "layers" / cache_key
        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            cached_pointer = {
                "cache_key": cache_key,
                "manifest": str(manifest_path.relative_to(self.workspace)),
            }
            restored, _ = self._load_layer_document_attempt(session, cached_pointer)
            session.layer_document = self._layer_document_pointer(
                manifest_path,
                restored,
                cache_key=cache_key,
            )
            self.save(session)
            return restored

        published_cels: list[SpriteCel] = []
        output_records: list[dict[str, Any]] = []
        for cel in cels:
            image = normalized_images[(cel.layer_id, cel.frame_index)]
            destination = directory / "cels" / cel.layer_id / f"frame_{cel.frame_index:03d}.png"
            if destination.exists():
                raise FileExistsError(
                    f"Refusing to overwrite layer cel artifact: {destination}"
                )
            _atomic_save_png(image, destination)
            record = asdict(
                ArtifactRecord.from_path(destination, root=self.workspace, media_type="image/png")
            )
            output_records.append(record)
            published_cels.append(
                SpriteCel(
                    layer_id=cel.layer_id,
                    frame_index=cel.frame_index,
                    image_path=str(destination.relative_to(self.workspace)),
                    sha256=str(record["sha256"]),
                    offset_x=cel.offset_x,
                    offset_y=cel.offset_y,
                )
            )
        published = LayeredSpriteDocument(
            schema_version=document.schema_version,
            document_id=document.document_id,
            canvas_width=document.canvas_width,
            canvas_height=document.canvas_height,
            frame_count=document.frame_count,
            layers=document.layers,
            cels=tuple(published_cels),
            revision=document.revision,
        )
        published.validate_complete_cels()
        document_path = directory / "document.json"
        if document_path.exists():
            raise FileExistsError(
                f"Refusing to overwrite layer document artifact: {document_path}"
            )
        atomic_write_json(document_path, published.to_dict())
        document_record = self._artifact_record(
            document_path,
            media_type="application/json",
            role="layer_document",
        )
        manifest = {
            "schema_version": "1.0",
            "session_id": session.session_id,
            "stage": "layers",
            "cache_key": cache_key,
            "reason": reason,
            "inputs": [
                {
                    "path": session.source_image_path,
                    "sha256": session.source_sha256,
                    "role": "source",
                }
            ],
            "outputs": [*output_records, asdict(document_record)],
            "document": published.to_dict(),
            "document_artifact": asdict(document_record),
            "created_at": utc_now(),
        }
        atomic_write_json(manifest_path, manifest)
        pointer = self.workspace / session.output_dir / "manifests" / "layers.json"
        atomic_write_json(pointer, manifest)
        session.layer_document = self._layer_document_pointer(
            manifest_path,
            published,
            cache_key=cache_key,
        )
        self.save(session)
        return published

    def publish_layer_document(
        self,
        session: SheetProcessingSession,
        document: LayeredSpriteDocument,
        images: Mapping[tuple[str, int], Image.Image],
        *,
        reason: str,
    ) -> tuple[LayeredSpriteDocument, tuple[Path, ...]]:
        """Persist the document and publish its flattened frames for Auto Center."""

        self.save_layer_document(session, document, images, reason=reason)
        # Flatten the immutable persisted cels, rather than the caller's working
        # images.  This keeps the artwork stage tied to the SHA-verified layer
        # attempt that the session now references.
        persisted, persisted_images = self.load_layer_document(session)
        flattened = composite_document_frames(persisted, persisted_images)
        if not session.layer_document:
            raise ArtifactIntegrityError("Published layer document pointer is missing")
        layer_manifest = self._workspace_artifact_path(
            session.layer_document["manifest"],
            label="Layer document manifest",
        )
        layer_manifest_record = self._artifact_record(
            layer_manifest,
            media_type="application/json",
            role="layer_document_manifest",
        )
        outputs = self.commit_stage(
            session,
            "artwork",
            flattened,
            config={
                "layer_document_cache_key": session.layer_document["cache_key"]
                if session.layer_document
                else "",
                "canvas_width": persisted.canvas_width,
                "canvas_height": persisted.canvas_height,
            },
            metadata={
                "layer_document": dict(session.layer_document or {}),
                "reason": reason,
            },
            input_artifacts=(layer_manifest_record,),
        )
        return persisted, outputs

    @staticmethod
    def _invalidate_downstream(
        session: SheetProcessingSession,
        stage: str,
    ) -> None:
        downstream = {
            "source": ("background", "segmentation", "artwork", "alignment", "export"),
            "background": ("segmentation", "artwork", "alignment", "export"),
            "segmentation": ("artwork", "alignment", "export"),
            "artwork": ("alignment", "export"),
            "alignment": ("export",),
            "export": (),
        }
        invalidated = downstream.get(stage, ())
        for name in invalidated:
            session.stages.pop(name, None)
        if stage in {"source", "background", "segmentation"}:
            session.layer_document = None
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
        input_artifacts: Sequence[ArtifactRecord] = (),
    ) -> tuple[Path, ...]:
        if status not in {"passed", "manual_review", "failed"}:
            raise ValueError(f"Invalid stage status: {status}")
        if not images:
            raise ValueError("A stage must publish at least one output image")
        source_record = self._artifact_record(
            self.source_path(session),
            media_type="image/png",
            role="source",
        )
        verified_inputs = [source_record]
        for record in input_artifacts:
            self._verify_artifact_record(record, label=f"{stage} input")
            verified_inputs.append(record)
        cache_key = stable_digest(
            {
                "session_id": session.session_id,
                "source_sha256": session.source_sha256,
                "stage": stage,
                "config": config,
                "metadata": metadata or {},
                # Config is not a substitute for the pixels it is applied to.
                # This prevents Auto Center from restoring an old alignment
                # attempt after Studio has published different artwork.
                "image_sha256": [_image_digest(image) for image in images],
                "input_artifacts": [
                    {
                        "sha256": record.sha256,
                        "role": record.role,
                        "media_type": record.media_type,
                    }
                    for record in verified_inputs
                ],
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
            "inputs": [asdict(record) for record in verified_inputs],
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
        allow_manual_review: bool = False,
    ) -> dict[str, Any]:
        alignment = session.stages.get("alignment")
        validation_warnings: list[str] = []
        if not alignment or alignment.get("status") != "passed":
            validation_warnings.append("alignment stage is not passed")
        if len(session.frame_adjustments) != len(frames):
            raise ValueError("EXPORT_BLOCKED: frame adjustments do not match frames")
        if any(item.manual_review for item in session.frame_adjustments):
            validation_warnings.append("alignment contains manual_review frames")
        if validation_warnings and not allow_manual_review:
            raise ValueError("EXPORT_BLOCKED: " + "; ".join(validation_warnings))
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
                "validation_warnings": validation_warnings,
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
            "status": "manual_review" if validation_warnings else "passed",
            "validation_warnings": validation_warnings,
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
            "status": "manual_review" if validation_warnings else "passed",
            "manifest": str((directory / "manifest.json").relative_to(self.workspace)),
            "outputs": [record["path"] for record in records],
        }
        self.save(session)
        return manifest
