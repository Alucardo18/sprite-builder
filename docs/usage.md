# Guía de uso

## 1. Crear y analizar un personaje

Organice el canon así:

```text
characters/tzucan/
├── bible.yaml
├── palette.json
├── references/
│   └── caminarBalamDerecha.png
└── overrides/
```

La Bible debe bloquear: silueta, proporción cabeza/cuerpo, prendas, colores,
armas, accesorios, perspectiva e iluminación. Marque los rasgos como
obligatorios, opcionales o prohibidos. La paleta usa colores sRGB y tolerancia
ΔE00; reserve el chroma de fondo para que no coincida con el personaje.

Puede medir una referencia sin red:

```bash
sprite-builder reference-analyze --image <referencia.png> \
  --palette-colors 16 --output reports/reference.json
```

Para crear archivos iniciales no destructivos:

```bash
sprite-builder character-create --id <id> --description "<descripción>" \
  --reference <referencia.png> --palette-colors 16
```

Esto crea `characters/<id>/bible.yaml` y `palette.json` en estado draft; se
niega a sobrescribir archivos existentes. Después pida a la skill
`sprite-builder` inspeccionar la referencia con `view_image` y confirme
layout, silueta, proporciones, paleta, outline, iluminación, prendas y zona
estable del torso antes de bloquear el canon.

## 2. Definir un job

Ejemplo mínimo:

```yaml
schema_version: "1.0"
job:
  id: tzucan-walk-right-v001
character:
  id: tzucan
  bible: characters/tzucan/bible.yaml
  references:
    - characters/tzucan/references/caminarBalamDerecha.png
animation:
  name: walk
  directions: [right]
  frame_count: 4
  fps: 8
  loop: true
  phases: [contact_left, passing_left, contact_right, recovery]
generation:
  source_size: [1024, 1024]
  # La hoja completa es la fuente creativa; su tamaño no se recorta después.
  quality: medium
  mode: sheet
  candidates_per_sheet: 1
  sheet:
    layout: horizontal
    rows: 1
    columns: 4
    gutter_px: 0
  prompt:
    style: "16-bit pixel art, hard pixel clusters, crisp stepped silhouettes, no anti-aliasing"
    pixel_language: "Deliberate 1px/2px clusters, selective dithering, nearest-neighbor pixel logic"
    camera: "One fixed orthographic top-down three-quarter camera and identical scale in every cell"
    palette: "Locked Character Bible palette with stable hue families and material roles"
    lighting: "One stable light direction and value hierarchy across the sheet"
    identity: "Same head, torso, hair, clothing, equipment proportions, outline weight, and body scale"
    animation: "Change only the anatomy and equipment required by each listed phase; preserve contacts"
    negative: "No text, labels, scenery, borders, extra characters, checkerboard, collage, or cropped body parts"
  background:
    mode: transparent_preferred
    fallback: manual_ui
    max_attempts: 3  # initial generation plus two alpha retries
    color: "#00FF00"
render:
  cell_size: [128, 128]
  target_body_height_px: 74
  palette_lock: true
  dithering: false
  integrated_shadow: true
  palette_max_delta_e00: 10
  resampling:
    methods: [premultiplied_area, premultiplied_lanczos, pixel_majority, edge_aware]
    selection: auto
    save_variants: true
alignment:
  method: torso_hybrid_v1
  canonical_canvas_anchor: [64, 68]
  confidence_review_threshold: 0.65
  allow_manual_override: true
export:
  formats: [individual, horizontal, godot]
  output_dir: exports/tzucan/walk_right
  godot:
    project_root: /ruta/al/proyecto/godot
    resource_dir: res://assets/textures/sprites/player/generated
```

## 3. Generar dentro de Codex

Primero prepare y revise la cola determinista:

```bash
sprite-builder prepare --job configs/examples/tzucan_walk_right.yaml
sprite-builder queue --job-id tzucan-walk-right-v001
```

Después abra el repositorio en Codex y formule una petición como:

> Usa la skill local sprite-builder para ejecutar
> `configs/examples/tzucan_walk_right.yaml`. Usa la referencia aprobada,
> genera una hoja horizontal completa por dirección con GPT Image 2, conserva la
> resolución nativa y detente ante revisión manual.

La skill ejecuta un bucle por hoja:

