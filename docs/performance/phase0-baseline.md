# Fase 0 · línea base de UI

La línea base acotada mide el puente Python → componente de tres flujos
representativos:

- `sheet-studio`: editor de fondo/segmentación de Sheet Studio.
- `tileset-builder`: editor de atlas y Pattern Studio.
- `pixel-editor`: edición por capas con selección y animación.

El harness no arranca un navegador, no llama APIs de imágenes y no modifica
`app.py` ni el estado de una sesión. Cada muestra cold limpia la caché de data
URIs y cada rerun reconstruye las mismas imágenes con píxeles idénticos para
medir la reutilización de la caché. Además registra las invocaciones de los
puentes, bytes del payload JSON y, opcionalmente, un reporte observacional de
`tracemalloc`.

Desde la raíz del repositorio:

```bash
./.venv/bin/python scripts/benchmark_ui_performance.py \
  --reruns 5 \
  --soak-runs 20 \
  --pretty \
  --output reports/performance/phase0-ui-baseline.json
```

`elapsed_ms` y `props_bytes` son medidas del proceso local y no equivalen a
tiempo de renderizado del navegador. `component_calls` e `image_uri_calls`
cuentan invocaciones del puente y de serialización de imágenes, no llamadas de
red. El soak no aplica un umbral fijo: sirve
para comparar crecimiento entre revisiones sin convertir una métrica sensible
al host en un test frágil.
