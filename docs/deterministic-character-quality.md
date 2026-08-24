# Calidad determinista de personajes

El centrado por torso y la integridad anatómica son contratos distintos. El
torso decide la traslación del frame; armas, VFX, cabello y poses extendidas no
deben moverlo. Los landmarks de cabeza, núcleo corporal y apoyo sirven para
auditar, no para reescalar o deformar cada frame.

## Gate semántico optativo

JobSpec 1.0 conserva compatibilidad hacia atrás. Para una producción nueva,
active el gate explícitamente:

```yaml
quality_gates:
  block_export_on_review: true
  semantic_integrity:
    enabled: true
    alpha_threshold: 8
    body_roi_x: [0.18, 0.82]
    min_bottom_gutter_px: 2
    support_band_height_px: 4
    required_support_components: 2
    max_support_y_jitter_px: 1
    max_terminal_taper_ratio: 0.80
    runtime_preview_scales: [1.0, 0.5]
```

`body_roi_x` excluye de la medición armas laterales largas. Debe ajustarse al
contrato del personaje y la dirección; no es un detector universal de pies.
`required_support_components: 2` es apropiado cuando ambas plantas deben leerse
separadas. Use `1` cuando la perspectiva o el movimiento superpongan los pies.

El reporte distingue:

- `reject`: el apoyo toca o rebasa el gutter mínimo; existe recorte geométrico;
- `review`: apoyo plano, componentes insuficientes o deriva vertical ambigua;
- `pass`: la geometría satisface el contrato configurado.

Un gutter amplio por sí solo nunca prueba que el pie esté completo. El gate
compara también el ancho de la última fila con la banda de apoyo y cuenta sus
componentes. Como el alpha no entiende anatomía, un resultado ambiguo se manda
a revisión visual, no se repara automáticamente.

`sprite-builder preview` añade:

- overlay multiancla con guía de suelo dibujada debajo de la planta;
- contact sheets nearest-neighbour a cada `runtime_preview_scales`;
- el preview nativo existente, sin modificar los PNG alineados.

Cuando `block_export_on_review` está activo, `export` exige primero un reporte
`consistency.json` con estado `pass`. El reporte fija el digest del JobSpec y el
SHA-256 de cada frame alineado; cualquier cambio posterior invalida el gate y
obliga a validar de nuevo.

## Reparaciones quirúrgicas

Una reparación de anatomía o variante de material debe declarar una máscara
RGBA de edición. El verificador exige dimensiones idénticas, preserva alpha por
defecto, calcula hashes y rechaza cualquier cambio fuera de la máscara:

```bash
sprite-builder verify-edit \
  --before frame_accepted.png \
  --after frame_repaired.png \
  --mask allowed_edit_mask.png \
  --overlay reports/frame_repair_overlay.png \
  --report reports/frame_repair.json
```

El overlay pinta cambios autorizados en cian y cualquier invasión de píxeles
protegidos en rojo, ampliados con nearest-neighbour para revisión visual.

No se deben trasplantar o escalar rectángulos de pies desde otra pose. Si falta
una forma, se reconstruye dentro de la máscara manteniendo byte-identical el
torso, rostro, equipo y resto del canvas. Después se inspecciona a 1x y a escala
runtime, se regeneran las variantes derivadas y se vuelven a ejecutar los gates.

## Criterio de producción

1. Alineación estable por torso.
2. Sin `CELL_OVERFLOW` ni resize específico por frame.
3. Soporte de suelo y silueta terminal aprobados.
4. Cambios fuera de la máscara iguales a cero.
5. Alpha preservado salvo autorización explícita.
6. Revisión a 1x y escala runtime.
7. Regeneración de derivados y validación final antes de exportar.
