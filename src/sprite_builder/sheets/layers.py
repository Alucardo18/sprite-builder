"""Non-destructive layer/cel primitives for pixel-art sprite documents.

The processing pipeline works with flattened frames, while the editor works with
layer tracks and cels.  A cel is deliberately only translated by integral pixels:
the document never rescales a generated sprite to make it fit a frame.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from PIL import Image, ImageDraw

LayerRole = Literal["source", "body", "retouch", "shadow", "vfx", "reference"]


def _clamp_opacity(value: object) -> float:
    try:
        parsed = float(str(value))
    except ValueError:
        parsed = 1.0
    return max(0.0, min(1.0, parsed))


@dataclass(frozen=True, slots=True)
class SpriteLayer:
    """A layer track shared by every frame in an animation."""

    layer_id: str
    name: str
    role: LayerRole = "retouch"
    visible: bool = True
    locked: bool = False
    exportable: bool = True
    opacity: float = 1.0
    alpha_locked: bool = False

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SpriteLayer:
        role = str(value.get("role", "retouch"))
        if role not in {"source", "body", "retouch", "shadow", "vfx", "reference"}:
            role = "retouch"
        return cls(
            layer_id=str(value["layer_id"]),
            name=str(value.get("name", "Capa")),
            role=role,  # type: ignore[arg-type]
            visible=bool(value.get("visible", True)),
            locked=bool(value.get("locked", False)),
            exportable=bool(value.get("exportable", True)),
            opacity=_clamp_opacity(value.get("opacity", 1.0)),
            alpha_locked=bool(value.get("alpha_locked", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SpriteCel:
    """An image placed at an integer offset for one layer and one frame."""

    layer_id: str
    frame_index: int
    image_path: str
    sha256: str
    offset_x: int = 0
    offset_y: int = 0

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SpriteCel:
        return cls(
            layer_id=str(value["layer_id"]),
            frame_index=int(value["frame_index"]),
            image_path=str(value.get("image_path", "")),
            sha256=str(value.get("sha256", "")),
            offset_x=int(value.get("offset_x", 0)),
            offset_y=int(value.get("offset_y", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LayeredSpriteDocument:
    """A Photoshop-like stack of layer tracks over an animation timeline."""

    schema_version: str
    document_id: str
    canvas_width: int
    canvas_height: int
    frame_count: int
    layers: tuple[SpriteLayer, ...]
    cels: tuple[SpriteCel, ...]
    revision: int = 1

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> LayeredSpriteDocument:
        raw_layers = value.get("layers", ())
        raw_cels = value.get("cels", ())
        if not isinstance(raw_layers, Sequence) or isinstance(raw_layers, (str, bytes)):
            raise ValueError("Document layers must be a sequence")
        if not isinstance(raw_cels, Sequence) or isinstance(raw_cels, (str, bytes)):
            raise ValueError("Document cels must be a sequence")
        document = cls(
            schema_version=str(value.get("schema_version", "1.0")),
            document_id=str(value["document_id"]),
            canvas_width=max(1, int(value["canvas_width"])),
            canvas_height=max(1, int(value["canvas_height"])),
            frame_count=max(1, int(value["frame_count"])),
            layers=tuple(
                SpriteLayer.from_dict(item)
                for item in raw_layers
                if isinstance(item, Mapping)
            ),
            cels=tuple(
                SpriteCel.from_dict(item)
                for item in raw_cels
                if isinstance(item, Mapping)
            ),
            revision=max(1, int(value.get("revision", 1))),
        )
        document.validate()
        return document

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "frame_count": self.frame_count,
            "layers": [layer.to_dict() for layer in self.layers],
            "cels": [cel.to_dict() for cel in self.cels],
            "revision": self.revision,
        }

    def validate(self) -> None:
        layer_ids = [layer.layer_id for layer in self.layers]
        if not layer_ids:
            raise ValueError("A sprite document needs at least one layer")
        if len(layer_ids) != len(set(layer_ids)):
            raise ValueError("Sprite layer ids must be unique")
        cel_keys = [(cel.layer_id, cel.frame_index) for cel in self.cels]
        if len(cel_keys) != len(set(cel_keys)):
            raise ValueError("A document can only have one cel per layer/frame")
        valid_layers = set(layer_ids)
        for cel in self.cels:
            if cel.layer_id not in valid_layers:
                raise ValueError(f"Cel references unknown layer: {cel.layer_id}")
            if not 0 <= cel.frame_index < self.frame_count:
                raise ValueError(f"Cel frame is out of bounds: {cel.frame_index}")

    def validate_complete_cels(self) -> None:
        """Validate a persisted document has one immutable cel per layer/frame.

        A document can deliberately be assembled without cels while it is being
        edited.  Once written as an artifact attempt, however, omitting a cel
        would make the flattened pipeline input ambiguous (missing data could
        otherwise be mistaken for transparent pixels).
        """

        self.validate()
        expected = {
            (layer.layer_id, frame_index)
            for layer in self.layers
            for frame_index in range(self.frame_count)
        }
        actual = {(cel.layer_id, cel.frame_index) for cel in self.cels}
        if actual != expected:
            missing = sorted(expected - actual)
            unexpected = sorted(actual - expected)
            details: list[str] = []
            if missing:
                details.append(f"missing={missing}")
            if unexpected:
                details.append(f"unexpected={unexpected}")
            raise ValueError(
                "A persisted sprite document needs exactly one cel per "
                f"layer/frame ({', '.join(details)})"
            )

    def layer(self, layer_id: str) -> SpriteLayer:
        for layer in self.layers:
            if layer.layer_id == layer_id:
                return layer
        raise KeyError(layer_id)

    def cel(self, layer_id: str, frame_index: int) -> SpriteCel | None:
        for cel in self.cels:
            if cel.layer_id == layer_id and cel.frame_index == frame_index:
                return cel
        return None

    def with_layer(
        self,
        layer: SpriteLayer,
        *,
        above_layer_id: str | None = None,
    ) -> LayeredSpriteDocument:
        if layer.layer_id in {item.layer_id for item in self.layers}:
            raise ValueError(f"Layer already exists: {layer.layer_id}")
        layers = list(self.layers)
        if above_layer_id is None:
            layers.append(layer)
        else:
            index = next(
                (index for index, item in enumerate(layers) if item.layer_id == above_layer_id),
                None,
            )
            if index is None:
                raise KeyError(above_layer_id)
            layers.insert(index + 1, layer)
        return replace(self, layers=tuple(layers), revision=self.revision + 1)

    def reordered(self, layer_id: str, destination_index: int) -> LayeredSpriteDocument:
        layers = list(self.layers)
        current = next(
            (index for index, item in enumerate(layers) if item.layer_id == layer_id),
            None,
        )
        if current is None:
            raise KeyError(layer_id)
        item = layers.pop(current)
        layers.insert(max(0, min(len(layers), int(destination_index))), item)
        return replace(self, layers=tuple(layers), revision=self.revision + 1)

    def with_layer_properties(self, layer_id: str, **changes: Any) -> LayeredSpriteDocument:
        layers = tuple(
            replace(layer, **changes) if layer.layer_id == layer_id else layer
            for layer in self.layers
        )
        if layers == self.layers:
            raise KeyError(layer_id)
        updated = replace(self, layers=layers, revision=self.revision + 1)
        updated.validate()
        return updated

    def with_cel(self, cel: SpriteCel) -> LayeredSpriteDocument:
        self.layer(cel.layer_id)
        if not 0 <= cel.frame_index < self.frame_count:
            raise ValueError("Cel frame is out of bounds")
        cels = [
            item
            for item in self.cels
            if (item.layer_id, item.frame_index) != (cel.layer_id, cel.frame_index)
        ]
        cels.append(cel)
        updated = replace(self, cels=tuple(cels), revision=self.revision + 1)
        updated.validate()
        return updated

    def with_cel_offset(
        self,
        layer_id: str,
        frame_index: int,
        *,
        offset_x: int,
        offset_y: int,
    ) -> LayeredSpriteDocument:
        previous = self.cel(layer_id, frame_index)
        if previous is None:
            raise KeyError((layer_id, frame_index))
        return self.with_cel(
            replace(previous, offset_x=int(offset_x), offset_y=int(offset_y))
        )

    def revised(self) -> LayeredSpriteDocument:
        """Mark a pixel-content edit while retaining the same layer/cel layout."""

        return replace(self, revision=self.revision + 1)

    def expanded_to_content(
        self,
        images: Mapping[tuple[str, int], Image.Image],
        *,
        padding: int = 0,
        include_roles: Sequence[LayerRole] | None = None,
    ) -> LayeredSpriteDocument:
        """Enlarge every frame cell to fit content, preserving every pixel and offset."""

        allowed = set(include_roles) if include_roles is not None else None
        min_x, min_y = 0, 0
        max_x, max_y = self.canvas_width, self.canvas_height
        for layer in self.layers:
            if not layer.visible or not layer.exportable:
                continue
            if allowed is not None and layer.role not in allowed:
                continue
            for frame_index in range(self.frame_count):
                cel = self.cel(layer.layer_id, frame_index)
                image = images.get((layer.layer_id, frame_index))
                if cel is None or image is None:
                    continue
                bbox = image.convert("RGBA").getbbox()
                if bbox is None:
                    continue
                min_x = min(min_x, cel.offset_x + bbox[0])
                min_y = min(min_y, cel.offset_y + bbox[1])
                max_x = max(max_x, cel.offset_x + bbox[2])
                max_y = max(max_y, cel.offset_y + bbox[3])
        pad = max(0, int(padding))
        shift_x = -min_x + pad
        shift_y = -min_y + pad
        width = max(1, max_x - min_x + pad * 2)
        height = max(1, max_y - min_y + pad * 2)
        cels = tuple(
            replace(cel, offset_x=cel.offset_x + shift_x, offset_y=cel.offset_y + shift_y)
            for cel in self.cels
        )
        updated = replace(
            self,
            canvas_width=width,
            canvas_height=height,
            cels=cels,
            revision=self.revision + 1,
        )
        updated.validate()
        return updated


def composite_document_frames(
    document: LayeredSpriteDocument,
    images: Mapping[tuple[str, int], Image.Image],
    *,
    analysis_only: bool = False,
) -> tuple[Image.Image, ...]:
    """Flatten visible export layers with nearest, integer-only placement."""

    result: list[Image.Image] = []
    for frame_index in range(document.frame_count):
        frame = Image.new("RGBA", (document.canvas_width, document.canvas_height))
        for layer in document.layers:
            if not layer.visible or not layer.exportable:
                continue
            if analysis_only and layer.role in {"vfx", "reference"}:
                continue
            cel = document.cel(layer.layer_id, frame_index)
            image = images.get((layer.layer_id, frame_index))
            if cel is None or image is None:
                continue
            placed = image.convert("RGBA")
            if layer.opacity < 1:
                placed = placed.copy()
                alpha = placed.getchannel("A").point(
                    lambda value, opacity=layer.opacity: round(value * opacity)
                )
                placed.putalpha(alpha)
            frame.alpha_composite(placed, dest=(cel.offset_x, cel.offset_y))
        result.append(frame)
    return tuple(result)


def composite_document_frame(
    document: LayeredSpriteDocument,
    images: Mapping[tuple[str, int], Image.Image],
    frame_index: int,
    *,
    analysis_only: bool = False,
) -> Image.Image:
    """Flatten one frame without composing every hidden timeline frame."""

    index = int(frame_index)
    if not 0 <= index < document.frame_count:
        raise IndexError(index)
    frame = Image.new("RGBA", (document.canvas_width, document.canvas_height))
    for layer in document.layers:
        if not layer.visible or not layer.exportable:
            continue
        if analysis_only and layer.role in {"vfx", "reference"}:
            continue
        cel = document.cel(layer.layer_id, index)
        image = images.get((layer.layer_id, index))
        if cel is None or image is None:
            continue
        placed = image.convert("RGBA")
        if layer.opacity < 1:
            placed = placed.copy()
            placed.putalpha(
                placed.getchannel("A").point(
                    lambda value, opacity=layer.opacity: round(value * opacity)
                )
            )
        frame.alpha_composite(placed, dest=(cel.offset_x, cel.offset_y))
    return frame


def fill_cel_selection(
    image: Image.Image,
    mask: Any,
    color: tuple[int, int, int, int],
) -> Image.Image:
    """Fill a boolean selection exactly, without filtering or antialiasing."""

    import numpy as np

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    selected = np.asarray(mask, dtype=bool)
    if selected.shape != rgba.shape[:2]:
        raise ValueError("Selection mask must match cel size")
    rgba[selected] = np.asarray(color, dtype=np.uint8)
    return Image.fromarray(rgba, "RGBA")


def replace_cel_color(
    image: Image.Image,
    source: tuple[int, int, int, int],
    target: tuple[int, int, int, int],
    *,
    tolerance: int = 0,
    mask: Any | None = None,
) -> Image.Image:
    """Replace RGBA colors inside an optional selection using integer distance."""

    import numpy as np

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    delta = np.abs(rgba.astype(np.int16) - np.asarray(source, dtype=np.int16))
    selected = np.max(delta, axis=2) <= max(0, min(255, int(tolerance)))
    if mask is not None:
        region = np.asarray(mask, dtype=bool)
        if region.shape != selected.shape:
            raise ValueError("Selection mask must match cel size")
        selected &= region
    rgba[selected] = np.asarray(target, dtype=np.uint8)
    return Image.fromarray(rgba, "RGBA")


def transform_cel_selection(
    image: Image.Image,
    mask: Any,
    operation: str,
) -> tuple[Image.Image, Any]:
    """Flip or rotate selected pixels with nearest, integer-only placement."""

    import numpy as np

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    selected = np.asarray(mask, dtype=bool)
    if selected.shape != rgba.shape[:2]:
        raise ValueError("Selection mask must match cel size")
    rows, columns = np.where(selected)
    if not len(rows):
        return image.convert("RGBA"), selected.copy()
    x0, x1 = int(columns.min()), int(columns.max()) + 1
    y0, y1 = int(rows.min()), int(rows.max()) + 1
    piece = rgba[y0:y1, x0:x1].copy()
    piece_mask = selected[y0:y1, x0:x1].copy()
    piece[~piece_mask, 3] = 0
    if operation == "flip-horizontal":
        transformed = np.flip(piece, axis=1)
        transformed_mask = np.flip(piece_mask, axis=1)
    elif operation == "flip-vertical":
        transformed = np.flip(piece, axis=0)
        transformed_mask = np.flip(piece_mask, axis=0)
    elif operation == "rotate-cw":
        transformed = np.rot90(piece, -1)
        transformed_mask = np.rot90(piece_mask, -1)
    elif operation == "rotate-ccw":
        transformed = np.rot90(piece, 1)
        transformed_mask = np.rot90(piece_mask, 1)
    elif operation == "rotate-180":
        transformed = np.rot90(piece, 2)
        transformed_mask = np.rot90(piece_mask, 2)
    elif operation == "scale-2x":
        transformed = np.repeat(np.repeat(piece, 2, axis=0), 2, axis=1)
        transformed_mask = np.repeat(np.repeat(piece_mask, 2, axis=0), 2, axis=1)
    elif operation == "scale-half":
        transformed = piece[::2, ::2].copy()
        transformed_mask = piece_mask[::2, ::2].copy()
    else:
        raise ValueError(f"Unknown pixel transform: {operation}")
    rgba[selected] = (0, 0, 0, 0)
    max_height, max_width = rgba.shape[:2]
    if transformed_mask.shape[0] > max_height or transformed_mask.shape[1] > max_width:
        crop_y = max(0, (transformed_mask.shape[0] - max_height) // 2)
        crop_x = max(0, (transformed_mask.shape[1] - max_width) // 2)
        transformed = transformed[crop_y : crop_y + max_height, crop_x : crop_x + max_width]
        transformed_mask = transformed_mask[
            crop_y : crop_y + max_height,
            crop_x : crop_x + max_width,
        ]
    height, width = transformed_mask.shape
    center_x = (x0 + x1) // 2
    center_y = (y0 + y1) // 2
    dest_x = center_x - width // 2
    dest_y = center_y - height // 2
    dest_x = max(0, min(rgba.shape[1] - width, dest_x))
    dest_y = max(0, min(rgba.shape[0] - height, dest_y))
    output_mask = np.zeros(selected.shape, dtype=bool)
    target = rgba[dest_y : dest_y + height, dest_x : dest_x + width]
    target[transformed_mask] = transformed[transformed_mask]
    output_mask[dest_y : dest_y + height, dest_x : dest_x + width] = transformed_mask
    return Image.fromarray(rgba, "RGBA"), output_mask


def outline_cel_pixels(
    image: Image.Image,
    color: tuple[int, int, int, int],
    *,
    radius: int = 1,
    mask: Any | None = None,
) -> Image.Image:
    """Add a crisp outline around opaque pixels, constrained by a selection."""

    import numpy as np

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    opaque = rgba[..., 3] > 0
    expanded = opaque.copy()
    for _ in range(max(1, min(8, int(radius)))):
        padded = np.pad(expanded, 1, constant_values=False)
        expanded = np.logical_or.reduce(
            [
                padded[0:-2, 0:-2], padded[0:-2, 1:-1], padded[0:-2, 2:],
                padded[1:-1, 0:-2], padded[1:-1, 1:-1], padded[1:-1, 2:],
                padded[2:, 0:-2], padded[2:, 1:-1], padded[2:, 2:],
            ]
        )
    outline = expanded & ~opaque
    if mask is not None:
        selected = np.asarray(mask, dtype=bool)
        if selected.shape != outline.shape:
            raise ValueError("Selection mask must match cel size")
        outline &= selected
    rgba[outline] = np.asarray(color, dtype=np.uint8)
    return Image.fromarray(rgba, "RGBA")


def remove_isolated_pixels(
    image: Image.Image,
    *,
    minimum_neighbors: int = 2,
    mask: Any | None = None,
) -> Image.Image:
    """Remove isolated opaque pixels using an exact 8-neighbour count."""

    import numpy as np

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    opaque = rgba[..., 3] > 0
    padded = np.pad(opaque, 1, constant_values=False)
    neighbors = sum(
        padded[dy : dy + opaque.shape[0], dx : dx + opaque.shape[1]].astype(np.uint8)
        for dy in range(3)
        for dx in range(3)
        if (dy, dx) != (1, 1)
    )
    remove = opaque & (neighbors < max(0, min(8, int(minimum_neighbors))))
    if mask is not None:
        selected = np.asarray(mask, dtype=bool)
        if selected.shape != remove.shape:
            raise ValueError("Selection mask must match cel size")
        remove &= selected
    rgba[remove] = (0, 0, 0, 0)
    return Image.fromarray(rgba, "RGBA")


def duplicate_document_frame(
    document: LayeredSpriteDocument,
    images: Mapping[tuple[str, int], Image.Image],
    frame_index: int,
) -> tuple[LayeredSpriteDocument, dict[tuple[str, int], Image.Image]]:
    """Insert a pixel-identical frame after ``frame_index`` without resizing."""

    source_index = max(0, min(document.frame_count - 1, int(frame_index)))
    insert_at = source_index + 1
    next_images: dict[tuple[str, int], Image.Image] = {}
    next_cels: list[SpriteCel] = []
    for layer in document.layers:
        for next_index in range(document.frame_count + 1):
            old_index = (
                source_index
                if next_index == insert_at
                else next_index
                if next_index < insert_at
                else next_index - 1
            )
            old_cel = document.cel(layer.layer_id, old_index)
            old_image = images.get((layer.layer_id, old_index))
            if old_cel is not None:
                next_cels.append(
                    replace(old_cel, frame_index=next_index, image_path="", sha256="")
                )
            if old_image is not None:
                next_images[(layer.layer_id, next_index)] = old_image.copy()
    updated = replace(
        document,
        frame_count=document.frame_count + 1,
        cels=tuple(next_cels),
        revision=document.revision + 1,
    )
    updated.validate()
    return updated, next_images


def delete_document_frame(
    document: LayeredSpriteDocument,
    images: Mapping[tuple[str, int], Image.Image],
    frame_index: int,
) -> tuple[LayeredSpriteDocument, dict[tuple[str, int], Image.Image]]:
    """Delete one frame while preserving at least one animation frame."""

    if document.frame_count <= 1:
        raise ValueError("An animation needs at least one frame")
    removed = max(0, min(document.frame_count - 1, int(frame_index)))
    next_images: dict[tuple[str, int], Image.Image] = {}
    next_cels: list[SpriteCel] = []
    for layer in document.layers:
        next_index = 0
        for old_index in range(document.frame_count):
            if old_index == removed:
                continue
            old_cel = document.cel(layer.layer_id, old_index)
            old_image = images.get((layer.layer_id, old_index))
            if old_cel is not None:
                next_cels.append(
                    replace(old_cel, frame_index=next_index, image_path="", sha256="")
                )
            if old_image is not None:
                next_images[(layer.layer_id, next_index)] = old_image.copy()
            next_index += 1
    updated = replace(
        document,
        frame_count=document.frame_count - 1,
        cels=tuple(next_cels),
        revision=document.revision + 1,
    )
    updated.validate()
    return updated, next_images


def move_document_frame(
    document: LayeredSpriteDocument,
    images: Mapping[tuple[str, int], Image.Image],
    source_index: int,
    destination_index: int,
) -> tuple[LayeredSpriteDocument, dict[tuple[str, int], Image.Image]]:
    """Reorder a whole frame across every layer track."""

    source = max(0, min(document.frame_count - 1, int(source_index)))
    destination = max(0, min(document.frame_count - 1, int(destination_index)))
    order = list(range(document.frame_count))
    moved = order.pop(source)
    order.insert(destination, moved)
    next_images: dict[tuple[str, int], Image.Image] = {}
    next_cels: list[SpriteCel] = []
    for layer in document.layers:
        for next_index, old_index in enumerate(order):
            old_cel = document.cel(layer.layer_id, old_index)
            old_image = images.get((layer.layer_id, old_index))
            if old_cel is not None:
                next_cels.append(
                    replace(old_cel, frame_index=next_index, image_path="", sha256="")
                )
            if old_image is not None:
                next_images[(layer.layer_id, next_index)] = old_image.copy()
    updated = replace(
        document,
        cels=tuple(next_cels),
        revision=document.revision + 1,
    )
    updated.validate()
    return updated, next_images


def paint_cel_stroke(
    image: Image.Image,
    points: Sequence[tuple[int, int]],
    *,
    color: tuple[int, int, int, int],
    radius: int = 0,
    erase: bool = False,
) -> Image.Image:
    """Paint a hard-edged pixel stroke without interpolation or antialiasing."""

    if not points:
        return image.convert("RGBA")
    result = image.convert("RGBA").copy()
    draw = ImageDraw.Draw(result)
    brush_radius = max(0, int(radius))
    fill = (0, 0, 0, 0) if erase else tuple(int(channel) for channel in color)

    def draw_dot(point: tuple[int, int]) -> None:
        x, y = point
        if brush_radius == 0:
            draw.point((x, y), fill=fill)
            return
        draw.ellipse(
            (x - brush_radius, y - brush_radius, x + brush_radius, y + brush_radius),
            fill=fill,
        )

    draw_dot(points[0])
    for start, end in zip(points, points[1:], strict=False):
        if brush_radius == 0:
            draw.line((start, end), fill=fill, width=1)
        else:
            draw.line((start, end), fill=fill, width=brush_radius * 2 + 1)
            draw_dot(end)
    return result
