#!/usr/bin/env python3
"""Prepare high-resolution sprite and tileset assets for HyperFrames composition."""

import json
import shutil
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np

from sprite_builder.tilesets.patterns import generate_terrain_pattern
from sprite_builder.tilesets.autotile import autotile_dual_grid, autotile_blob47

ROOT = Path(__file__).resolve().parent.parent
HF_ASSETS = ROOT / "hyperframes-showcase" / "assets"
SPRITES_DIR = HF_ASSETS / "sprites"
TILES_DIR = HF_ASSETS / "tiles"
AUDIO_DIR = HF_ASSETS / "audio"

SPRITES_DIR.mkdir(parents=True, exist_ok=True)
TILES_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# 1. Copy Voiceover Audios
src_audio = ROOT / "tutorial-video" / "public" / "audio"
for i in range(1, 7):
    name = f"showcase_scene{i}.mp3"
    shutil.copy(src_audio / name, AUDIO_DIR / name)
print("✓ Audio files copied.")

# 2. Copy Aztec Warrior Source Sheet & Aligned Frames
session_dir = ROOT / "sheet_sessions" / "sheet-20260913T034239-7de8d336-6d58"
source_img = session_dir / "source" / "7de8d336b7753f1ab14065d0b166123bd9f51633e6c616710d69da58baecb04d.png"
shutil.copy(source_img, SPRITES_DIR / "source_sheet.png")

# Find aligned frames
align_dir = session_dir / "attempts" / "alignment" / "4c0192006d2dbb760f5a8c22dd51e08fe369daffe7a8084b7990d710f3e7c243"
frames = []
for i in range(16):
    f_path = align_dir / f"frame_{i:03d}.png"
    if f_path.exists():
        shutil.copy(f_path, SPRITES_DIR / f"frame_{i:02d}.png")
        frames.append(Image.open(f_path).convert("RGBA"))
print(f"✓ Copied {len(frames)} aligned sprite frames.")

# Create Animated GIFs for the character
if len(frames) >= 8:
    walk_frames = frames[:8]
    walk_frames[0].save(
        SPRITES_DIR / "warrior_walk.gif",
        save_all=True,
        append_images=walk_frames[1:],
        duration=125, # 8 fps
        loop=0,
        disposal=2,
    )
    print("✓ Created warrior_walk.gif (8 FPS)")

if len(frames) == 16:
    frames[0].save(
        SPRITES_DIR / "warrior_full_cycle.gif",
        save_all=True,
        append_images=frames[1:],
        duration=125,
        loop=0,
        disposal=2,
    )
    print("✓ Created warrior_full_cycle.gif (8 FPS)")

if len(frames) == 16:
    fw, fh = frames[0].size
    contact = Image.new("RGBA", (fw * 4, fh * 4), (0, 0, 0, 0))
    for idx, f in enumerate(frames):
        row = idx // 4
        col = idx % 4
        contact.paste(f, (col * fw, row * fh))
    contact.save(SPRITES_DIR / "aligned_sheet.png")
    print("✓ Created aligned_sheet.png")

if len(frames) > 0:
    frames[0].save(SPRITES_DIR / "clean_frame_0.png")
    src_sheet = Image.open(source_img).convert("RGBA")
    sw, sh = src_sheet.size
    cell_w, cell_h = sw // 4, sh // 4
    raw_frame_0 = src_sheet.crop((0, 0, cell_w, cell_h))
    raw_frame_0.save(SPRITES_DIR / "raw_frame_0.png")
    print("✓ Created raw_frame_0.png and clean_frame_0.png")

# 3. Generate Real Tileset Atlases
tile_size = (32, 32)

def make_texture(primary_hex: str, secondary_hex: str):
    img = Image.new("RGBA", tile_size, primary_hex)
    draw = ImageDraw.Draw(img)
    p_rgb = Image.new("RGBA", (1, 1), primary_hex).getpixel((0, 0))
    s_rgb = Image.new("RGBA", (1, 1), secondary_hex).getpixel((0, 0))
    
    np.random.seed(42)
    for y in range(tile_size[1]):
        for x in range(tile_size[0]):
            r = np.random.rand()
            if r > 0.75:
                draw.point((x, y), fill=s_rgb)
    return img

grass = make_texture("#4a8505", "#3a6804")
dirt = make_texture("#8b5a2b", "#6e441f")
water = make_texture("#2b75a0", "#1d587c")

grass.save(TILES_DIR / "base_grass.png")
dirt.save(TILES_DIR / "base_dirt.png")
water.save(TILES_DIR / "base_water.png")

# B. Blob 47: Grass over Dirt
blob_res = generate_terrain_pattern(
    interior=grass,
    exterior=dirt,
    kind="blob_47",
    tile_size=tile_size,
    columns=12,
    terrain_profile="grass_over_dirt",
    edge_variation=2,
    edge_seed=777,
)
blob_res.image.save(TILES_DIR / "blob47_grass_dirt.png")
print(f"✓ Generated blob47_grass_dirt.png ({blob_res.image.size[0]}x{blob_res.image.size[1]})")

# C. Dual Grid 15: Grass over Dirt (omit columns for dual_grid_15)
dual_res = generate_terrain_pattern(
    interior=grass,
    exterior=dirt,
    kind="dual_grid_15",
    tile_size=tile_size,
    terrain_profile="clean",
)
dual_res.image.save(TILES_DIR / "dualgrid15_grass_dirt.png")
print(f"✓ Generated dualgrid15_grass_dirt.png ({dual_res.image.size[0]}x{dual_res.image.size[1]})")

# D. Generate a beautiful autotiled sample map with Blob 47 and Dual Grid
matrix = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
    [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0],
    [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0],
    [0, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0],
    [0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0],
    [0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0],
    [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0],
    [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
]

dual_map = autotile_dual_grid(matrix, dual_res.image, tile_size)
dual_map.save(TILES_DIR / "sample_map_dualgrid.png")
print("✓ Generated sample_map_dualgrid.png")

blob_map = autotile_blob47(matrix, blob_res.image, tile_size)
blob_map.save(TILES_DIR / "sample_map_blob47.png")
print("✓ Generated sample_map_blob47.png")

print("\nAll showcase assets successfully prepared in hyperframes-showcase/assets/!")
