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
