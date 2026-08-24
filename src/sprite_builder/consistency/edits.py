"""Pixel-exact verification for surgical sprite repairs and material edits."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(frozen=True, slots=True)
class MaskedEditReport:
    status: str
    before_sha256: str
    after_sha256: str
    mask_sha256: str
    changed_pixels: int
    changed_inside_mask: int
    changed_outside_mask: int
    alpha_mismatch_pixels: int
    changed_bbox: tuple[int, int, int, int] | None

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["changed_bbox"] = list(self.changed_bbox) if self.changed_bbox else None
        return value


def _read(path: str | Path) -> tuple[np.ndarray, str]:
    source = Path(path)
    payload = source.read_bytes()
    with Image.open(source) as image:
        array = np.asarray(image.convert("RGBA")).copy()
    return array, hashlib.sha256(payload).hexdigest()


def verify_masked_edit(
    before_path: str | Path,
    after_path: str | Path,
    mask_path: str | Path,
    *,
    require_alpha_identity: bool = True,
) -> MaskedEditReport:
    before, before_sha = _read(before_path)
    after, after_sha = _read(after_path)
    mask_rgba, mask_sha = _read(mask_path)
    if before.shape != after.shape or before.shape[:2] != mask_rgba.shape[:2]:
        raise ValueError("Before, after, and edit mask dimensions must match")
    allowed = mask_rgba[:, :, 3] > 0
    changed = np.any(before != after, axis=2)
    changed_inside = int(np.count_nonzero(changed & allowed))
    changed_outside = int(np.count_nonzero(changed & ~allowed))
    alpha_mismatch = int(np.count_nonzero(before[:, :, 3] != after[:, :, 3]))
    points = np.argwhere(changed)
    bbox = None
    if len(points):
        y0, x0 = points.min(axis=0)
        y1, x1 = points.max(axis=0) + 1
        bbox = int(x0), int(y0), int(x1), int(y1)
    status = "pass"
    if changed_outside or (require_alpha_identity and alpha_mismatch):
        status = "reject"
    elif not changed_inside:
        status = "review"
    return MaskedEditReport(
        status=status,
        before_sha256=before_sha,
        after_sha256=after_sha,
        mask_sha256=mask_sha,
        changed_pixels=int(np.count_nonzero(changed)),
        changed_inside_mask=changed_inside,
        changed_outside_mask=changed_outside,
        alpha_mismatch_pixels=alpha_mismatch,
        changed_bbox=bbox,
    )


def render_masked_edit_overlay(
    before_path: str | Path,
    after_path: str | Path,
    mask_path: str | Path,
    output_path: str | Path,
    *,
    scale: int = 4,
) -> Path:
    """Render cyan authorized changes and red protected-pixel violations."""

    if scale < 1:
        raise ValueError("Overlay scale must be >= 1")
    before, _before_sha = _read(before_path)
    after, _after_sha = _read(after_path)
    mask_rgba, _mask_sha = _read(mask_path)
    if before.shape != after.shape or before.shape[:2] != mask_rgba.shape[:2]:
        raise ValueError("Before, after, and edit mask dimensions must match")
    allowed = mask_rgba[:, :, 3] > 0
    changed = np.any(before != after, axis=2)
    overlay = after.copy()
    overlay[:, :, :3] = np.rint(overlay[:, :, :3].astype(float) * 0.45).astype(np.uint8)
    overlay[:, :, 3] = np.maximum(overlay[:, :, 3], 160)
    overlay[changed & allowed] = (0, 220, 255, 255)
    overlay[changed & ~allowed] = (255, 35, 70, 255)
    image = Image.fromarray(overlay, "RGBA")
    if scale != 1:
        image = image.resize(
            (image.width * scale, image.height * scale), Image.Resampling.NEAREST
        )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=False)
    return destination
