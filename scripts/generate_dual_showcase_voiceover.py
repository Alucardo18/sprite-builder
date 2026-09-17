#!/usr/bin/env python3
"""Generate voiceover audio files for Dual Showcase tutorial using edge-tts."""

import asyncio
import os
import subprocess
from pathlib import Path

VOICE_JORGE = "es-MX-JorgeNeural"
VOICE_DALIA = "es-MX-DaliaNeural"

SCRIPT_PARTS = [
    (
        "showcase_scene1",
        "¿Buscas acelerar el arte de tu videojuego 2D sin perder calidad ni control? Conoce Sprite Builder: la herramienta todo en uno diseñada para transformar hojas de sprites en personajes animados fluidos, y texturas simples en mundos vivos con autotiling automático. ¡Vamos a verlo!",
    ),
    (
        "showcase_scene2",
        "Comenzamos en Sheet Studio con nuestro guerrero azteca. En un solo clic eliminamos el fondo oscuro con el cuentagotas y limpiamos cualquier residuo de halo sin tocar el contorno original. Luego, el motor alinea automáticamente cada pose tomando como ancla el torso y la pelvis. Así, cuando el personaje camina o ataca, su centro de gravedad es perfecto y no tiembla en pantalla.",
    ),
    (
        "showcase_scene3",
        "Aquí entra la magia del Estudio: abrimos el reproductor integrado para ver el personaje cobrar vida en tiempo real como un GIF fluido. Podemos ajustar la velocidad en FPS, activar Onion Skin para comparar cuadros vecinos y retocar cualquier detalle píxel por píxel con herramientas de dibujo y capas independientes.",
    ),
    (
        "showcase_scene4",
        "Ahora pasamos a Tileset Builder. Si necesitas terrenos orgánicos como praderas, playas o acantilados, el algoritmo Blob 47 genera de inmediato las 47 combinaciones posibles a partir de tus texturas. Al dibujar en el lienzo, las esquinas y transiciones se unen solas de forma totalmente natural.",
    ),
    (
        "showcase_scene5",
        "¿Prefieres máxima velocidad y ligereza? Cambiamos a Dual Grid 15. Con tan solo dos tiles base, el sistema crea las 15 variantes de esquina requeridas por el estándar de grilla dual. Es la forma más rápida y económica en memoria para maquetar niveles masivos en motores como Godot 4.",
    ),
    (
        "showcase_scene6",
        "Para comprobarlo todo, abrimos el Map Tester y pintamos libremente en un mapa interactivo. Cuando estemos conformes, exportamos el paquete completo con un clic, con los metadatos y scripts listos para Godot, Unity o Tiled. ¡Arte 2D impecable y listo para tu juego!",
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
    base_dir = Path(__file__).parent.parent / "tutorial-video" / "public" / "audio"
    dalia_dir = base_dir / "dalia"
    base_dir.mkdir(parents=True, exist_ok=True)
    dalia_dir.mkdir(parents=True, exist_ok=True)

    print("--- Generating Jorge de México (es-MX-JorgeNeural) for Dual Showcase ---")
    durations = {}
    for name, text in SCRIPT_PARTS:
        out_file = str(base_dir / f"{name}.mp3")
        await generate_speech(text, VOICE_JORGE, out_file)
        dur = get_duration(out_file)
        durations[name] = dur
        print(f"  {name}: {dur:.2f}s ({round(dur * 60)} frames @ 60fps)")

    print("\n--- Generating Dalia (es-MX-DaliaNeural) backup ---")
    for name, text in SCRIPT_PARTS:
        out_file = str(dalia_dir / f"{name}.mp3")
        await generate_speech(text, VOICE_DALIA, out_file)

    print("\n=== SUMMARY OF JORGE TRACK DURATIONS ===")
    total_sec = sum(durations.values())
    for name, dur in durations.items():
        frames = round(dur * 60)
        print(f"'{name}': {dur:.2f}s ({frames} frames)")
    print(f"Total Speech Time: {total_sec:.2f}s (~{round(total_sec * 60)} frames)")


if __name__ == "__main__":
    asyncio.run(main())
