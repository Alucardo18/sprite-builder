import asyncio
import edge_tts
import os

SPRITE_SCENES = {
    "sprite_scene1": (
        "¡Bienvenidos a Sprite Builder! Si creas sprites o animaciones 2D para tus videojuegos, "
        "sabes que pasar de una ilustración a una animación fluida puede ser un proceso tedioso. "
        "En este tutorial aprenderás el flujo completo de Sheet Studio: desde limpiar el fondo y separar las poses, "
        "hasta alinear el personaje por su centro de gravedad y exportar para Godot y Unity sin perder un solo píxel."
    ),
    "sprite_scene2": (
        "Comenzamos con la remoción de fondo. En la pestaña Fondo, podemos seleccionar el color a eliminar "
        "o tomarlo directamente desde la esquina superior de la imagen. "
        "Con los controles de tolerancia y limpieza de fringe, eliminamos los molestos halos claros alrededor de nuestro personaje, "
        "preservando siempre el delineado oscuro original. Todo el proceso es no destructivo y mantiene la paleta limpia."
    ),
    "sprite_scene3": (
        "El siguiente paso es Preparar Poses. Aquí definimos la cuadrícula inicial para separar cada cuadro de animación: "
        "en nuestro caso, dieciséis poses en cuatro filas y cuatro columnas. "
        "Podemos inspeccionar y ajustar las cajas provisionales sobre el lienzo interactivo para garantizar que cada postura "
        "esté bien delimitada antes de pasar a la alineación geométrica."
    ),
    "sprite_scene4": (
        "Llegamos al paso clave: la alineación multi-anchor. "
        "Un error muy común es alinear los sprites usando la caja envolvente exterior, lo que provoca que el personaje tiemble "
        "cuando mueve un arma o báculo. Sprite Builder analiza el torso, la pelvis y la base del cuerpo para fijar el centro de gravedad. "
        "Elegimos el perfil de animación, pulsamos Autoalinear todo, y cada pose queda perfectamente balanceada en su celda."
    ),
    "sprite_scene5": (
        "Por último, revisamos Cortes Finales y la pestaña Export. "
        "El sistema genera una celda uniforme para toda la animación sin estirar ni deformar el arte original. "
        "Con un solo clic podemos descargar el paquete con regiones AtlasTexture para Godot, o los cuadros PNG individuales listos para usar. "
        "¡Tu personaje ahora tiene animaciones limpias, estables y listas para entrar en acción!"
    ),
}

async def generate(voice: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    for key, text in SPRITE_SCENES.items():
        out_file = os.path.join(out_dir, f"{key}.mp3")
        print(f"Generating [{voice}] {key} -> {out_file}...")
        comm = edge_tts.Communicate(text, voice, rate="+2%")
        await comm.save(out_file)
        print(f"Saved {out_file}")

async def main():
    print("=== Generando locución de Sprite Builder con Jorge (es-MX-JorgeNeural) ===")
    await generate("es-MX-JorgeNeural", "tutorial-video/public/audio")

    print("\n=== Generando locución de respaldo con Dalia (es-MX-DaliaNeural) ===")
    await generate("es-MX-DaliaNeural", "tutorial-video/public/audio/dalia")

if __name__ == "__main__":
    asyncio.run(main())
