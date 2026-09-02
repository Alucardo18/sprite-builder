# sprite-builder

Pipeline local, reproducible y asistido por IA para convertir arte fuente en
sprites pixel art consistentes y listos para Godot 4.6. Está pensado para
**La Leyenda de Tzucan**, pero sus contratos sirven para personajes, enemigos,
NPC, objetos, ataques y efectos.

La generación visual canónica usa la skill local `sprite-builder` y GPT Image 2
para producir una hoja completa por dirección con un prompt de consistencia
versionado. Python prepara la request, conserva la hoja en su resolución nativa,
valida el alpha y registra regiones lógicas para Godot; no recorta ni genera
frames individuales en este modo.

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

## Sheet Studio: editor web local

Si solo quieres limpiar, segmentar, alinear y exportar una sprite sheet, estos
son los pasos mínimos:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[ui]'
sprite-builder ui
```

La app abre en [http://127.0.0.1:8501/](http://127.0.0.1:8501/) y mantiene la
barra lateral visible mientras amplía el canvas. Para ejecutarla sin abrir el
navegador, elegir otro puerto o trabajar sobre otro workspace:

```bash
sprite-builder ui --no-browser
sprite-builder ui --port 8504
sprite-builder --workspace /ruta/al/proyecto ui
```

El editor incluye:

- segmentación horizontal, vertical o en grid con guías pixel-perfect;
- remoción de chroma y herramientas manuales de varita, cuentagotas y borrador;
- selección independiente por frame, historial de ediciones y ajuste fino;
- centrado por torso/body anchor, sin usar armas o VFX para calcular el anclaje;
- exportación RGBA, frames, manifest, contact sheet y GIF sin interpolación.

Cada sesión se guarda de forma inmutable bajo `sheet_sessions/<session_id>/`
con lineage y SHA-256. Una máscara se normaliza cuando cambia la geometría del
frame, y un artefacto rechazado o pendiente de revisión nunca pasa a exportación.

Consulta [README_UI.md](README_UI.md) para el flujo completo de fondo,
segmentación, centrado, edición manual, sesiones y exportación a Godot.

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

4. En Codex, pida usar la skill local `sprite-builder` para ejecutar las requests
   `request_kind: sheet` con GPT Image 2. Cada request produce una hoja completa
   de la animación y dirección declaradas.
5. Si se generó fuera del ejecutor, la ingestión equivale a:

```bash
sprite-builder ingest --request jobs/<id>/generation/requests/<request>.json \
  --image /ruta/al/candidato.png
```

6. Cuando `queue` ya no muestre pendientes, valide las hojas nativas y abra
   Sheet Studio para la remoción manual del fondo:

```bash
sprite-builder sheet-source-validate --job configs/examples/tzucan_walk_right.yaml
sprite-builder ui
sprite-builder sheet-native-export --session <session-id> \
  --animation walk_right \
  --output-dir exports/tzucan/walk_right/native \
  --texture-resource-path res://assets/textures/sprites/player/walk/generated/walk_right.png
```

`prepare` prepara las solicitudes pero no genera imágenes:

```bash
sprite-builder prepare --job configs/examples/tzucan_walk_right.yaml
```

La ruta de generación solo acepta hojas nativas completas. No existen comandos
de job para `postprocess`, `align`, `validate`, `preview`, `export` o `run`.
Después de la ingestión se continúa con `sheet-source-validate`, Sheet Studio y
`sheet-native-export`.

Para personajes nuevos puede activar el gate semántico de plantas, gutter y
deriva de suelo. Este gate no confunde margen transparente con anatomía
completa, genera previews a escala runtime y bloquea exportaciones en revisión.
Las reparaciones quirúrgicas se validan con una máscara byte-exact mediante
`sprite-builder verify-edit`. Consulte el
[contrato de calidad determinista](docs/deterministic-character-quality.md).

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

Estos comandos preparan y contabilizan colas; Codex procesa cada request de
hoja pendiente con GPT Image 2. El número de requests ya no depende del número
de frames.

## Herramientas directas para hojas existentes

Estas herramientas sirven para inspección o edición manual de hojas ya creadas;
no forman parte de la generación y no producen requests por frame:

```bash
sprite-builder sheet-session-create --image jobs/demo/raw/walk_right_sheet.png
sprite-builder ui
sprite-builder sheet-native-export --session <session-id> \
  --animation walk_right \
  --output-dir exports/demo/native \
  --texture-resource-path res://assets/generated/tzucan/walk_right.png
```

`sheet-native-export` conserva el PNG completo y solo escribe regiones lógicas
para Godot. No recorta, centra, rellena ni reescala la fuente.

## Salida

El vertical slice incluido y verificado produce:

```text
exports/tzucan/walk_right/native/
├── native-sheet.png
├── walk_right.metadata.json
├── walk_right.sprite_frames.tres
└── walk_right.native-export.json
```

La hoja nativa conserva el tamaño que devuelve GPT Image 2. Las celdas se
describen únicamente como regiones lógicas en el metadata; la escala de
presentación queda en Godot.

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
