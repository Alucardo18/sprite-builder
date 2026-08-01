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
5. Configure el tablero fijo de **Tile Properties**: tile base y cuatro bordes.
   El compositor recorta la base y los Sources completos con la matriz de ocho
   vecinos; los corners se forman con los mismos empalmes diagonales.
6. Pulse cualquier slot y elija su Source haciendo clic directamente en un
   tile original del **Set View**. La miniatura asignada aparece en el tablero.
7. Si sólo tiene una muestra de borde, use **Completar 4 por rotación**. Los
   Cutoffs por orientación, Custom corners, rotación, Flip X y reemplazos por
   variante permanecen dentro de **Ajustes avanzados**.
8. Pinte y borre en el **Sandbox** para comprobar las transiciones.

El proyecto JSON conserva Sources, posiciones del Set View, sets generados,
transformaciones y correcciones, y sólo vuelve a abrirse sobre la misma imagen
verificada por SHA-256. La exportación conserva los layouts canónicos, el
manifiesto y el instalador para Godot 4.

El bundle contiene `terrain_tiles.png`, `terrain_bitmask_reference.png`,
`terrain_pattern.json`, `install_terrain_tileset.gd` y sus instrucciones. El
script crea
`terrain_tileset.tres` dentro de Godot después de importar el PNG. El manifest
conserva la relación entre máscara, tile fuente, coordenada canónica y peering
bits para generadores procedurales.

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
