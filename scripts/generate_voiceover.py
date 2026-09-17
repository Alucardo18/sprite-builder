import asyncio
import edge_tts
import os

SCENES = {
    "scene1": (
        "¿Alguna vez te has preguntado cómo los juegos estilo Zelda o Stardew Valley logran que sus mundos se sientan tan vivos y naturales? "
        "El secreto no es dibujar cada celda a mano, sino combinar tres transiciones fundamentales: "
        "pasto sobre tierra, tierra sobre agua y acantilados directos al agua. "
        "Hoy aprenderás a crear este ecosistema completo en minutos con el sistema Blob 47 de Sprite Builder."
    ),
    "scene2": (
        "Empezamos con la base de toda pradera: Pasto sobre Tierra. "
        "Al pulsar este botón, la herramienta sintetiza automáticamente cuarenta y siete piezas que resuelven todas las uniones: "
        "senderos angostos, claros de bosque y curvas amplias. "
        "Observa en el sandbox cómo los mechones verdes caen suavemente sobre la tierra firme, "
        "creando bordes redondeados que eliminan por completo el aspecto cuadrado del mapa."
    ),
    "scene3": (
        "Ahora creamos las costas con Tierra sobre Agua. "
        "Este set representa el suelo firme que se eleva por encima del mar o de un lago. "
        "Nota el detalle en las orillas: el sistema genera automáticamente una sombra proyectada y un biselado que le da profundidad al agua. "
        "Así, tu mapa gana volumen vertical de inmediato, simulando un banco de arena o una playa natural."
    ),
    "scene4": (
        "¿Y qué pasa si tienes islas flotantes o acantilados donde el pasto llega directamente al mar? "
        "Para eso usamos Pasto sobre Agua. "
        "Este patrón elimina la franja de tierra intermedia y conecta el césped verde brillante directo con el agua profunda. "
        "Es ideal para islas mágicas, bordes de ríos caudalosos o caídas empinadas hacia el océano."
    ),
    "scene5": (
        "Al juntar estos tres patrones, tienes el ecosistema completo: un mar con islas de tierra y praderas verdes en su interior. "
        "En Map Tester puedes pintar tu mundo en tiempo real y comprobar que todas las esquinas encajan a la perfección. "
        "Cuando estés listo, descarga tu tileset para Godot 4, Unity o Tiled en un solo clic. "
        "¡Así de fácil es construir terrenos profesionales con Sprite Builder!"
    ),
}

async def generate(voice: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    for key, text in SCENES.items():
        out_file = os.path.join(out_dir, f"{key}.mp3")
        print(f"Generating [{voice}] {key} -> {out_file}...")
        comm = edge_tts.Communicate(text, voice, rate="+2%")
        await comm.save(out_file)
        print(f"Saved {out_file}")

async def main():
    print("=== Generando locución principal con Jorge (es-MX-JorgeNeural) ===")
    await generate("es-MX-JorgeNeural", "tutorial-video/public/audio")

    print("\n=== Generando locución alternativa con Dalia (es-MX-DaliaNeural) ===")
    await generate("es-MX-DaliaNeural", "tutorial-video/public/audio/dalia")

if __name__ == "__main__":
    asyncio.run(main())
