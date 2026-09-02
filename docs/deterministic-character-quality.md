# Calidad determinista de personajes

La integridad anatómica y la conservación de la hoja nativa son contratos
distintos. La hoja completa conserva resolución, escala y pixels; armas, VFX,
cabello y poses extendidas no deben provocar recortes ni reescalados.

## Gate semántico optativo

Para una producción nueva, active el gate semántico en el JobSpec y revise la
hoja completa en Sheet Studio:

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

Sheet Studio permite revisar las celdas lógicas y sus overlays sin alterar la
hoja fuente. `sheet-native-export` exige que la revisión de alpha, el tamaño
nativo y las regiones estén aprobados; cualquier cambio posterior invalida el
manifest y obliga a validar de nuevo.

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
runtime y se vuelve a ejecutar la validación de la hoja nativa.

## Criterio de producción

1. Hoja completa en resolución nativa.
2. Sin crop, resize, resampling ni split físico de pixels.
3. Soporte de suelo y silueta terminal aprobados.
4. Cambios fuera de la máscara iguales a cero.
5. Alpha preservado salvo autorización explícita.
6. Regiones lógicas y hash aprobados antes de exportar.
