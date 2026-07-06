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
  # Prioridad descriptiva para la skill; no es un parámetro de API.
  quality: medium
  candidates_per_frame: 2
  background:
    color: "#00FF00"
render:
  cell_size: [128, 128]
  target_body_height_px: 74
  palette_lock: true
  dithering: false
  integrated_shadow: true
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
> genera los candidatos con la herramienta integrada image_gen, conserva el
> chroma indicado y detente ante revisión manual.

La skill ejecuta un bucle multi-turn:

1. Validar el job y leer la Bible.
2. Separar restricciones permanentes de pose/fase.
3. Elegir exactamente la siguiente solicitud pendiente.
4. Llamar una sola vez a `image_gen` con la referencia canónica y, cuando
   exista, el frame anterior aceptado. Esa llamada es la última acción del
   turno.
5. En el turno siguiente, recuperar el PNG generado e ingerirlo:

   ```bash
   sprite-builder ingest \
     --request jobs/<job-id>/generation/requests/<request>.json \
     --image /ruta/al/resultado-image-gen.png
   ```

6. Volver a consultar `queue` y repetir hasta cero pendientes.

No agrupe varios frames en una imagen ni solicite el spritesheet final a
`image_gen`. El sheet se ensambla después, de forma determinista.

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
La generación continúa solicitud por solicitud con la skill.

## 5. Ejecutar y reanudar

```bash
sprite-builder run --job configs/examples/tzucan_walk_right.yaml
```

Para investigar una etapa:

```bash
sprite-builder validate --job configs/examples/tzucan_walk_right.yaml
sprite-builder postprocess --job configs/examples/tzucan_walk_right.yaml
sprite-builder align --job configs/examples/tzucan_walk_right.yaml
sprite-builder preview --job configs/examples/tzucan_walk_right.yaml
```

El pipeline reconoce los artefactos existentes; después de corregir el problema
puede volver a ejecutar:

```bash
sprite-builder run --job configs/examples/tzucan_walk_right.yaml
```

## 6. Corregir un torso anchor

Abra el preview de anchors. Muestra cada frame, su índice y una cruz roja sobre
el torso. Compare la cruz con los frames anterior/siguiente, no con el centro
del bounding box.

La corrección se expresa mediante un JSON indexado por frame:

```json
{"2": [64, 68]}
```

```bash
sprite-builder align --job configs/examples/tzucan_walk_right.yaml \
  --overrides jobs/tzucan-walk-right-v001/overrides/anchors.json
```

El manifest conserva el anchor usado, confianza y fuente. El override tiene
precedencia. No desplace el anchor para acomodar la punta de un arma: amplíe
la celda o exporte el VFX por separado.

## 7. Previews

```bash
python scripts/preview_animation.py jobs/<id>/aligned/*.png \
  -o jobs/<id>/reports/animation.gif --mode gif --fps 8 --scale 4

python scripts/preview_animation.py jobs/<id>/aligned/*.png \
  -o jobs/<id>/reports/contact.png --mode contact --columns 4

python scripts/preview_animation.py jobs/<id>/aligned/*.png \
  -o jobs/<id>/reports/anchors.png --mode anchors \
  --anchors jobs/<id>/manifests/anchors.json
```

Los previews pueden escalarse para inspección, pero no sustituyen a los PNG
lógicos usados en el sheet.

## 8. Exportar y copiar a Godot

```bash
sprite-builder export --job configs/examples/tzucan_walk_right.yaml
```

O use las utilidades directas mostradas en el README. Para el caso Tzucan:

```bash
GODOT_ROOT=/Users/emmanuel/Documents/GODOT/The-legend-of-Tzukan/godot
TARGET="$GODOT_ROOT/assets/textures/sprites/player/walk/generated"
mkdir -p "$TARGET"
cp exports/tzucan/walk_right/walk_right.png "$TARGET/"
cp exports/tzucan/walk_right/walk_right.sprite_frames.tres "$TARGET/"
cp exports/tzucan/walk_right/walk_right.metadata.json "$TARGET/"
```

El `.tres` referencia
`res://assets/textures/sprites/player/walk/generated/walk_right.png`.
Abra Godot, deje que importe el PNG y asigne
`walk_right.sprite_frames.tres` a `AnimatedSprite2D.sprite_frames`. No copie
archivos `.import`; pertenecen a Godot.

## 9. Vertical slice Tzucan verificado

```text
exports/tzucan/walk_right/walk_right.png              512×128 RGBA
exports/tzucan/walk_right/walk_right.metadata.json    4 regiones
exports/tzucan/walk_right/walk_right.sprite_frames.tres
jobs/tzucan-walk-right-v001/reports/walk_right.gif
jobs/tzucan-walk-right-v001/reports/walk_right_contact.png
jobs/tzucan-walk-right-v001/reports/walk_right_anchors.png
```

La animación `walk_right` tiene cuatro celdas 128×128, loop a 8 FPS y
`torso_anchor [64,68]`. El reporte guardado tiene estado `pass`, cobertura de
paleta 1.0 en todos los frames y drift medio 2.019.

## 10. Diagnóstico

- **`CELL_OVERFLOW`**: aumente la celda para todos los frames o separe VFX.
- **Fringe verde**: revise el chroma, la máscara alpha y el matte cleanup.
- **Jitter**: mire el anchor overlay; corrija el torso, no el bounding box.
- **Drift de identidad**: regenere sólo el frame fallido usando canon y vecinos.
- **`.tres` no encuentra textura**: el `texture_resource_path` debe empezar con
  `res://` y apuntar al sheet dentro del proyecto.
- **Animación rápida/lenta**: `speed` es FPS; `duration` por frame queda en 1.0.
