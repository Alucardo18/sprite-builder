from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from sprite_builder.domain.errors import ArtifactIntegrityError
from sprite_builder.sheets import SheetSessionStore
from sprite_builder.sheets import session as session_module
from sprite_builder.ui import app


def _png_bytes(
    size: tuple[int, int] = (8, 8),
    color: tuple[int, int, int, int] = (12, 34, 56, 255),
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def test_session_listing_is_reused_and_invalidated_by_new_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SheetSessionStore(tmp_path)
    original_glob = Path.glob
    glob_calls = 0

    def counted_glob(path: Path, pattern: str):
        nonlocal glob_calls
        glob_calls += 1
        return original_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", counted_glob)

    assert store.list_sessions() == ()
    assert store.list_sessions() == ()
    assert glob_calls == 1

    session = store.create(_png_bytes(), source_name="hero.png")

    assert store.list_sessions() == (session.session_id,)
    assert glob_calls == 2


def test_load_and_source_path_share_one_hash_but_reverify_after_source_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SheetSessionStore(tmp_path)
    session = store.create(_png_bytes(), source_name="hero.png")
    original_sha256_file = session_module.sha256_file
    hash_calls = 0

    def counted_sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
        nonlocal hash_calls
        hash_calls += 1
        return original_sha256_file(path, chunk_size)

    monkeypatch.setattr(session_module, "sha256_file", counted_sha256_file)

    loaded = store.load(session.session_id)
    source_path = store.source_path(loaded)

    assert source_path.is_file()
    assert hash_calls == 1

    source_path.write_bytes(_png_bytes(size=(9, 8), color=(90, 80, 70, 255)))
    with pytest.raises(ArtifactIntegrityError):
        store.source_path(loaded)
    assert hash_calls == 2


def test_load_source_caches_bytes_but_returns_fresh_pil_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SheetSessionStore(tmp_path)
    session = store.create(_png_bytes(size=(10, 6)), source_name="hero.png")
    loaded = store.load(session.session_id)
    app._read_source_bytes.clear()

    original_read_bytes = Path.read_bytes
    read_calls = 0

    def counted_read_bytes(path: Path) -> bytes:
        nonlocal read_calls
        read_calls += 1
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)

    first = app._load_source(store, loaded)
    second = app._load_source(store, loaded)

    assert first.size == second.size == (10, 6)
    assert first is not second
    assert first.tobytes() == second.tobytes()
    assert read_calls == 1
