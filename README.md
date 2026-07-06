# sprite-builder

Pipeline local, reproducible y asistido por IA para convertir arte fuente en
sprites pixel art consistentes y listos para Godot 4.6. Está pensado para
**La Leyenda de Tzucan**, pero sus contratos sirven para personajes, enemigos,
NPC, objetos, ataques y efectos.

La generación visual ocurre dentro de Codex mediante la skill local
`sprite-builder` y la herramienta integrada `image_gen`. Python se ocupa de
las partes deterministas: transparencia, recorte, paleta, validación,
alineación por torso, spritesheets, previews y exportación a Godot.

## Instalación

Requiere Python 3.12 o posterior:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
sprite-builder doctor
```

Para habilitar el fallback opcional de eliminación de fondo:

```bash
python -m pip install -e '.[background]'
```

Para instalar y abrir el editor web local de sprite sheets:

```bash
python -m pip install -e '.[ui]'
sprite-builder ui
```

Consulte [README_UI.md](README_UI.md) para el flujo de segmentación, chroma,
centrado, ajuste fino, sesiones y exportación manual a Godot.

## Flujo recomendado

1. Analice una referencia o cree el esqueleto de un personaje:

```bash
sprite-builder reference-analyze --image <referencia.png> \
  --output reports/reference.json
sprite-builder character-create --id <id> --description "<descripción>" \
  --reference <referencia.png>
```

   `character-create` nunca sobrescribe una Bible existente y deja el canon
   en estado draft para revisión humana.
2. Complete `bible.yaml`, bloquee `palette.json` y cree un job YAML.
3. Prepare y revise la cola:

```bash
sprite-builder prepare --job configs/examples/tzucan_walk_right.yaml
sprite-builder queue --job-id tzucan-walk-right-v001
```

4. En Codex, pida usar la skill local `sprite-builder`. Cada candidato ocupa
   dos turnos: `image_gen` termina el turno de generación; en el turno
   siguiente Codex ingiere ese PNG y genera el siguiente candidato.
5. La ingestión que realiza la skill equivale a:

```bash
sprite-builder ingest --request jobs/<id>/generation/requests/<request>.json \
  --image /ruta/al/candidato.png
```

6. Cuando `queue` ya no muestre pendientes, ejecute el pipeline:

```bash
sprite-builder run --job configs/examples/tzucan_walk_right.yaml
sprite-builder validate --job configs/examples/tzucan_walk_right.yaml
sprite-builder postprocess --job configs/examples/tzucan_walk_right.yaml
sprite-builder align --job configs/examples/tzucan_walk_right.yaml
sprite-builder preview --job configs/examples/tzucan_walk_right.yaml
sprite-builder export --job configs/examples/tzucan_walk_right.yaml
```

`--dry-run` prepara las solicitudes pero no genera imágenes:

```bash
sprite-builder run --job configs/examples/tzucan_walk_right.yaml --dry-run
```

Un job que requiera intervención humana se detiene sin exportar arte
silenciosamente. Corrija el frame o el anchor, guarde el override y reanude:

```bash
sprite-builder align --job configs/examples/tzucan_walk_right.yaml \
  --overrides jobs/tzucan-walk-right-v001/overrides/anchors.json
sprite-builder run --job configs/examples/tzucan_walk_right.yaml \
  --overrides jobs/tzucan-walk-right-v001/overrides/anchors.json
```

Consulte [la guía de uso](docs/usage.md) para el contrato completo, el flujo en
Codex, la corrección manual y la integración con Godot.

## Lotes

Un batch deriva el número de personajes y animaciones de sus listas:

```yaml
schema_version: "1.0"
batch:
  id: playable-characters-v001
characters:
  - id: tzucan
    jobs:
      - configs/examples/tzucan_walk_right.yaml
```

```bash
sprite-builder batch-prepare --batch <batch.yaml>
sprite-builder batch-status --batch <batch.yaml>
```

Estos comandos preparan y contabilizan colas; Codex sigue procesando cada
solicitud pendiente con la skill y `image_gen`.

## Secuencias desde frame 0

Un JobSpec puede declarar un frame canónico ya aceptado:

```yaml
generation:
  source_size: [1024, 1024]
  candidates_per_frame: 1
  seed:
    path: references/frame_000.png
    frame_index: 0
```

`prepare` marca esa request con `source_kind: seed`. Ingiérala sin llamar
`image_gen`, y registre cada decisión visual de forma inmutable:

```bash
sprite-builder ingest --request <request.json> --image references/frame_000.png
sprite-builder request-review --request <request.json> \
  --status accepted --notes "canonical frame 0"
```

Use la skill local `create-sprite-from-frame0` para coordinar el resto de la
secuencia. Un candidato rechazado no se recicla: se crea un nuevo intento.

## Utilidades directas

Estas herramientas también funcionan sin el orquestador:

```bash
python scripts/build_spritesheet.py jobs/demo/aligned/*.png \
  --output exports/demo/walk_right.png \
  --layout horizontal --cell-width 128 --cell-height 128

python scripts/preview_animation.py jobs/demo/aligned/*.png \
  --output exports/demo/walk_right.gif --mode gif --fps 8

python scripts/preview_animation.py jobs/demo/aligned/*.png \
  --output exports/demo/anchors.png --mode anchors \
  --anchors jobs/demo/manifests/anchors.json

python scripts/export_godot_metadata.py jobs/demo/aligned/*.png \
  --sheet exports/demo/walk_right.png \
  --output-dir exports/demo \
  --texture-resource res://assets/generated/tzucan/walk_right.png \
  --animation walk_right --fps 8 \
  --cell-width 128 --cell-height 128
```

`build_spritesheet.py` nunca interpola imágenes. Si un sprite no cabe en su
celda, devuelve `CELL_OVERFLOW`: aumente la celda para toda la animación o
separe arma/VFX; no reduzca un único frame.

## Salida

El vertical slice incluido y verificado produce:

```text
exports/tzucan/walk_right/
├── frames/
│   ├── walk_right_000.png
│   ├── walk_right_001.png
│   ├── walk_right_002.png
│   └── walk_right_003.png
├── walk_right.png
├── walk_right.metadata.json
└── walk_right.sprite_frames.tres

jobs/tzucan-walk-right-v001/reports/
├── consistency.json
├── walk_right.gif
├── walk_right_contact.png
└── walk_right_anchors.png
```

El sheet es RGBA de 512×128: cuatro celdas de 128×128, `walk_right` a
8 FPS. El reporte actual aprueba los cuatro frames con drift medio 2.019 y
anchors `[64,68]`, sin revisión manual pendiente.

El `.tres` contiene un `AtlasTexture` por frame y un recurso `SpriteFrames`.
No se crea ningún `.import`; Godot es su única fuente de verdad.

## Desarrollo

```bash
pytest
ruff check .
mypy src/sprite_builder
```

Arquitectura: [docs/architecture.md](docs/architecture.md) · orquestación:
[docs/orchestration.md](docs/orchestration.md) · alineación:
[docs/torso-alignment.md](docs/torso-alignment.md) · exportación:
[docs/godot-export.md](docs/godot-export.md)
