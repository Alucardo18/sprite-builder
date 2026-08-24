# sprite-builder UI

Editor web local para convertir sprite sheets existentes en PNG transparentes,
alineados y listos para importarse manualmente en Godot.

## Instalación

Requiere Python 3.12 o posterior:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[ui,dev]'
```

## Abrir la interfaz

Desde la raíz del proyecto:

```bash
sprite-builder ui
```

Si quieres dejar el servicio levantado sin abrir el navegador, usa:

```bash
./.venv/bin/sprite-builder ui --no-browser
```

La UI queda disponible en [http://127.0.0.1:8501/](http://127.0.0.1:8501/).

## Tileset Builder

Abra **Tileset Builder** desde la navegación superior. La página conserva el
editor pixel-perfect de atlas y añade **Pattern Studio**, un flujo de
generación inspirado en el Set View de Tilesetter:

1. Defina el Tile Size y cargue una imagen en **Atlas**.
2. Use **Importar grilla** para convertir las celdas opacas en Sources, o
   arrastre sobre la imagen para guardar un Source de tamaño libre.
3. Seleccione un tile en **Set View** y ejecute **Build Borders · Blob** para
   crear 47 variantes con placeholders.
4. Para Wang, seleccione dos tiles y ejecute **Build Borders · Wang**; esos
   tiles representan los dos terrenos de la transición.
5. Para **Dual Grid · 15**, seleccione exactamente dos terrenos y ejecute
   **Build Dual Grid · 15**. Genera las 15 transiciones desde ambas texturas;
   el atlas 4×4 conserva también el slot de fondo lógico (máscara 0) que espera
   TileMapDual, pero éste no cuenta como transición. Este perfil sólo cubre la
   cuadrícula **Square** de cuatro esquinas; no use este atlas para TileMapDual
   isométrico, hexagonal ni triangular. Cada tile debe medir al menos **2×2 px**.
6. En cualquier set generado, abra **Estrategia del borde** y elija
   **Pasto sobre tierra**, **Tierra sobre agua** o **Pasto sobre agua**.
   En Wang y Dual, Terreno A debe ser el material indicado antes de “sobre” y
   Terreno B el material de fondo. En Blob/Sides la misma gramática se aplica
   sobre el Tile base y sus Border Sources; el primer borde configurado sirve
   como referencia de paleta cuando no hay un segundo terreno. El nivel
   `1` es sutil, `2` moderado y `3` texturizado; la semilla cambia la variante de
   forma determinista. El perfil clásico y el nivel `0` conservan el borde limpio.
   Los perfiles materiales generan bandas duras de paleta —sombra, ribete,
   banco o raíz— derivadas de los Sources. No usan blur, antialiasing ni alpha blend;
   las máscaras puras permanecen intactas.
7. Para **Blob/Wang**, configure **Tile Properties**: el tile base y los cuatro
   Border Sources. Blob compone sus corners con esos empalmes diagonales; Wang
   parte además de sus terrenos A/B. Sides usa el mismo tile base y sus cuatro
   bordes. Dual Grid sólo expone Terreno A y Terreno B.
8. En Blob/Wang/Sides, pulse un slot y elija su Source haciendo clic directamente en
   un tile original del **Set View**. En Dual, los únicos ajustes de arte son
   reemplazos opcionales de las máscaras **1–15**; máscara 0 es el fondo de
   referencia derivado de Terreno B y no se puede editar.
9. Si Blob o Wang sólo tiene una muestra de borde, use **Completar 4 por
   rotación**. Los Cutoffs, rotación y Flip X permanecen en **Ajustes avanzados**;
   los Custom corners son exclusivos de Blob y los reemplazos por variante están
   disponibles para los roles editables de cada patrón.
10. Pinte y borre en el **Sandbox** para comprobar las transiciones. En Dual
   Grid se pinta la cuadrícula lógica: el display muestra una fila y una
   columna adicionales, desplazadas medio tile, y calcula cada tile con el
   orden interno NW, NE, SE, SW. El export traduce ese orden al contrato de
   TileMapDual; no reordene el arte a mano.

El proyecto JSON conserva Sources, posiciones del Set View, sets generados,
transformaciones y correcciones, y sólo vuelve a abrirse sobre la misma imagen
verificada por SHA-256. Restaura el **Tile Size** cuadrado de 1 a 64 px; los
Sources usan bounds absolutos en píxeles, por lo que los offsets y spacings del
editor de Atlas no forman parte de ese proyecto. La exportación conserva los
layouts canónicos, el manifiesto y el instalador para Godot 4.
La investigación visual y los límites pixel-perfect de los perfiles están en
[`docs/dual-grid-edge-profiles.md`](docs/dual-grid-edge-profiles.md).

El bundle contiene `terrain_tiles.png`, `terrain_bitmask_reference.png`,
`terrain_pattern.json`, `install_terrain_tileset.gd` y sus instrucciones. El
script crea `terrain_tileset.tres` dentro de Godot después de importar el PNG.
El manifest conserva la relación entre máscara, tile fuente, coordenada
canónica y peering bits para generadores procedurales. Para Blob, Wang y Sides,
el recurso funciona con los Terrains nativos de `TileMapLayer`. Para Dual Grid,
el bundle prepara el atlas y metadata; el runtime sigue siendo
[TileMapDual](https://github.com/pablogila/TileMapDual) o un adaptador propio
que mantenga las cuadrículas lógica y de display. No instala ni reemplaza ese
plugin/nodo.

Para elegir otro workspace:

```bash
sprite-builder --workspace /ruta/al/proyecto ui
```

La UI escucha únicamente en `127.0.0.1` por default. Opciones:

```bash
sprite-builder ui --port 8502
sprite-builder ui --no-browser
```

Procesamiento headless opcional sobre el mismo core:

```bash
sprite-builder sheet-session-create --image sheet.png
sprite-builder sheet-process --session <id> --frame-count 4 --orientation horizontal
sprite-builder sheet-export --session <id> --layout horizontal
```

## Flujo rápido

1. Suba una sprite sheet PNG desde la barra lateral.
2. Pulse **Crear sesión con este PNG**.
3. Primero limpie el fondo en **Background** con varita, borrador o cuentagotas.
4. Indique el número de frames y elija horizontal, vertical o grid.
5. Ajuste tamaño de celda, offsets, spacing, filas y columnas.
6. Revise la segmentación en **Sheet** sobre el sheet ya transparente.
7. En **Segmentación + Auto Center**, arrastre cada frame, use las guías y ajuste offsets.
8. Bloquee manualmente cualquier frame revisado de baja confianza.
9. En **Export**, active el recorte inteligente si hay demasiado espacio transparente.
10. Pulse **Exportar sprite .png**.

La sesión queda bajo `sheet_sessions/<session_id>/` y puede reabrirse desde la
barra lateral. El PNG fuente, los intentos, overrides y exports conservan
SHA-256 y lineage.

## Segmentación

- **Horizontal**: distribuye N frames de izquierda a derecha.
- **Vertical**: distribuye N frames de arriba hacia abajo.
- **Grid**: usa filas y columnas en orden row-major.
- **Auto-calcular tamaño de celda** descuenta offsets y spacing.

Si la división deja píxeles sobrantes, la UI muestra un warning. Un corte fuera
de la imagen se rechaza como `CELL_OVERFLOW`.

## Remoción de fondo

El modo pixel-art usa distancia RGB, alpha duro y flood fill desde el borde.
Esto evita borrar chroma encerrado dentro del personaje. Cleanup reemplaza RGB
contaminado en el fringe sin blur ni alpha suavizado.

- Aumente tolerancia si queda fondo.
- Redúzcala si desaparece outline.
- Mantenga **Preservar outline** activo para pixel art.
- Use **Quitar casi transparentes** para suciedad alpha residual.

## Centrado y ajuste fino

El método recomendado busca la masa corporal mediante componentes conectados,
percentiles y distance transform. Armas y VFX finos no determinan el anchor.
Bounding box simple existe sólo como fallback explícito.

En **Ajuste fino**:

- X positivo mueve el frame a la derecha.
- Y positivo lo mueve hacia abajo.
- **Reset frame** vuelve a `(0, 0)`.
- **Copiar a todos** aplica el offset actual a toda la secuencia.
- **Revisado y bloqueado** confirma un anchor de baja confianza.

Nunca reduzca un único frame para hacer caber un arma: amplíe el canvas para
todos los frames o separe esa capa.

## Exportación

Se puede exportar:

- Sprite sheet PNG RGBA.
- Frames individuales.
- Manifest JSON.
- Contact/anchor sheet.
- Preview GIF.

No se aplica resampling. Todos los frames usan la misma celda.

## Importación manual en Godot

1. Copie únicamente el PNG final dentro del proyecto de Godot.
2. Cree o seleccione un nodo `AnimatedSprite2D`.
3. Cree un recurso `SpriteFrames`.
4. Elija **Add frames from a Sprite Sheet**.
5. Indique las columnas y filas registradas en el manifest.
6. Use compresión lossless y filtrado nearest para pixel art.
7. Configure FPS y loop.

No copie archivos `.import`; Godot los administra.

## Problemas comunes

- **Fringe verde**: suba cleanup un paso o ajuste ligeramente tolerancia.
- **Jitter**: revise el punto de torso, no el bbox de arma/efecto.
- **Mal corte**: verifique cell size, offsets y spacing.
- **Frame vacío**: revise las líneas de corte y el color chroma.
- **Canvas insuficiente**: aumente ancho/alto para toda la secuencia.
- **Export bloqueado**: revise y bloquee los anchors marcados `manual_review`.

## Limitaciones actuales

- El movimiento fino se hace con inputs numéricos X/Y.
- El muestreo de chroma usa selector o esquina superior izquierda.
- Siluetas muy inusuales pueden requerir revisión manual.
- Se recomienda una sesión activa por pestaña del navegador.