1. Validar el job y leer la Bible.
2. Compilar un único prompt detallado con canon, estilo 16-bit, cámara, paleta,
   layout y la lista completa de fases.
3. Elegir exactamente la siguiente request `request_kind: sheet` pendiente.
4. Ejecutar una sola vez GPT Image 2 por dirección/candidato:

   ```bash
   sprite-builder --workspace <workspace> generate-openai \
     --request jobs/<job-id>/generation/requests/<request>.json
   ```

5. Si la imagen se produjo fuera del ejecutor, ingerir la hoja completa:

   ```bash
   sprite-builder ingest \
     --request jobs/<job-id>/generation/requests/<request>.json \
     --image /ruta/al/resultado-image-gen.png
   ```

6. Confirmar que el PNG mantiene exactamente `generation.source_size`, volver a
   consultar `queue` y repetir hasta cero requests pendientes.

Para `transparent_preferred` la ingestión inspecciona el canal alpha, el borde,
la proporción transparente, los componentes y el RGB oculto. Si el resultado es
opaco, la request queda rechazada y aparece una nueva request `alpha_retry` en la
cola. Se permiten como máximo dos reintentos.

Después del segundo fallo se crea una `sheet_session` y una request
`manual_alpha`. Abra `sprite-builder ui`, seleccione el `manual_session_id`
mostrado por `queue`, elimine el fondo en el editor y exporte un PNG transparente.
Ese PNG se ingiere en la request manual. Los jobs transparentes no aplican chroma
automático como fallback.

No se generan frames individuales. GPT Image 2 recibe una sola instrucción
detallada y devuelve la hoja completa; el pipeline sólo registra sus regiones
lógicas para la UI/atlas. No se permite `autocut`, crop, resize ni resampling de
la fuente creativa.

## 4. Preparar varios personajes o animaciones

Guarde, por ejemplo, este contenido como `<batch.yaml>`:

```yaml
schema_version: "1.0"
batch:
  id: playable-v001
characters:
  - id: tzucan
    jobs:
      - configs/examples/tzucan_walk_right.yaml
```

Los conteos son derivados; no escriba `character_count` ni
`animation_count`.

```bash
sprite-builder batch-prepare --batch <batch.yaml>
sprite-builder batch-status --batch <batch.yaml>
```

`batch-prepare` valida la pertenencia personaje/job y prepara todas las colas.
`batch-status` devuelve `pending`, `ingested` y `total`, globales y por job.
En el modo sheet, cada request representa una dirección completa, no un frame.

## 5. Validar hojas nativas y reanudar

```bash
sprite-builder sheet-source-validate --job configs/examples/tzucan_walk_right.yaml
```

El comando escribe `jobs/<id>/manifests/sheet-source.json`, verifica que cada
PNG sea una hoja completa del tamaño configurado y declara explícitamente que no
se ejecutaron crop, resize, resampling ni split físico de pixels. Después:

```bash
sprite-builder sheet-session-create --image jobs/<id>/raw/<sheet>.png
sprite-builder ui
# En Sheet Studio: abre la sesión, guarda la segmentación y elimina el fondo
# manualmente sobre la hoja completa; después usa "Exportar hoja nativa".
sprite-builder sheet-native-export --session <session-id> \
  --animation walk_right --output-dir exports/tzucan/walk_right/native \
  --texture-resource-path res://assets/textures/sprites/player/walk/generated/walk_right.png
```

`sheet-process` puede calcular y guardar la segmentación para la UI, pero
`sheet-native-export` vuelve a leer el PNG completo de la etapa de alpha y sólo
convierte los límites aprobados en regiones `AtlasTexture`. Si se cambia la
hoja, se crea una nueva sesión; nunca se sobrescribe la fuente.

El JobSpec ya no tiene una ruta de generación por frame. El modo admitido es
`generation.mode: sheet`; `candidates_per_sheet` controla cuántas hojas
completas se solicitan por dirección. La fuente creativa no pasa por reducción,
recorte, alineación ni cuantización: cualquier revisión geométrica se hace sobre
la hoja completa en Sheet Studio y queda fuera de `sheet-native-export`.

La paleta bloqueada se incorpora al prompt de la hoja nativa. El campo
`palette_max_delta_e00` solo aplica a operaciones opcionales sobre hojas
externas; la ruta GPT Image 2 no cuantiza ni fuerza colores después de generar.
Una paleta puede añadir roles sin romper el formato plano:

