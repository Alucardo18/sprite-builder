# Arquitectura

`sprite-builder` separa la generación creativa de las transformaciones
geométricas. La primera usa un prompt de consistencia versionado y GPT Image 2
para producir una hoja completa; las segundas son funciones Python
deterministas y verificables.

```text
descripción + referencias
        │
        ▼
Character Bible ──► prompt detallado + plan completo de fases
        │                              │
        │                              ▼
        │                       GPT Image 2 API
        │                              │
        ▼                              ▼
 canon aprobado ◄────────── hoja fuente nativa por dirección
                                       │
                                       ▼
                         alpha manual/UI + QA de dimensiones
                                       │
                                       ▼
                 regiones lógicas → metadata JSON → AtlasTexture/.tres

Hoja completa aprobada → regiones lógicas nativas → un PNG RGBA compartido →
metadata JSON → SpriteFrames .tres con AtlasTexture
```

## Límites de responsabilidad

- **Generación**: la skill `sprite-builder` prepara y ejecuta el comando
  `generate-openai`, que usa GPT Image 2 con parámetros estructurados. `mode: sheet`
  es el flujo canónico: una request por dirección/candidato y un prompt para la animación
  completa.
- **Dominio/orquestación**: valida jobs, registra artefactos y reanuda etapas.
- **Native sheet QA**: verifica tamaño, hash, alpha, layout y lineage sin
  materializar crops ni imágenes por frame.
- **Native full-sheet export**: copia la hoja RGBA manualmente limpiada sin
  modificar sus bytes; sólo traduce límites de corte a regiones de atlas. No
  recorta, centra, rellena ni reescala físicamente la fuente.
- **Sheet core**: permite inspeccionar y editar hojas existentes en Sheet Studio.
  Sus operaciones auxiliares no forman parte de la generación GPT Image 2 ni
  sustituyen el export nativo.
- **UI local**: traduce controles Streamlit a configuraciones del sheet core; no
  contiene algoritmos de imagen.

## Interfaz local y sesiones

`sprite-builder ui` inicia un editor local. Las sesiones viven bajo
`sheet_sessions/<session_id>/`, copian el PNG fuente de forma inmutable y
versionan cada intento por digest de configuración. El orden es:

```text
source → segmentation → background/manual alpha → native full-sheet export
```

`sheet-native-export` exige que `background/manual alpha` contenga exactamente
un PNG del tamaño fuente y no continúa por `optional scale`, `alignment` o
`trim_transparent`. La escala de presentación queda en el consumidor runtime
(por ejemplo, `AnimatedSprite2D` con filtro nearest).

Los outputs se escriben antes del manifest. Al reabrir, tamaño y SHA-256 de
cada artefacto deben coincidir. Un cambio de segmentación o fondo invalida el
export nativo y obliga a revisar de nuevo las regiones.

El flujo predeterminado prepara artefactos para GPT Image 2. El comando explícito
`generate-openai` requiere una credencial en el entorno, registra el proveedor y entrega sus
bytes al mismo gate de ingestión. No se llama a una API para crear imágenes de
frames independientes.

## Artefactos y quality gates

Cada etapa conserva entradas, salidas, hashes, métricas y warnings. Un cambio
en la Bible invalida generación y etapas posteriores; cambiar sólo el layout
lógico requiere volver a validar las regiones.

Estados:

- `pass`: puede avanzar.
- `review`: requiere confirmación o corrección humana.
- `reject`: debe reemplazarse/regenerarse.
- `failed`: error técnico reproducible.

Ninguna exportación debe aceptar una hoja con alpha inválido, tamaño nativo
incorrecto, clipping o regiones lógicas pendientes de revisión.

## Invariantes

1. La hoja completa es la única fuente creativa y conserva su resolución nativa.
2. La generación solicita una hoja por dirección/candidato, nunca imágenes de
   frames independientes.
3. La segmentación solo describe regiones lógicas y no modifica los pixels.
4. El estilo 16-bit se exige en el prompt de GPT Image 2; el runtime usa la
   escala y el filtro nearest que correspondan.
5. Alpha manual/proveedor, tamaño nativo, hash y regiones deben pasar antes de
   `sheet-native-export`.
6. Los overrides humanos son archivos versionables; no se ocultan.
7. Godot administra `.import`.
### Opt-in OpenAI Image API executor

Prepared generation requests may be executed directly with GPT Image 2 through the optional
`generate-openai` command. This boundary exists because native transparency is an API output
option, not merely a prompt instruction. For transparent jobs the executor always sends
`background="transparent"` and `output_format="png"`, preserves the decoded PNG bytes without
RGB conversion, records non-secret provider metadata, and delegates acceptance to the existing
ingestion alpha gate. The executor does not weaken immutable raw storage, retry limits, request
lineage, or the manual-review fallback.
