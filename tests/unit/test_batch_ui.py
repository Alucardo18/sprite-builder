"""Unit tests for UI batch configuration replication and ZIP export."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image

from sprite_builder.sheets import (
    BackgroundRemovalConfig,
    SegmentationConfig,
    SheetSessionStore,
)
from sprite_builder.ui.app import _build_batch_export_zip, _replicate_session_config


def test_replicate_session_config_syncs_background_and_grid(tmp_path: Path) -> None:
    store = SheetSessionStore(tmp_path)
    img1 = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
    img2 = Image.new("RGBA", (64, 64), (0, 255, 0, 255))

    buf1, buf2 = io.BytesIO(), io.BytesIO()
    img1.save(buf1, format="PNG")
    img2.save(buf2, format="PNG")

    s1 = store.create(buf1.getvalue(), source_name="char_idle.png")
    s2 = store.create(buf2.getvalue(), source_name="char_walk.png")

    # Modify s1 configs
    s1.background_removal_config = BackgroundRemovalConfig(color=(12, 34, 56), tolerance=45.0)
    s1.segmentation_config = SegmentationConfig(frame_count=8, rows=2, columns=4)
    store.save(s1)

    # Replicate to s2
    updated = _replicate_session_config(
        store,
        s1,
        [s2.session_id],
        copy_background=True,
        copy_segmentation=True,
    )

    assert updated == 1
    loaded_s2 = store.load(s2.session_id)
    assert loaded_s2.background_removal_config.color == (12, 34, 56)
    assert loaded_s2.background_removal_config.tolerance == 45.0
    assert loaded_s2.segmentation_config.rows == 2
    assert loaded_s2.segmentation_config.columns == 4


def test_build_batch_export_zip_creates_valid_archive(tmp_path: Path) -> None:
    store = SheetSessionStore(tmp_path)
    img = Image.new("RGBA", (32, 32), (0, 0, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    s1 = store.create(buf.getvalue(), source_name="hero_attack.png")
    zip_bytes = _build_batch_export_zip(store, [s1.session_id])

    assert len(zip_bytes) > 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as archive:
        names = archive.namelist()
        assert any("session.json" in name for name in names)
        assert any("frame_" in name or "sheet.png" in name for name in names)
