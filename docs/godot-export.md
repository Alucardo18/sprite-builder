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

## Terrenos y mapas procedurales

Para tiles no se usa el bitmap de autotile de Godot 3. Godot 4 lo reemplazó por
`Terrain Set`, donde cada tile declara sus terrain peering bits:

- Wang de 16 roles exporta `TERRAIN_MODE_MATCH_CORNERS`.
- Blob de 47 roles exporta `TERRAIN_MODE_MATCH_CORNERS_AND_SIDES`.
- Sides de 16 roles exporta `TERRAIN_MODE_MATCH_SIDES`.

**Pattern Studio** separa Sources, Tiles y Generated Sets. La imagen puede
dividirse automáticamente por la grilla o convertirse en Sources mediante
recortes libres. Los Tiles que las referencian se organizan en el Set View:

- Un tile seleccionado crea un Blob Set de 47 variantes.
- Dos tiles seleccionados crean un Wang Set de 16 transiciones.
- Tile Properties muestra permanentemente el tile base y los cuatro bordes.
  Los ocho corners interiores/exteriores se generan con los mismos clips
  diagonales que unen los bordes.
- Una posición se asigna activándola y haciendo clic en el Source tile deseado
  dentro del propio Set View.
- Los bordes pueden completarse desde una muestra mediante rotaciones
  automáticas de 0°, 90°, 180° y 270°. Los Custom corners son overrides
  opcionales dentro de Ajustes avanzados.

Los layouts exportados son:

- Blob 47: plantilla oficial `3×3 minimal` de Godot 3, 12×4 y un slot vacío.
- Wang/Corners: plantilla oficial `2×2`, 4×4.
- Sides: plantilla `3×3 minimal` de 16 tiles, 4×4 y esquinas ignoradas.

Durante la edición, Blob 47 usa la composición visual de Tilesetter de 11×5.
Esas coordenadas sólo organizan el Generated Set; el PNG exportado conserva la
plantilla Godot de 12×4 y sus peering bits.

Cada borde Blob referencia un Source completo que incluye terreno y exterior.
El compositor reproduce el flujo de capas de Tilesetter: recorta primero la
base según los vecinos cardinales e interiores, mide el alfa de cada Source
para calcular los puntos de unión horizontal y vertical, y después aplica los
clips rectos o diagonales de cada variante en orden. `Cutoff` pertenece a cada
orientación y determina cuánto terreno de la base cede al Source de ese borde.
El control rápido aplica un mismo valor a los cuatro y cada borde puede
ajustarse individualmente.

En Godot 3 estas plantillas se configuraban como bitmasks de Autotile. Godot 4
no importa un bitmap de máscaras separado: las mismas relaciones se escriben
como Terrain Peering Bits. Por eso el PNG artístico conserva el layout familiar,
pero el instalador y `terrain_pattern.json` son los que configuran el
comportamiento en Godot 4.

Cada borde admite un Source diferente, rotación, Flip X y Cutoff. Si el empalme
automático no encaja con el arte, cualquiera de los cuatro corners interiores
o exteriores puede añadir un Custom corner como capa. Una variante también
puede sustituirse con un Source completo, sin alterar las demás combinaciones
del set. La lista lateral de Sources sirve para crear y organizar recortes; la
asignación visual se realiza desde la grilla.

El Sandbox usa el set activo y sus correcciones para validar el autotiling
antes de exportar. El bundle incluye un `EditorScript` que crea el atlas
normalizado, registra todos los tiles y asigna terreno `0` o espacio vacío `-1`
a cada dirección. Para instalarlo:

1. Copie el contenido del ZIP a una misma carpeta del proyecto.
2. Espere a que Godot importe `terrain_tiles.png`.
3. Abra `install_terrain_tileset.gd` y elija **File > Run**.
4. Asigne el nuevo `terrain_tileset.tres` a un `TileMapLayer`.
5. Use el terreno `0` con las APIs `set_cells_terrain_connect()` o
   `set_cells_terrain_path()` para mapas procedurales.

`terrain_pattern.json` es independiente de Godot y registra la máscara, el tile
fuente elegido, la coordenada del atlas normalizado y los peering bits de cada
rol. Puede usarse directamente si el generador de mapas selecciona tiles por
vecindad. El JSON de proyecto descargable conserva los bounds de cada Source,
las posiciones de Tiles, las configuraciones Blob/Wang, las correcciones y el
SHA-256 de la imagen original.

`terrain_bitmask_reference.png` es una guía visual para comparar el tileset con
las plantillas clásicas. No es un recurso que Godot 4 necesite importar.

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
