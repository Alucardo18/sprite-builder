from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw

from sprite_builder.character import analyze_reference, create_character_skeleton


def _sheet(path: Path) -> Path:
    image = Image.new("RGB", (128, 64), (0, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 10, 42, 54), fill=(180, 90, 30))
    draw.rectangle((20, 18, 34, 38), fill=(230, 160, 45))
    draw.rectangle((78, 8, 110, 54), fill=(180, 90, 30))
    draw.rectangle((86, 18, 102, 38), fill=(230, 160, 45))
    # Enclosed chroma is not background.
    draw.rectangle((25, 26, 28, 29), fill=(0, 255, 0))
    image.save(path)
    return path


def test_analyze_reference_finds_frames_palette_and_proportions(tmp_path: Path) -> None:
    analysis = analyze_reference(_sheet(tmp_path / "sheet.png"), palette_colors=3)
    assert analysis.background_removed
    assert len(analysis.frame_bboxes) == 2
    assert len(analysis.component_bboxes) == 2
    assert len(analysis.palette) == 3
    assert analysis.proportions["mean_frame_height_px"] > 40
    assert sum(color.weight for color in analysis.palette) == pytest.approx(1, abs=1e-5)


def test_create_skeleton_is_reviewable_and_non_destructive(tmp_path: Path) -> None:
    reference = _sheet(tmp_path / "sheet.png")
    result = create_character_skeleton(
        "Tzucan Test",
        "Guerrero jaguar de prueba",
        workspace=tmp_path,
        reference=reference,
        palette_colors=4,
    )
    bible = yaml.safe_load(result.bible.read_text(encoding="utf-8"))
    palette = json.loads(result.palette.read_text(encoding="utf-8"))
    assert bible["identity"]["id"] == "tzucan-test"
    assert bible["review"]["required"] is True
    assert bible["reference"]["frame_count_detected"] == 2
    assert len(palette["colors"]) == 3  # capped by unique foreground colours
    original = result.bible.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        create_character_skeleton(
            "Tzucan Test",
            "Una descripción distinta",
            workspace=tmp_path,
            reference=reference,
        )
    assert result.bible.read_text(encoding="utf-8") == original


def test_create_skeleton_without_reference_has_manual_palette(tmp_path: Path) -> None:
    result = create_character_skeleton(
        "npc-one",
        "NPC sin referencia",
        workspace=tmp_path,
    )
    palette = json.loads(result.palette.read_text(encoding="utf-8"))
    assert result.analysis is None
    assert palette["extraction"] == "manual"
    assert palette["colors"] == []
