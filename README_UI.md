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
