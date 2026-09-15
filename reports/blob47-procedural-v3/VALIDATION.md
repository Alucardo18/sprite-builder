# Blob 47 procedural v3

La revisión visual usa el material procedural nativo, sin Sources importados ni
operaciones de resize, blur o resampling. Las capturas se generaron con:

```text
.venv/bin/python reports/blob47-procedural-v3/render.py
```

Artefactos revisados:

- `grass_over_dirt-atlas-8x.png`, `dirt_over_water-atlas-8x.png`, `grass_over_water-atlas-8x.png`: atlas completo de 47 máscaras × 3 variantes.
- `*-outer-corners-8x.png`: las cuatro esquinas exteriores en las tres variantes.
- `*-inner-corners-8x.png`: las cuatro esquinas interiores en las tres variantes.
- `*-island-hole-mosaic.png`: mosaico conectado con una isla y un agujero.
- `*-mosaic.png`: comparación ampliada de los tres perfiles.

## Comprobaciones

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pytest tests/unit/test_tileset_organic_blob_variants.py` | 39 passed |
| `.venv/bin/python -m pytest tests/unit/test_tilesetter_blob_corners_adversarial.py tests/unit/test_tileset_rounded_corners.py tests/unit/test_tilesetter_wang_adversarial.py tests/unit/test_tileset_autotile.py` | 54 passed |
| `.venv/bin/python -m pytest tests/test_tilesetter_studio_adversarial.py` | 25 passed |
| `.venv/bin/ruff check src/sprite_builder/tilesets/patterns.py tests/unit/test_tileset_organic_blob_variants.py tests/test_tilesetter_studio_adversarial.py` | All checks passed |
| `.venv/bin/ruff check src/sprite_builder/ui/app.py` | 40 E501 preexistentes en el archivo amplio de UI |
| `.venv/bin/mypy src/sprite_builder/tilesets/patterns.py` | Success |
| `node --check /tmp/blob47-studio-final.js` | 0 |
| `.venv/bin/python -m py_compile src/sprite_builder/tilesets/patterns.py src/sprite_builder/ui/app.py` | 0 |
| `git diff --check` | 0 |

`tests/test_ui_smoke.py` queda en 8 passed y 1 fallo de una aserción de texto de
alineación preexistente en `app.py`; no toca el flujo Blob 47.

La comprobación visual del servicio en `http://127.0.0.1:8501/?page=tilesets`
mostró los tres botones de perfil, el estado `47 formas · 3 variantes · 141
tiles listos`, el mosaico de isla/agujero y la vista actualizada tras cambiar
entre pasto/tierra, tierra/agua y pasto/agua. El endpoint de validación en
`http://127.0.0.1:8502/?page=tilesets` también respondió 200.
