from __future__ import annotations

from pathlib import Path

from PIL import Image

from sprite_builder.export import (
    build_native_metadata,
    export_native_godot_bundle,
    preserve_native_sheet,
)


def _native_source(path: Path) -> None:
    image = Image.new("RGBA", (13, 9), (0, 255, 255, 255))
    image.putpixel((2, 3), (12, 34, 56, 255))
    image.putpixel((10, 7), (12, 34, 56, 0))
    image.save(path, format="PNG", optimize=False)


def test_native_export_copies_full_sheet_and_keeps_irregular_regions(tmp_path: Path) -> None:
    source = tmp_path / "manual-full-sheet.png"
    output = tmp_path / "godot" / "native.png"
    _native_source(source)
    regions = ((0, 0, 7, 9), (7, 0, 6, 9))

    result = preserve_native_sheet(source, output, regions=regions)

    assert output.read_bytes() == source.read_bytes()
    assert result.sheet_size == (13, 9)
    assert result.regions == regions
    assert result.source_sha256 == result.output_sha256
    metadata = build_native_metadata(
        result,
        animation="save",
        fps=8,
        loop=False,
        frame_indices=(4, 9),
    )
    assert metadata["export_mode"] == "native_full_sheet"
    assert metadata["sheet"]["size"] == [13, 9]
    assert metadata["sheet"]["cell_size"] is None
    assert metadata["frames"][0]["native_frame_index"] == 4
    assert metadata["frames"][1]["region"] == [7, 0, 6, 9]
    assert metadata["transformations"]["resample"] is False


def test_native_godot_bundle_uses_full_atlas_regions_without_import(tmp_path: Path) -> None:
    source = tmp_path / "manual-full-sheet.png"
    output = tmp_path / "native.png"
    _native_source(source)
    result = preserve_native_sheet(
        source,
        output,
        regions=((0, 0, 7, 9), (7, 0, 6, 9)),
    )

    metadata_path, tres_path = export_native_godot_bundle(
        sheet=result,
        output_directory=tmp_path / "bundle",
        texture_resource_path="res://assets/generated/native.png",
        animation="save_confirm",
        fps=8,
        loop=False,
        frame_indices=(4, 9),
    )

    text = tres_path.read_text(encoding="utf-8")
    assert metadata_path.is_file()
    assert text.count('[sub_resource type="AtlasTexture"') == 2
    assert "Rect2(0, 0, 7, 9)" in text
    assert "Rect2(7, 0, 6, 9)" in text
    assert ".import" not in text
