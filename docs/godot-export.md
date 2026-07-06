# Exportación a Godot 4.6

El proyecto de referencia usa Godot 4.6, `AnimatedSprite2D`, `SpriteFrames` y
subrecursos `AtlasTexture`. El exportador reproduce esa estructura.

## Recursos

Por cada animación:

- un PNG RGBA horizontal o grid;
- metadata JSON portable;
- un `.sprite_frames.tres`;
- previews opcionales.

Ejemplo del `.tres`:

```text
[gd_resource type="SpriteFrames" load_steps=6 format=3]

[ext_resource type="Texture2D" path="res://assets/generated/walk_right.png" id="1_atlas"]

[sub_resource type="AtlasTexture" id="AtlasTexture_0000"]
atlas = ExtResource("1_atlas")
region = Rect2(0, 0, 128, 128)

[resource]
animations = [{
"frames": [{
"duration": 1.0,
"texture": SubResource("AtlasTexture_0000")
}],
"loop": true,
"name": &"walk_right",
"speed": 8.0
}]
```

`duration` es un multiplicador relativo; `speed` contiene los FPS.

## Instalación en el juego

1. Copie PNG y `.tres` a una carpeta dentro del proyecto Godot.
2. Asegure que el path usado al exportar coincide con el path `res://` real.
3. Abra el proyecto para que Godot importe el PNG.
4. Asigne el `.tres` a `AnimatedSprite2D.sprite_frames`.
5. Aplique a `AnimatedSprite2D.offset` el `godot_offset` del metadata. Para
   Tzucan 128×128 con torso anchor `[64,68]`, el valor es `[0,-4]`.
6. Seleccione la animación y reproduzca a la velocidad exportada.

No copie ni genere `.import`: contiene estado gestionado por Godot y puede
cambiar entre máquinas.

## Filtrado y pixel art

El PNG final está a resolución lógica. Use nearest-neighbor en Godot; el juego
de referencia ya configura el filtrado global para pixel art. Si se integra en
otro proyecto, configure el filtro de texturas de CanvasItem como nearest.

## Metadata

El JSON incluye tamaño del sheet/celda, layout, FPS, loop, hashes, regiones,
torso/foot anchors, foreground bbox, pivot y `godot_offset`. Godot no necesita
leerlo para mostrar la animación, pero sirve para offsets, sockets, hitboxes,
VFX y auditoría.

## Verificación

- El sheet mide `columnas × ancho` por `filas × alto`.
- Todas las regiones quedan dentro del PNG.
- El número de regiones coincide con frames.
- La textura del `.tres` empieza con `res://`.
- Godot carga el recurso sin errores.
- El loop y FPS coinciden con el job.
- El personaje no salta al extender un arma.