```json
{
  "colors": ["#2A1A18", "#C47A50", "#66788A"],
  "roles": {
    "skin": {"colors": ["#C47A50"], "match_colors": ["#D08960"]},
    "metal": {"colors": ["#66788A"], "match_colors": ["#71859A"]}
  }
}
```

Las operaciones opcionales de Sheet Studio pueden registrar colores cuantizados,
pero ese procesamiento no forma parte del export nativo.

## 6. Revisar la hoja completa

Revise la silueta, la continuidad entre celdas y las regiones lógicas en Sheet
Studio. Si una pose necesita una corrección, genere una nueva hoja completa o
edite la hoja manualmente; no existe una etapa de corrección por frame dentro
del JobSpec.

## 7. Exportar una hoja nativa completa

Cuando la hoja completa ya tiene alpha manual en Sheet Studio y sus cortes
fueron aprobados, use el modo explícito `sheet-native-export`. Este modo lee el
único output RGBA de la etapa `background`, calcula las regiones en memoria y
escribe una sola copia byte-a-byte de la hoja original. No ejecuta
`auto_center`, `trim_transparent`, padding, reducción ni resampling.

```bash
sprite-builder sheet-native-export \
  --workspace <sheet-workspace> \
  --session <session-id> \
  --animation save_prepare \
  --frame-indices 0,1,2,3 \
  --output-dir <project>/godot/assets/sprites/npcs/shaman/generated/v2/save_prepare \
  --native-sheet-output <project>/godot/assets/sprites/npcs/shaman/generated/v2/save/save_down_native.png \
  --texture-resource-path res://assets/sprites/npcs/shaman/generated/v2/save/save_down_native.png \
  --fps 8
```

`--frame-indices` identifica las posiciones de la hoja completa, no crea una
hoja nueva. Para Godot, el `.tres` resultante usa `AtlasTexture` con regiones
`(x, y, ancho, alto)` y puede compartir el mismo PNG nativo entre varias
animaciones. El manifest incluye hashes de entrada/salida y declara las
transformaciones prohibidas para que un recorte accidental sea detectable.

## 7. Previews de una sesión Sheet Studio

```bash
sprite-builder sheet-export --session <session-id> \
  --layout horizontal --no-frames --no-contact-sheet
```

Los previews son auxiliares de revisión; no sustituyen la hoja nativa que se
exportará a Godot.

## 8. Copiar el bundle nativo a Godot

```bash
GODOT_ROOT=/Users/emmanuel/Documents/GODOT/The-legend-of-Tzukan/godot
TARGET="$GODOT_ROOT/assets/textures/sprites/player/walk/generated"
mkdir -p "$TARGET"
cp exports/tzucan/walk_right/native/native-sheet.png "$TARGET/walk_right.png"
cp exports/tzucan/walk_right/native/walk_right.sprite_frames.tres "$TARGET/"
cp exports/tzucan/walk_right/native/walk_right.metadata.json "$TARGET/"
```

El `.tres` referencia
`res://assets/textures/sprites/player/walk/generated/walk_right.png`.
Abra Godot, deje que importe el PNG y asigne
`walk_right.sprite_frames.tres` a `AnimatedSprite2D.sprite_frames`. No copie
archivos `.import`; pertenecen a Godot.

## 8.1 Herramientas opcionales para hojas externas

Esta sección aplica únicamente a hojas existentes que se estén editando en
Sheet Studio. No forma parte del JobSpec de generación GPT Image 2 y no debe
ejecutarse sobre la fuente nativa que vaya a pasar por `sheet-native-export`.
Para una hoja externa, `sheet-process` puede normalizar cada celda con el perfil
de escala del personaje:

```bash
sprite-builder --workspace /ruta/al/workspace sheet-process \
  --session <session-id> --frame-count 14 --orientation grid \
  --rows 2 --columns 7 --cell-width 256 --cell-height 512 \
  --canvas-width 96 --canvas-height 96 \
  --anchor-x 48 --anchor-y 55 --manual-alpha \
  --normalize-scale --target-body-height-px 44 \
  --scale-tolerance-px 1 --scale-min-ratio 0.75 \
  --scale-max-ratio 1.333333
```

