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

## Contrato de interacción vigente

- El editor de **Fondo & Estudio** (Tab 1) ofrece la suite completa de herramientas de retoque pixel-art directamente sobre el sprite sheet: varita (`wand`), borrador (`eraser`), lápiz (`pencil`), cuentagotas (`eyedropper`), cubeta/relleno (`fill`), reemplazar color (`replace_color`), recorte (`crop_lasso`, `crop_rect`, `crop_ellipse`), selección (`select_lasso`, `select_rect`, `select_ellipse`), mover selección flotante (`move`), rotación libre y acciones de píxeles (voltear H/V, rotar 90°/180°, escalar 2×/½, contorno de 1 px y limpieza de píxeles aislados), además de paleta y selector de color.
- La tab de **Preparar & Alinear** (Tab 2) unifica la alineación multi-anchor de poses con perfiles de movimiento y el corte y grilla de poses.
- El cuentagotas muestra el RGBA muestreado del frame activo. Las máscaras son locales al frame y
  se normalizan cuando cambia la geometría; no basta validar solo el número de frames.
- Mantén separadas las keys de widgets Streamlit y el estado lógico. El modo ancho amplía el
  canvas sin ocultar la barra lateral; usa Liquid Glass en controles y conserva claridad pixel-art.

## Tileset Builder

> 📖 **Guía completa paso a paso**: Consulta [`docs/tile-builder-guide.md`](docs/tile-builder-guide.md) para aprender los 5 módulos (Asistente 1-Click, Procedural con Colores, Selección Manual Blob/Dual/Wang, Autotiles Animados y Map Tester con Exportación).

Abra **Tileset Builder** desde la navegación superior. La página conserva el
editor pixel-perfect de atlas y añade **Pattern Studio**, un flujo de
generación inspirado en el Set View de Tilesetter:

1. Defina el Tile Size y cargue una imagen en **Atlas**.
2. Use **Importar grilla** para convertir las celdas opacas en Sources, o
   arrastre sobre la imagen para guardar un Source de tamaño libre.
3. Para **Blob 47**, puede sintetizar todo el autotile desde **1 o 2 tiles**:
   - **1 tile (fondo transparente)**: Seleccione 1 tile en **Set View** y ejecute **Build Borders · Blob**. Genera las 47 máscaras completas con contornos orgánicos, sombra proyectada y cresta de luz (rim light) sin necesidad de recortar bordes manuales.
   - **2 tiles (Terreno A sobre Terreno B)**: Seleccione 2 tiles (por ejemplo, pasto y tierra) y ejecute **Build Blob 47 (A sobre B)** en Tile Properties. Sintetiza la transición completa entre ambos materiales.
   - Los sets Blob nuevos usan tres variantes orgánicas por máscara (141 tiles exportables).
   - Si prefiere el flujo clásico con recortes manuales de bordes, cambie el modo a **Bordes manuales (Legacy)** en Tile Properties.
4. Para Wang, seleccione dos tiles y ejecute **Build Borders · Wang**; esos
   tiles representan los dos terrenos de la transición.
5. Para **Dual Grid · 15**, seleccione exactamente dos terrenos y ejecute
   **Build Dual Grid · 15**. Genera las 15 transiciones desde ambas texturas;
   el atlas 4×4 conserva también el slot de fondo lógico (máscara 0) que espera
   TileMapDual, pero éste no cuenta como transición. Este perfil sólo cubre la
   cuadrícula **Square** de cuatro esquinas; no use este atlas para TileMapDual
   isométrico, hexagonal ni triangular. Cada tile debe medir al menos **2×2 px**.
