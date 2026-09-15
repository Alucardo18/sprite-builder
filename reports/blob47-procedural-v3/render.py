"""Review the production procedural Blob path using generated materials."""
from pathlib import Path

import numpy as np
from PIL import Image

from sprite_builder.tilesets import build_tilesetter_terrain_pattern
from sprite_builder.tilesets.patterns import _normalize_blob_mask

output = Path(__file__).parent
for profile in ("grass_over_dirt", "dirt_over_water", "grass_over_water"):
    result = build_tilesetter_terrain_pattern(
        Image.new("RGBA", (1, 1)), tile_size=(16, 16), sources=[],
        set_config={"blobMaterialMode": "procedural", "terrainProfile": profile,
                    "variantCount": 3, "edgeVariation": 2, "edgeSeed": 0},
        kind="blob_47",
    )
    result.image.save(output / f"{profile}-native.png")
    Image.fromarray(np.asarray(result.image).repeat(8, 0).repeat(8, 1)).save(
        output / f"{profile}-atlas-8x.png"
    )
    tiles = {}
    for role in result.tiles:
        x, y = role.column * 16, role.row * 16
        tiles[role.mask, role.variant] = result.image.crop((x, y, x + 16, y + 16))
    grid = np.zeros((11, 15), bool)
    grid[1:10, 2:13] = True
    grid[4:7, 6:9] = False
    mosaic = Image.new("RGBA", (15 * 16, 11 * 16))
    for y in range(11):
        for x in range(15):
            mask = 0
            if grid[y, x]:
                for bit, (dy, dx) in enumerate(((-1, 0), (-1, 1), (0, 1), (1, 1),
                                                (1, 0), (1, -1), (0, -1), (-1, -1))):
                    if 0 <= y + dy < 11 and 0 <= x + dx < 15 and grid[y + dy, x + dx]:
                        mask |= 1 << bit
            variant = ((x + 1) * 73856093 ^ (y + 1) * 19349663) % 3
            mosaic.paste(tiles[_normalize_blob_mask(mask), variant], (x * 16, y * 16))
    mosaic_4x = Image.fromarray(np.asarray(mosaic).repeat(4, 0).repeat(4, 1))
    mosaic_4x.save(output / f"{profile}-mosaic.png")
    mosaic_4x.save(output / f"{profile}-island-hole-mosaic.png")
    outer_masks = (28, 112, 193, 7)
    inner_masks = (247, 253, 127, 223)
    for label, masks in (("outer-corners", outer_masks), ("inner-corners", inner_masks)):
        contact = Image.new("RGBA", (4 * 18, 3 * 18), (30, 35, 40, 255))
        for variant in range(3):
            for col, mask in enumerate(masks):
                contact.paste(tiles[mask, variant], (col * 18, variant * 18))
        Image.fromarray(np.asarray(contact).repeat(8, 0).repeat(8, 1)).save(
            output / f"{profile}-{label}-8x.png"
        )
