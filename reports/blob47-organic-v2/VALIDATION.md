# Blob 47: resultado final

Corrección geométrica y capas materiales implementadas. El usuario autorizó generar textura y gradientes oscuros proceduralmente y aportó una referencia visual. Esta autorización reemplaza la limitación inicial de no crear tonalidades.

Archivos de implementación: `src/sprite_builder/tilesets/patterns.py` y `tests/unit/test_tileset_organic_blob_variants.py`. El HTML se inspeccionó y su JavaScript pasó la comprobación de sintaxis; no fue editado. Se conservaron los cambios preexistentes y no se publicaron ni sobrescribieron assets aceptados.

Geometría: fillets amplios que enlazan con los lados; curvas deterministas asimétricas; campo de baja frecuencia; limpieza binaria de puntas y muescas; puertos canónicos intactos. Material: sombra de contacto 1–2 px, segunda banda oscura intermitente, manchas 2x2 de bajo contraste y mechones de tres píxeles, con semilla independiente. No hay blur, antialias, interpolación ni remuestreo de generación. Se conserva la protección de Sources dibujados grandes.

## Capturas

- `before-*.png`: referencia previa a editar.
- `final-*-native.png`: atlas nativo 16x16, 141 tiles.
- `final-*-atlas.png`: atlas de 47 máscaras por tres variantes, contacto 8x.
- `final-*-outer.png`, `final-*-inner.png`: cuatro esquinas por tres variantes, 8x.
- `final-*-mosaic.png`: isla y agujero, máscaras derivadas de vecinos válidos, 4x.
- `final-profiles.png`: pasto/tierra, tierra/agua, pasto/agua (de arriba abajo).
- `render_contacts.py`: generador reproducible, ejecutar con `.venv/bin/python reports/blob47-organic-v2/render_contacts.py <nombre-de-intento>`.

Se inspeccionaron visualmente el atlas, las esquinas, la comparación y el mosaico. La referencia se adaptó a la densidad nativa de 16px; no es una reproducción de su detalle a mayor resolución. Las ampliaciones son replicaciones enteras para inspección únicamente.

## Validación final

```
.venv/bin/pytest tests/unit/test_tileset_organic_blob_variants.py tests/unit/test_tilesetter_blob_corners_adversarial.py tests/unit/test_tileset_rounded_corners.py tests/unit/test_tilesetter_wang_adversarial.py tests/unit/test_tileset_autotile.py
```

**78 passed in 76.69s**. Incluye bancos de 141 tiles en 16/32/64/128 con tres semillas; conectividad, pinholes, componentes pequeños, puertos entre máscaras/variantes/semillas, sombras sobre el contorno, clusters y regresiones clásicas.

- `.venv/bin/ruff check src/sprite_builder/tilesets/patterns.py tests/unit/test_tileset_organic_blob_variants.py`: PASS.
- `.venv/bin/mypy src/sprite_builder/tilesets/patterns.py`: PASS, 1 archivo.
- `node --check /tmp/blob47-studio.js`: PASS. Extracción literal de bloques script del HTML.
- `git diff --check`: PASS.

Comprobación adicional final:

`.venv/bin/pytest tests/unit/test_tileset_organic_blob_variants.py::test_material_profiles_keep_all_native_topologies` — **3 passed in 3.80s**, los tres perfiles, 47 máscaras, tres variantes y semillas 0/91/314 a 16px. Ruff y diff-check se repitieron tras añadir esa prueba: PASS.

No se ejecutó la suite completa del repositorio ni una sesión de navegador.

## Historial de comprobaciones intermedias

## Comprobaciones ejecutadas

- `.venv/bin/pytest tests/unit/test_tileset_organic_blob_variants.py`: primera ejecución 14 pasaron/4 fallaron; segunda 17/1; tras las correcciones 22 pasaron. Incluye 16/32/64/128, 141 tiles, semillas 0/91/314, conectividad y pinholes.
- `.venv/bin/pytest tests/unit/test_tilesetter_blob_corners_adversarial.py tests/unit/test_tileset_rounded_corners.py tests/unit/test_tilesetter_wang_adversarial.py tests/unit/test_tileset_autotile.py`: 53 pasaron y una regresión del borde dibujado falló; corregida posteriormente.
- `.venv/bin/pytest tests/unit/test_tilesetter_blob_corners_adversarial.py::test_blob_edge_profile_follows_authored_border_without_recoloring_or_center_bands tests/unit/test_tileset_organic_blob_variants.py`: 23 pasaron tras restaurar la protección del Source grande.
- `.venv/bin/pytest tests/unit/test_tileset_organic_blob_variants.py::test_compatible_ports_match_across_masks_seeds_and_variants`: 1 pasó.
- `.venv/bin/ruff check src/sprite_builder/tilesets/patterns.py tests/unit/test_tileset_organic_blob_variants.py`: pasó.
- `.venv/bin/mypy src/sprite_builder/tilesets/patterns.py`: pasó (1 archivo); un error intermedio por código Blob inalcanzable fue corregido.
- `node --check /tmp/blob47-studio.js`: pasó; JavaScript extraído de los bloques script del HTML indicado.
- `git diff --check`: pasó.

Inspección visual: referencia, atlas de 47 máscaras/tres variantes, contactos exteriores/interiores, comparación de perfiles y mosaico isla/agujero. La comparación usa Sources planos verde/tierra/agua. Esa limitación inicial fue resuelta con la autorización posterior para generar sombras. No se probó el navegador ni se afirma una regresión completa del repositorio.

Última ejecución, después de la limpieza binaria:

`.venv/bin/pytest tests/unit/test_tileset_organic_blob_variants.py tests/unit/test_tilesetter_blob_corners_adversarial.py` — **34 passed in 70.92s**.


## SHA-256 final

- `src/sprite_builder/tilesets/patterns.py`: `c4f95aa9add74fd19895cd6064fd26d61855cea6624e4f1ba28a2d83d5f00481`

- `src/sprite_builder/ui/terrain_pattern_studio_component/index.html`: `7278756808e3e0c3c46edbce6b06ff210d49c4c1df6373a5364fb404e3cc4105`

- `tests/unit/test_tileset_organic_blob_variants.py`: `c7677473f143b3be78c3aeab1389df31efe6ae8faa470aeb664a6d5d8cd0362b`