6. En cualquier set generado, abra **Estrategia del borde** y elija
   **Orgánico neutral**, **Pasto sobre tierra**, **Tierra sobre agua** o
   **Pasto sobre agua**.
   En Wang y Dual, Terreno A debe ser el material indicado antes de “sobre” y
   Terreno B el material de fondo. En Blob/Sides la misma gramática se aplica
   sobre el Tile base y sus Border Sources; el primer borde configurado sirve
   como referencia de paleta cuando no hay un segundo terreno. El nivel
   `1` es sutil, `2` moderado y `3` texturizado; la semilla cambia la variante de
   forma determinista. El perfil clásico y el nivel `0` conservan el borde limpio.
   Los perfiles materiales generan bandas duras de paleta —sombra, ribete,
   banco o raíz— derivadas de los Sources. No usan blur, antialiasing ni alpha blend;
   las máscaras puras permanecen intactas.
   En Blob, **Variantes por máscara** controla uno, dos o tres bancos. Cada
   banco conserva los mismos puertos y peering bits; sólo cambia el recorrido
   interior del contorno. El Sandbox reparte las variantes de forma
   determinista para que la repetición sea visible antes de exportar. En modo
   síntesis inteligente, configure **Sombra proyectada** (0–4 px), **Dirección de
   sombra** (Sur, Sur-Este u Omnidireccional con enfriamiento tonal pixel-art) y
   **Cresta de luz superior (Rim light)** para lograr volumen e iluminación profesional.
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
verificada por SHA-256. El tamaño predeterminado es **16×16 px** y los presets
incluyen **32×32, 64×64 y 128×128 px**; los
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
En Blob orgánico, el atlas coloca tres layouts canónicos en bancos
horizontales. El instalador registra las 141 celdas con probabilidad uniforme,
y el manifiesto conserva `variant`, `variant_seed` y la semilla principal.

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
3. Limpie y guarde la hoja completa en **Fondo**.
   Puede activar una capa de grid visual de 16, 32, 64 o 128 px; la guía no altera
   los píxeles ni aparece en el archivo exportado.
4. En **Preparar & Alinear**, el lienzo unificado inicia con cortes automáticos calculados
   y guías anatómicas simultáneas (cian estabiliza, ámbar valida y magenta muestra el anchor fusionado):
   - **Modo Anchors (por defecto)**: ajuste fino de la posición de cada frame arrastrándolo directamente o mediante offsets X/Y con guías anatómicas.
   - **Modo Cortes**: ajuste interactivo de las líneas divisorias de la grilla sobre la hoja completa.
   - **Modo Pintar capas**: retoque de pixel-art y capas de anatomía.
   - Debajo del lienzo, use la **Tira de frames extraídos** con deltas y el **Mini-reproductor en vivo** a FPS ajustable para verificar la estabilidad de la animación en tiempo real.
5. Pulse **Guardar poses y alineación** para confirmar de forma atómica ambas etapas y avanzar a exportación.
6. En **Exportación**, defina layout (horizontal, vertical o grid), columnas, recorte inteligente y opciones de empaquetado (hoja PNG, frames .zip, contact sheet o GIF en bucle).

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

El método recomendado fusiona torso, raíz de pelvis y soporte del suelo. Hombros
y base de cabeza validan la anatomía sin arrastrar el cuerpo. Los perfiles cambian
el peso por eje: `idle` prioriza torso, `walk` pelvis/suelo y `attack` el núcleo
corporal. Armas y VFX finos no determinan el anchor; bounding box simple existe
sólo como fallback explícito.

En **Ajuste fino**:

- X positivo mueve el frame a la derecha.
- Y positivo lo mueve hacia abajo.
- El frame activo se puede arrastrar libremente sobre el canvas completo.
- Al pasar el cursor, la celda muestra `Frame N`; el primer clic selecciona un
  frame y el siguiente gesto permite arrastrarlo.
- El clic derecho abre acciones rápidas para seleccionar, autoalinear,
  restablecer o bloquear el anchor del frame bajo el cursor.
- `[` y `]` cambian al frame anterior o siguiente sin usar el selector.
- **Autoalinear todo** recalcula la alineación multi-anchor de todos los frames y
  conserva el resultado como offsets manuales en cero.
- Las capas **Centros de columnas (X)** y **Centros de filas (Y)** dibujan guías
  continuas sobre todo el canvas y pueden activarse por separado.
- **Reset frame** vuelve a `(0, 0)`.
- **Copiar a todos** aplica el offset actual a toda la secuencia.
- **Revisado y bloqueado** confirma un anchor de baja confianza.

Nunca reduzca un único frame para hacer caber un arma: amplíe el canvas para
todos los frames o separe esa capa.

Cambiar la configuración después de guardar una alineación no bloquea Cortes ni
Export: ambos usan la última revisión guardada y muestran la diferencia como
advertencia. Los anchors de baja confianza también quedan registrados como
`manual_review`, pero el usuario puede exportar bajo su criterio.

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
- **Export bloqueado**: guarde fondo, mapa provisional y alineación;
  revise además los anchors marcados `manual_review`.

## Limitaciones actuales

- La corrección manual mueve el frame completo en X/Y enteros; no rota ni escala.
- El muestreo de chroma usa selector o esquina superior izquierda.
- Siluetas muy inusuales pueden requerir revisión manual.
- Se recomienda una sesión activa por pestaña del navegador.
