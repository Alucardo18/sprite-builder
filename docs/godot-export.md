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

Para Blob, Wang y Sides, el instalador crea un `Terrain Set` de Godot 4 donde
cada tile declara sus *terrain peering bits*:

- Wang de 16 roles exporta `TERRAIN_MODE_MATCH_CORNERS`.
- Blob de 47 roles exporta `TERRAIN_MODE_MATCH_CORNERS_AND_SIDES`.
- Sides de 16 roles exporta `TERRAIN_MODE_MATCH_SIDES`.
- Dual Grid usa `TERRAIN_MODE_MATCH_CORNERS` como metadata del atlas, pero no
  convierte un `TileMapLayer` nativo en un runtime dual-grid.

El perfil Dual Grid exportado aquí es únicamente **Square**: usa cuatro
vecinos/corners y el offset rectangular de medio tile. Aunque TileMapDual v5
admite también topologías isométricas, hexagonales y triangulares, sus
vecindades, layouts y offsets de display no coinciden con este atlas 4×4; no
los mezcle.

**Pattern Studio** separa Sources, Tiles y Generated Sets. La imagen puede
dividirse automáticamente por la grilla o convertirse en Sources mediante
recortes libres. Los Tiles que las referencian se organizan en el Set View:

- Un tile seleccionado crea un Blob Set de 47 variantes.
- Dos tiles seleccionados crean un Wang Set de 16 transiciones.
- Exactamente dos tiles seleccionados crean un Dual Grid Set: 15 transiciones
  desde ambas texturas, más el slot de fondo lógico (máscara 0) del atlas
  estándar 4×4 compatible con TileMapDual. Los Border Sources no son
  obligatorios para este tipo de set. Cada celda Dual debe medir al menos
  2×2 px.
- En Blob y Wang, Tile Properties muestra el tile base y los cuatro Border
  Sources. Blob genera sus ocho corners interiores/exteriores con clips
  diagonales; Wang parte también de sus terrenos A/B para componer las
  transiciones. Sides usa el mismo tile base y cuatro bordes, e ignora las
  esquinas para componer sólo relaciones cardinales.
- En Blob/Wang, una posición se asigna activándola y haciendo clic en el Source
  tile deseado dentro del propio Set View. Dual Grid sólo mantiene Terreno A,
  Terreno B y reemplazos opcionales para máscaras 1–15; máscara 0 es el fondo
  de referencia derivado de Terreno B y no admite override.
- Los bordes de Blob/Wang/Sides pueden completarse desde una muestra mediante
  rotaciones automáticas de 0°, 90°, 180° y 270°. Los Custom corners son
  overrides opcionales exclusivos de Blob dentro de Ajustes avanzados.

Los layouts exportados son:

- Blob 47: plantilla oficial `3×3 minimal` de Godot 3, 12×4 y un slot vacío.
- Wang/Corners: plantilla oficial `2×2`, 4×4.
- Dual Grid: layout `2×2` 4×4, con las transiciones 1–15 y fondo lógico
  máscara 0 en el slot inferior izquierdo. La máscara artística interna de
  sprite-builder usa NW, NE, SE, SW; el perfil TileMapDual v5 traduce a su
  orden de peers NW, NE, SW, SE. El tile lleno máscara 15 ocupa la coordenada
  `(2, 1)`; no reordene el arte manualmente.
- Sides: plantilla `3×3 minimal` de 16 tiles, 4×4 y esquinas ignoradas.

Durante la edición, Blob 47 usa la composición visual de Tilesetter de 11×5.
Esas coordenadas sólo organizan el Generated Set; el PNG exportado conserva la
plantilla Godot de 12×4 y sus peering bits.

Cada borde Blob/Sides referencia un Source completo que incluye terreno y
exterior.
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
pero el instalador y `terrain_pattern.json` son los que configuran los Terrains
nativos de Godot 4. Eso no sustituye la lógica de un Dual Grid: para ese flujo
la máscara visual se obtiene de cuatro celdas lógicas, no de la búsqueda nativa
de combinación de un único `TileMapLayer`.

En Blob/Wang/Sides, cada borde admite un Source diferente, rotación, Flip X y
Cutoff. Si el empalme automático de Blob no encaja con el arte, cualquiera de
sus cuatro corners interiores o exteriores puede añadir un Custom corner como
capa. Una variante editable puede sustituirse con un Source completo, sin
alterar las demás combinaciones del set. En Dual Grid, esa sustitución sólo se
admite en máscaras 1–15: la máscara 0 siempre es la referencia de fondo de
Terreno B. La lista lateral de Sources sirve para crear y organizar recortes;
la asignación visual se realiza desde la grilla.

### Perfiles de borde Dual Grid y otros patrones

