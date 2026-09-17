#!/usr/bin/env python3
"""Generate voiceover audio files for the new Showcase tutorial using edge-tts."""

import asyncio
import os
import subprocess
from pathlib import Path

VOICE_JORGE = "es-MX-JorgeNeural"

SCRIPT_PARTS = [
    (
        "scene1_intro",
        "¿Quieres acelerar el arte de tu videojuego sin perder calidad? Conoce \"Sprite Builder\" y \"Tile Builder\": dos potentes herramientas para transformar tus hojas de sprites en animaciones fluidas y tus texturas en mundos interactivos."
    ),
    (
        "scene2_sprites_poses",
        "Comenzamos en \"Sheet Studio\" cargando esta hoja de doce poses de un zorro místico. En la pestaña de Fondo verificamos la transparencia limpia sin alterar ningún detalle. Luego, en Preparar Poses, el sistema detecta la cuadrícula de seis columnas por dos filas, delimitando cada postura con precisión milimétrica."
    ),
    (
        "scene3_sprites_gif",
        "Pasamos a Alineación y abrimos el \"Layer Studio\". Aquí la animación cobra vida de inmediato en un bucle continuo tipo \"GIF\". Activamos \"Onion Skin\" para comparar cuadros adyacentes y calibramos la velocidad a ocho fotogramas por segundo. Finalmente, en Export, marcamos la casilla de preview \"GIF\" y descargamos nuestra animación."
    ),
    (
        "scene4_tiles_wheel",
        "Ahora saltamos a \"Tile Builder\". En el asistente seleccionamos generación procedural. Usando el \"Wheel Picker\" elegimos interactivamente el color base y el tono secundario. Después seleccionamos la variante de textura, como la receta visual Zelda Top-Down. Pulsamos Crear Terreno y el sistema sintetiza el patrón al instante."
    ),
    (
        "scene5_tiles_map",
        "En \"Pattern Studio\" observamos el atlas completo con sus cuarenta y siete combinaciones orgánicas y variantes de textura. Al pasar a \"Map Tester\", el autotiling conecta automáticamente costas, praderas e islas con solo pintar en el lienzo. ¡Flujo completo, limpio y listo para tu juego!"
    ),
]

async def generate_speech(text: str, voice: str, output_path: str):
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate="+2%")
    await communicate.save(output_path)
    print(f"Generated {output_path}")

def get_duration(audio_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())

async def main():
    out_dir = Path("hyperframes-showcase/assets/audio_v2")
    out_dir.mkdir(parents=True, exist_ok=True)

    durations = {}
    for name, text in SCRIPT_PARTS:
        path = str(out_dir / f"{name}.mp3")
        await generate_speech(text, VOICE_JORGE, path)
        dur = get_duration(path)
        durations[name] = dur
        print(f"  [{name}] duration: {dur:.2f}s")

    print("\nSummary of audio durations:")
    total = 0
    for k, v in durations.items():
        print(f"  {k}: {v:.2f}s")
        total += v
    print(f"Total narration duration: {total:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