La medición usa cuantiles centrales del cuerpo y excluye extensiones finas
como armas, báculos y adornos. El frame se escala una sola vez con alpha
premultiplicado y luego se alinea por torso. El manifest de alignment conserva
`scale_factor`, `scale_reference_height_px`, `normalized_body_height_px` y
`scale_manual_review`. Un factor fuera de los límites queda en revisión, aunque
la punta del arma sobresalga de forma intencional.

`--manual-alpha` es importante: evita volver a ejecutar chroma sobre una
imagen que ya fue limpiada en la UI. No uses nearest para recuperar detalle;
nearest sólo conserva píxeles en previews o ampliaciones enteras.

### Alineación por pies sin escalado

En el tab **Sheet**, active **Auto alinear por pies** cuando la acción extienda
manos, armas, báculos o adornos. El detector busca la última banda ancha de
soporte dentro del corredor corporal y la usa como línea de suelo; las
extensiones finas no definen el anchor. Todos los frames se trasladan dentro
del canvas común seleccionado. Si hace falta más espacio, aumente `Canvas W/H`;
la operación agrega transparencia y nunca redimensiona ni remuestrea el sprite.

Guarde primero **la segmentación actual**. El panel **Mover y recortar cada
frame** sólo se habilita cuando el intento inmutable coincide exactamente con
los cortes visibles; cambiar cualquier corte vuelve a bloquearlo hasta guardar
la nueva segmentación. Seleccione un frame y arrastre directamente su figura dentro del marco. Al
soltar, el core recompone ese frame en el canvas elegido, descarta únicamente
los pixels que queden fuera y registra `cropped_pixel_count`. **Reaplicar pies**
restablece los offsets automáticos y **Guardar posiciones y recorte** publica
únicamente esas celdas como la revisión de alignment usada por Export; nunca
vuelve a publicar la segmentación de forma implícita.

El mismo modo está disponible en CLI con `--center-method feet`. No lo combine
con `--normalize-scale`: ambos contratos son deliberadamente excluyentes.

## 9. Bundle nativo verificado

```text
exports/tzucan/walk_right/native/native-sheet.png
exports/tzucan/walk_right/native/walk_right.metadata.json
exports/tzucan/walk_right/native/walk_right.sprite_frames.tres
exports/tzucan/walk_right/native/walk_right.native-export.json
```

La hoja conserva la resolución nativa de generación. El `.tres` referencia
regiones `AtlasTexture` dentro del PNG compartido y el manifest registra el hash
de entrada/salida junto con las transformaciones prohibidas.

## 10. Diagnóstico

- **Tamaño nativo incorrecto**: regenere la hoja con el `source_size` configurado;
  no intente corregirla con crop o resize.
- **Fringe verde**: revise el chroma, la máscara alpha y el matte cleanup.
- **Regiones incorrectas**: vuelva a guardar la segmentación en Sheet Studio;
  el PNG fuente no se modifica.
- **Drift de identidad**: regenere la hoja/candidato usando el canon y la lista de fases.
- **`.tres` no encuentra textura**: el `texture_resource_path` debe empezar con
  `res://` y apuntar al sheet dentro del proyecto.
- **Animación rápida/lenta**: `speed` es FPS; `duration` por frame queda en 1.0.
## Direct GPT Image 2 generation with native transparency

Install the opt-in API dependency and provide the credential through the environment:

```bash
python -m pip install -e '.[image-api]'
export OPENAI_API_KEY='...'
```

Generate exactly one prepared request through the OpenAI Image API:

```bash
sprite-builder --workspace /path/to/workspace generate-openai \
  --request /path/to/request.json
```

Inspect the exact non-secret provider parameters without making an API call:

```bash
sprite-builder --workspace /path/to/workspace generate-openai \
  --request /path/to/request.json --dry-run
```

The executor is pinned to `gpt-image-2`. Transparent jobs are sent with the structured
parameters `background="transparent"` and `output_format="png"`; reference-image jobs use
`images.edit`, while requests without references use `images.generate`. The base64 response is
written directly to immutable raw storage, accompanied by a `.provider.json` record, and then
passed through the normal alpha gate. Invalid alpha receives three total attempts (the initial
generation plus two retries) before
the configured manual UI fallback.

The API key is read only by the optional executor. It is never written to prompts, request JSON,
provider metadata, manifests, or job output.
