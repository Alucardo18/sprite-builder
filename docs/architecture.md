# Arquitectura

`sprite-builder` separa la generación creativa de las transformaciones
geométricas. La primera se ejecuta con la skill local de Codex y `image_gen`;
las segundas son funciones Python deterministas y verificables.

```text
descripción + referencias
        │
        ▼
Character Bible ──► prompt/plan de poses
        │                    │
        │                    ▼
        │          Codex skill + image_gen
        │                    │
        ▼                    ▼
canon aprobado ◄──── frames fuente
        │
        ▼
QA → alpha/autocut → escala/paleta → torso anchor → alineación
        │
        ▼
PNG individuales → sheet → metadata JSON → SpriteFrames .tres
```

## Límites de responsabilidad

- **Codex + skill `sprite-builder`**: interpreta la Bible, compone prompts,
  presenta referencias a `image_gen`, registra candidatos y coordina revisión.
- **Dominio/orquestación**: valida jobs, registra artefactos y reanuda etapas.
- **Postprocesamiento**: extrae alpha y preserva pixel art.
- **Consistencia**: compara identidad, silueta, paleta y continuidad.
- **Alignment**: estima el torso, aplica overrides y traslada frames.
- **Export**: ensambla celdas sin resampling y genera recursos Godot.
- **Preview**: produce GIF/contact sheets/overlays con Pillow y nearest-neighbor.
- **Sheet core**: inspecciona, segmenta y procesa sprite sheets existentes usando
  las mismas primitivas de postprocesamiento, alignment, preview y export.
- **UI local**: traduce controles Streamlit a configuraciones del sheet core; no
  contiene algoritmos de imagen.

## Interfaz local y sesiones

`sprite-builder ui` inicia un editor local. Las sesiones viven bajo
`sheet_sessions/<session_id>/`, copian el PNG fuente de forma inmutable y
versionan cada intento por digest de configuración. El orden es:

```text
source → segmentation → background → alignment → fine overrides → export
```

Los outputs se escriben antes del manifest. Al reabrir, tamaño y SHA-256 de
cada artefacto deben coincidir. Un cambio de segmentación o fondo invalida
alignment/export; cambiar sólo el layout de export no invalida frames.

El paquete Python no genera imágenes: esa etapa pertenece a la skill local y
`image_gen`. Esta separación hace explícito el punto creativo/humano.

## Artefactos y quality gates

Cada etapa conserva entradas, salidas, hashes, métricas y warnings. Un cambio
en la Bible invalida generación y etapas posteriores; cambiar sólo el layout de
exportación no invalida los frames aprobados.

Estados:

- `pass`: puede avanzar.
- `review`: requiere confirmación o corrección humana.
- `reject`: debe reemplazarse/regenerarse.
- `failed`: error técnico reproducible.

Ninguna exportación debe aceptar un frame con alpha inválido, clipping,
`CELL_OVERFLOW` o anchor pendiente de revisión.

## Invariantes

1. La altura corporal se fija por personaje/animación, no por frame.
2. El bounding box total nunca define el pivot.
3. Armas y VFX no influyen en el anchor del torso.
4. Tras llegar a resolución lógica sólo se usa nearest-neighbor.
5. Los sheets se construyen en código, no se solicitan como cuadrícula final a
   `image_gen`.
6. Los overrides humanos son archivos versionables; no se ocultan.
7. Godot administra `.import`.