**Estrategia del borde** aplica una gramática distinta a la silueta entre
materiales. En Wang y Dual Grid esos materiales son Terreno A y Terreno B; en
Blob/Sides se compone sobre el Tile base y los Border Sources configurados:

- **Pasto sobre tierra** usa irregularidad de frecuencia alta en grupos cortos,
  raíz oscura y mechones iluminados, con pequeñas entradas de tierra.
- **Tierra sobre agua** prioriza una ribera continua y curvas más largas; reduce
  los dientes aislados y construye sombra acuática, ribete claro y banco terroso.
- **Pasto sobre agua** conserva salientes vegetales cortos, pero con menos
  rugosidad, una línea húmeda intermitente y raíz vegetal oscura.
- **Borde limpio** mantiene exactamente la interpolación anterior de cada patrón.

El nivel de textura está limitado a `0..3`. El nivel `1` ya crea contraste real;
el `3` combina una desviación de hasta unos 2–3 px con bandas duras de 1–4 px según
el tamaño del tile. La semilla `0..999999` elige otra variante reproducible. Los
perfiles pueden derivar tonos RGB de los Sources para construir sombra, ribete y
banco o raíz, pero conservan el alpha, no usan blur, antialiasing ni alpha blend.
En Blob y Wang con Border Sources authored, la cobertura de la banda se toma de
los píxeles de borde realmente poseídos —no de una curva canónica separada—;
los Borders y corners originales quedan intactos y no aparece una segunda línea
en el centro del tile. Las rotaciones de 90 grados conservan el patrón. El
manifiesto Dual conserva sus claves dentro de `dual_grid`; los demás patrones las
escriben en `edge_profile`. En ambos casos se conservan
`terrain_profile`, `edge_variation` y `edge_seed` para reproducir el resultado.

El Sandbox usa el set activo y sus correcciones para validar el autotiling
antes de exportar. Para Dual Grid, la zona de pintura es la cuadrícula lógica y
el display tiene una fila y columna extra para que ninguna transición del borde
se recorte. El bundle incluye un `EditorScript` que crea el atlas normalizado
y registra todos los tiles. Blob, Wang y Sides usan sus peering bits nativos
con terreno `0` o espacio vacío `-1` según su patrón. Dual Grid usa un perfil
distinto: los cuatro peering bits de cada una de sus 16 celdas físicas siempre
son `0` o `1`; sólo `tile_data.terrain` vale `-1` para las transiciones 1–14.
La máscara 0 es el terreno lógico de fondo `0` y la máscara 15 el foreground
`1`.

Para instalar Blob, Wang o Sides en un `TileMapLayer` nativo:

1. Copie el contenido del ZIP a una misma carpeta del proyecto.
2. Espere a que Godot importe `terrain_tiles.png`.
3. Abra `install_terrain_tileset.gd` y elija **File > Run**.
4. Asigne el nuevo `terrain_tileset.tres` a un `TileMapLayer`.
5. Use el terreno `0` con las APIs `set_cells_terrain_connect()` o
   `set_cells_terrain_path()` para mapas procedurales.

Para usar **Dual Grid** con [TileMapDual](https://github.com/pablogila/TileMapDual):

1. Instale y active el plugin TileMapDual en el proyecto Godot; sprite-builder
   no lo incluye en el ZIP ni genera su nodo runtime.
2. Importe el atlas 4×4 y configúrelo siguiendo la plantilla *Standard* del
   plugin, incluyendo el slot de fondo lógico máscara 0 y el tile lleno
   máscara 15 en `(2, 1)`.
3. Cree un nodo `TileMapDual` con ese tileset y pinte/actualice su cuadrícula
   lógica. El plugin mantiene las capas world/display y aplica su offset de
   medio tile automáticamente.
4. Si no usa el plugin, implemente el adaptador equivalente: por cada celda de
   display, lea las cuatro celdas lógicas NW, NE, SE y SW, forme la máscara y
   coloque su tile. Al interoperar con TileMapDual v5, traduzca al orden de
   peers NW, NE, SW, SE registrado en `terrain_pattern.json`. No llame
   `set_cells_terrain_connect()` como sustituto de ese bucle dual-grid.

`terrain_pattern.json` es independiente de Godot y registra la máscara, el tile
fuente elegido, la coordenada del atlas normalizado y los peering bits de cada
rol. En Dual Grid incluye además la convención de cuadrícula lógica, el offset
de display, el orden de esquinas interno y el orden de peers TileMapDual, junto
con la máscara de fondo. Puede usarse directamente si el generador de mapas
selecciona tiles por vecindad. El JSON de proyecto descargable conserva los
bounds de cada Source, las posiciones de Tiles, las configuraciones
Blob/Wang/Dual Grid, las correcciones y el SHA-256 de la imagen original.

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
