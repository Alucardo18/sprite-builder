"""Centralized color manipulation, palettes, and chromatic harmonization for tilesets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


DEFAULT_TERRAIN_COLORS: dict[str, tuple[int, int, int]] = {
    "grass": (82, 135, 104),
    "dirt": (123, 115, 95),
    "water": (45, 104, 123),
    "sand": (198, 168, 112),
    "stone": (118, 122, 130),
    "lava": (196, 72, 34),
    "snow": (214, 226, 238),
    "dungeon": (74, 68, 82),
}


@dataclass(frozen=True, slots=True)
class TerrainPalette:
    """Coordinated color palette for a terrain biome or transition pair."""

    name: str
    primary_color: str
    secondary_color: str
    accent_color: str | None = None
    inside_material: str = "grass"
    outside_material: str = "dirt"
    recommended_preset: str = "zelda_topdown"
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "accent_color": self.accent_color or "",
            "inside_material": self.inside_material,
            "outside_material": self.outside_material,
            "recommended_preset": self.recommended_preset,
            "description": self.description,
        }


CURATED_BIOME_PALETTES: tuple[TerrainPalette, ...] = (
    TerrainPalette(
        name="Pradera / Bosque Templado",
        primary_color="#48A832",
        secondary_color="#8B5A2B",
        accent_color="#FDE047",
        inside_material="grass",
        outside_material="dirt",
        recommended_preset="zelda_topdown",
        description="Césped verde vivo clásico sobre tierra fértil estilo 16-bit top-down.",
    ),
    TerrainPalette(
        name="Costa / Playa Tropical",
        primary_color="#E5B869",
        secondary_color="#2B65EC",
        accent_color="#38BDF8",
        inside_material="sand",
        outside_material="water",
        recommended_preset="coastal_organic",
        description="Arena dorada soleada con transición a aguas marinas cristalinas.",
    ),
    TerrainPalette(
        name="Mazmorra Abisal / Cripta",
        primary_color="#505A69",
        secondary_color="#202530",
        accent_color="#A855F7",
        inside_material="stone",
        outside_material="dungeon",
        recommended_preset="neon_dungeon",
        description="Losas de piedra gótica con junta abisal y acentos fríos.",
    ),
    TerrainPalette(
        name="Tundra Nevada / Glaciar",
        primary_color="#E8F4F8",
        secondary_color="#6898B8",
        accent_color="#93C5FD",
        inside_material="snow",
        outside_material="stone",
        recommended_preset="retro_16bit",
        description="Manto de nieve blanca impoluta sobre roca helada.",
    ),
    TerrainPalette(
        name="Tierras Volcánicas / Magma",
        primary_color="#353038",
        secondary_color="#D84820",
        accent_color="#F97316",
        inside_material="stone",
        outside_material="lava",
        recommended_preset="retro_16bit",
        description="Roca basáltica oscura con grietas de lava incandescente.",
    ),
    TerrainPalette(
        name="Prototipado Limpio / Blueprint",
        primary_color="#60A5FA",
        secondary_color="#1E293B",
        accent_color="#F8FAFC",
        inside_material="stone",
        outside_material="dungeon",
        recommended_preset="clean_pixel",
        description="Estilo esquemático de alto contraste para level design y pruebas de colisión.",
    ),
)


def hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    """Parse a 3-hex or 6-hex color code into an RGB tuple."""
    clean = hex_code.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    if len(clean) != 6:
        raise ValueError(f"Invalid hex color code: {hex_code}")
    return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Format an RGB tuple into a standardized uppercase 7-character HEX string."""
    r, g, b = (max(0, min(255, int(channel))) for channel in rgb)
    return f"#{r:02x}{g:02x}{b:02x}".upper()


def normalize_hex_color(raw: str, fallback: str = "#48A832") -> str:
    """Normalize user input to a valid 7-character uppercase HEX string."""
    s = raw.strip()
    if not s:
        return fallback
    if not s.startswith("#"):
        s = "#" + s
    if len(s) == 4:
        s = f"#{s[1]*2}{s[2]*2}{s[3]*2}"
    if len(s) == 7:
        try:
            int(s[1:], 16)
            return s.upper()
        except ValueError:
            pass
    return fallback


def make_tint(rgb: tuple[int, int, int], factor: float) -> str:
    """Scale RGB channels by factor and return as a HEX string."""
    r, g, b = rgb
    return rgb_to_hex((
        max(0, min(255, round(r * factor))),
        max(0, min(255, round(g * factor))),
        max(0, min(255, round(b * factor))),
    ))


def get_default_terrain_rgb(material_key: str) -> tuple[int, int, int]:
    """Get the canonical RGB color for a given material key."""
    return DEFAULT_TERRAIN_COLORS.get(material_key.lower().strip(), DEFAULT_TERRAIN_COLORS["grass"])


def get_curated_palette(name_or_key: str) -> TerrainPalette | None:
    """Look up a curated palette by name or partial key."""
    query = name_or_key.lower().strip()
    for palette in CURATED_BIOME_PALETTES:
        if query in palette.name.lower() or query == palette.inside_material or query == palette.recommended_preset:
            return palette
    return None
