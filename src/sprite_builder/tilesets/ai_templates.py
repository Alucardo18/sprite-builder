"""AI prompt templates and texture preparation for tileset generation."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from PIL import Image, ImageDraw

MaterialRole = Literal["base", "secondary", "edge", "custom"]


@dataclass(frozen=True, slots=True)
class MaterialTemplate:
    """Curated material definition for generating seamless top-down tile textures."""

    id: str
    name: str
    category: str
    base_prompt: str
    default_role: MaterialRole
    suggested_profile: str
    description: str


MATERIAL_TEMPLATES: tuple[MaterialTemplate, ...] = (
    MaterialTemplate(
        id="grass_meadow",
        name="Césped / Pradera",
        category="Naturaleza",
        base_prompt=(
            "lush vibrant green top-down RPG meadow grass texture, seamless flat pixel art, "
            "16-bit retro game style, subtle clover accents, no directional shadows, uniform ground tile"
        ),
        default_role="base",
        suggested_profile="grass_over_dirt",
        description="Césped verde vivo clásico para exteriores y praderas estilo RPG 16-bit.",
    ),
    MaterialTemplate(
        id="dirt_earth",
        name="Tierra / Suelo",
        category="Naturaleza",
        base_prompt=(
            "rich warm brown loam dirt soil ground texture, seamless flat pixel art, "
            "16-bit retro top-down RPG path ground, subtle pebble grains, no directional shadows"
        ),
        default_role="secondary",
        suggested_profile="clean",
        description="Tierra fértil marrón con granulado sutil, ideal como terreno secundario o camino.",
    ),
    MaterialTemplate(
        id="stone_cobblestone",
        name="Adoquines / Piedra",
        category="Arquitectura",
        base_prompt=(
            "weathered gray cobblestone paving stones texture, top-down castle or village road, "
            "seamless flat pixel art, clean mortar lines, 16-bit retro fantasy style"
        ),
        default_role="base",
        suggested_profile="clean",
        description="Adoquines de roca pulida para caminos de aldea, plazas o patios de castillo.",
    ),
    MaterialTemplate(
        id="water_ocean",
        name="Agua / Océano",
        category="Naturaleza",
        base_prompt=(
            "clear vibrant cyan-blue animated water surface texture, gentle sunlight caustics, "
            "top-down 16-bit pixel art sea lake, seamless flat tile texture"
        ),
        default_role="secondary",
        suggested_profile="grass_over_water",
        description="Agua azul cristalina con sutiles cáusticas para costas, lagos y ríos.",
    ),
    MaterialTemplate(
        id="sand_desert",
        name="Arena / Playa",
        category="Naturaleza",
        base_prompt=(
            "warm golden desert sand ground texture, subtle wind ripples, "
            "top-down 16-bit RPG beach ground, seamless flat pixel art, uniform lighting"
        ),
        default_role="secondary",
        suggested_profile="clean",
        description="Arena dorada con suaves ondulaciones para playas o desiertos.",
    ),
    MaterialTemplate(
        id="snow_ice",
        name="Nieve / Hielo",
        category="Naturaleza",
        base_prompt=(
            "crisp clean white snow ground texture, soft pale cyan crystal highlights, "
            "top-down winter RPG ground, seamless flat pixel art, 16-bit retro"
        ),
        default_role="base",
        suggested_profile="clean",
        description="Manto de nieve blanca invernal con sutiles brillos celestes.",
    ),
    MaterialTemplate(
        id="dungeon_slate",
        name="Mazmorra / Losas Oscuras",
        category="Mazmorra",
        base_prompt=(
            "dark obsidian slate stone tile floor, clean carved borders, "
            "top-down fantasy catacomb or dungeon, seamless flat pixel art, 16-bit gothic style"
        ),
        default_role="base",
        suggested_profile="clean",
        description="Losas oscuras de catacumba o templo subterráneo con juntas marcadas.",
    ),
    MaterialTemplate(
        id="wood_planks",
        name="Madera / Tablones",
        category="Arquitectura",
        base_prompt=(
            "warm rustic oak wooden floor planks, horizontal wood grain, "
            "top-down medieval tavern interior floor, seamless flat pixel art, 16-bit retro"
        ),
        default_role="base",
        suggested_profile="clean",
        description="Suelo de tablones de roble rústico para interiores de tabernas o casas.",
    ),
    MaterialTemplate(
        id="lava_magma",
        name="Lava / Magma",
        category="Fantasía",
        base_prompt=(
            "incandescent glowing orange-red molten lava crust, dark basalt rock cracks, "
            "top-down volcano fantasy level, seamless flat pixel art, warm internal glow"
        ),
        default_role="secondary",
        suggested_profile="clean",
        description="Lava incandescente con costras basálticas oscuras para áreas volcánicas.",
    ),
    MaterialTemplate(
        id="scifi_metal",
        name="Metal Sci-Fi / Placas",
        category="Sci-Fi",
        base_prompt=(
            "futuristic dark steel panel plating, recessed seams, subtle bolts, "
            "top-down spaceship or industrial floor, seamless flat pixel art, clean metallic finish"
        ),
        default_role="base",
        suggested_profile="clean",
        description="Paneles metálicos industriales con remaches para naves espaciales o búnkeres.",
    ),
)

_TEMPLATES_BY_ID = {template.id: template for template in MATERIAL_TEMPLATES}


def get_material_template(template_id: str) -> MaterialTemplate | None:
    """Look up a curated material template by id."""
    return _TEMPLATES_BY_ID.get(template_id)


def list_material_templates() -> tuple[MaterialTemplate, ...]:
    """Return all available material templates."""
    return MATERIAL_TEMPLATES


def format_tile_prompt(
    template_id: str,
    *,
    custom_instruction: str = "",
    tile_size: tuple[int, int] = (32, 32),
    palette_style: str = "16-bit retro",
) -> str:
    """Format an optimized text prompt for AI tile texture generation."""
    template = get_material_template(template_id)
    base_text = template.base_prompt if template is not None else template_id.replace("_", " ")

    w, h = max(1, tile_size[0]), max(1, tile_size[1])
    constraints = (
        f"seamless repeatable texture swatch, exactly {w}x{h} pixel art scale, {palette_style}, "
        "orthographic top-down camera, flat even diffuse lighting with zero directional cast shadows, "
        "crisp clean pixel clustering, no text, no watermark, isolated game texture pattern"
    )

    if custom_instruction.strip():
        return f"{base_text}. {custom_instruction.strip()}. {constraints}"
    return f"{base_text}. {constraints}"


def generate_procedural_reference_tile(
    template_id: str,
    tile_size: tuple[int, int] = (32, 32),
    *,
    seed: int = 42,
) -> Image.Image:
    """Deterministically synthesize a procedural texture swatch.

    Provides immediate offline fallback and deterministic test generation.
    """
    width, height = max(1, int(tile_size[0])), max(1, int(tile_size[1]))
    rng = random.Random(seed)

    palettes: dict[str, tuple[tuple[int, int, int], ...]] = {
        "grass_meadow": (
            (74, 150, 48),
            (90, 172, 58),
            (62, 132, 40),
            (108, 194, 72),
        ),
        "dirt_earth": (
            (142, 94, 56),
            (124, 80, 46),
            (160, 110, 68),
            (106, 68, 38),
        ),
        "stone_cobblestone": (
            (115, 122, 134),
            (138, 145, 158),
            (92, 98, 110),
            (68, 72, 82),
        ),
        "water_ocean": (
            (42, 118, 188),
            (56, 142, 214),
            (32, 98, 162),
            (88, 178, 240),
        ),
        "sand_desert": (
            (218, 184, 118),
            (204, 170, 104),
            (232, 198, 134),
            (188, 154, 92),
        ),
        "snow_ice": (
            (225, 235, 248),
            (240, 246, 255),
            (205, 218, 236),
            (185, 202, 224),
        ),
        "dungeon_slate": (
            (54, 56, 68),
            (42, 44, 54),
            (68, 72, 86),
            (30, 32, 40),
        ),
        "wood_planks": (
            (168, 116, 70),
            (148, 100, 58),
            (186, 132, 82),
            (112, 74, 42),
        ),
        "lava_magma": (
            (220, 70, 20),
            (255, 140, 20),
            (170, 35, 15),
            (60, 25, 25),
        ),
        "scifi_metal": (
            (120, 135, 150),
            (140, 155, 172),
            (98, 112, 126),
            (70, 80, 92),
        ),
    }

    colors = palettes.get(template_id, ((100, 100, 100), (130, 130, 130), (70, 70, 70)))
    base_color = colors[0]

    img = Image.new("RGBA", (width, height), (*base_color, 255))
    pixels = np.array(img)

    for y in range(height):
        for x in range(width):
            noise_idx = rng.randint(0, len(colors) - 1)
            selected = colors[noise_idx]
            # subtle dithering
            jitter = rng.randint(-6, 6)
            r = min(255, max(0, selected[0] + jitter))
            g = min(255, max(0, selected[1] + jitter))
            b = min(255, max(0, selected[2] + jitter))
            pixels[y, x] = [r, g, b, 255]

    # Add material-specific structural cues
    if template_id == "stone_cobblestone":
        # Draw subtle stone block boundaries
        step = max(4, width // 4)
        for y in range(0, height, step):
            for x in range(width):
                pixels[y, x] = [50, 54, 62, 255]
        for y in range(height):
            row_idx = y // step
            offset = (step // 2) if (row_idx % 2 == 1) else 0
            for x in range(offset, width, step):
                pixels[y, x] = [50, 54, 62, 255]
    elif template_id == "wood_planks":
        # Horizontal plank lines
        step = max(4, height // 4)
        for y in range(0, height, step):
            for x in range(width):
                pixels[y, x] = [90, 58, 32, 255]

    return Image.fromarray(pixels, mode="RGBA")


def prepare_tile_source_record(
    image: Image.Image,
    tile_size: tuple[int, int],
    *,
    source_id: str,
    name: str,
    rect: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    """Create a structured Source record compatible with Pattern Studio."""
    tw, th = max(1, tile_size[0]), max(1, tile_size[1])
    if rect is None:
        rect = (0, 0, min(image.width, tw), min(image.height, th))

    return {
        "id": source_id,
        "name": name,
        "rect": [int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])],
        "crop": [int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])],
    }
