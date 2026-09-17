# Guía de Uso: Tileset Builder

Esta guía documenta paso a paso el funcionamiento y las mejores prácticas de **Tileset Builder** en `sprite-builder`, tanto para la generación procedural instantánea como para el flujo manual pixel-perfect y la exportación agnóstica a cualquier motor de videojuegos (Godot, Tiled, Unity, Unreal o motores propios).

---

## Flujo de Trabajo en 4 Pestañas

Tileset Builder organiza la creación de autotiles en 4 etapas limpias y especializadas:
1. **Atlas**: Carga o cosecha imágenes de referencia, define la grilla base (ej. 16×16 o 32×32 px) y recorta celdas.
2. **Pattern Studio**: Diseña composiciones de cuadrícula y asignación de celdas para Blob 47, Dual Grid 15 o Wang 16.
3. **Estudio de Acabado y Materiales**: Afina la estética con capas de ruido procedural (`dither`, `simplex`, `gravel`), distorsión de contornos y rugosidad, iluminación con sombras dinámicas (Sur, Sur-Este, Omnidireccional), cresta de luz (Rim), mini-sandbox conectado en vivo y exportación directa (Omnibundle ZIP, Godot 4, Unity, Tiled).
4. **Map Tester**: Pinta en mapas interactivos de gran escala y valida en tiempo real la continuidad de los terrenos.

---

## Índice de Contenidos

1. [Módulo 1 · Inicio Rápido (1-Click Wizard & Cosecha Automática)](#módulo-1--inicio-rápido-1-click-wizard--cosecha-automática)
2. [Módulo 2 · Generador Procedural Orgánico con Colores Base](#módulo-2--generador-procedural-orgánico-con-colores-base)
3. [Módulo 3 · Estudio de Acabado, Materiales y Exportación](#módulo-3--estudio-de-acabado-materiales-y-exportación)
4. [Módulo 4 · Flujo Manual por Selección (Estilo Tilesetter)](#módulo-4--flujo-manual-por-selección-estilo-tilesetter)
5. [Módulo 5 · Autotiles Animados](#módulo-5--autotiles-animados)
6. [Módulo 6 · Map Tester y Exportación Agnóstica de Bundles](#módulo-6--map-tester-y-exportación-agnóstica-de-bundles)
7. [Resumen del Formato y Archivos del Bundle](#resumen-del-formato-y-archivos-del-bundle)

---

## Módulo 1 · Inicio Rápido (1-Click Wizard & Cosecha Automática)

El **1-Click Wizard** permite transformar una imagen de referencia o un mockup ilustrado en un ecosistema de autotiles completamente funcional sin tener que recortar celda por celda.

### ¿Cómo funciona?
1. **Carga de Imagen**: En la pestaña **Atlas**, carga una imagen de referencia (paisaje en pixel-art, captura de pantalla o mockup con agua, pasto, arena y caminos).
2. **Auto-cosecha Inteligente**: El algoritmo analiza la imagen buscando celdas homogéneas representativas mediante cuantización de color K-Means y análisis de varianza espacial. Identifica los biomas dominantes (ej. Agua profunda, Tierra/Arena, Césped).
3. **Generación en 1 Clic**:
   - En **Pattern Studio**, despliega la sección **🪄 Asistente 1-Click**.
   - Haz clic en **"Generar Ecosistema Completo (3 Sets)"**.
   - El sistema construye automáticamente:
     - **Set 1**: Pasto sobre Tierra (Blob 47 con 3 variantes orgánicas = 141 tiles).
     - **Set 2**: Tierra sobre Agua (Blob 47 con sombra acuática y ribete de orilla).
     - **Set 3**: Pasto sobre Agua (Blob 47 con línea húmeda y raíz vegetal).
4. **Verificación Inmediata**: Cambia a la pestaña **Map Tester** para pintar con los 3 sets generados de inmediato.

> [!TIP]
> **Recomendación para imágenes de entrada**:
> - Utiliza imágenes PNG a resolución nativa (sin compresión JPEG con artefactos).
> - Asegúrate de que los parches de terreno tengan al menos el tamaño de un tile limpio (por ejemplo, 16×16 px o 32×32 px continuos sin personajes ni objetos superpuestos).

---

## Módulo 2 · Generador Procedural Orgánico con Colores Base

Si no dispones de texturas dibujadas a mano, el generador procedural permite sintetizar autotiles completos a partir de colores primarios y secundarios con iluminación pixel-art profesional.

### Parámetros Principales

| Parámetro | Rango / Opciones | Descripción |
| :--- | :--- | :--- |
| **Terreno A (Superior)** | Selector de Color RGBA | Color dominante del material que queda arriba (ej. verde para pasto). |
| **Terreno B (Inferior)** | Selector de Color RGBA | Color del material de fondo o inferior (ej. café para tierra o azul para agua). |
| **Estrategia del Borde** | `Orgánico neutral`, `Pasto sobre tierra`, `Tierra sobre agua`, `Pasto sobre agua`, `Clean` | Gramática que define cómo rompe la silueta y qué bandas de contacto se aplican. |
| **Nivel de Rugosidad** | `0` (Limpio), `1` (Sutil), `2` (Moderado), `3` (Texturizado) | Amplitud y frecuencia del quiebre en la silueta. |
| **Semilla (`Seed`)** | Entero (0 - 99999) | Variación pseudo-aleatoria determinista para cambiar la silueta sin alterar el estilo. |

### Volumen e Iluminación Pixel-Art

Para evitar que los tiles se vean planos o monótonos, el motor ofrece controles de volumen físico:

1. **Sombra Proyectada (0 a 4 px)**:
   - Añade una franja de oclusión bajo los bordes del Terreno A sobre el Terreno B.
   - **Direcciones**:
     - *Sur (Abajo)*: Ideal para vista top-down cenital.
     - *Sur-Este*: Iluminación clásica con foco de luz diagonal superior-izquierdo.
     - *Omnidireccional*: Crea profundidad uniforme alrededor de todo el contorno.
   - **Shadow Cool Shift**: Las sombras oscurecen el color de fondo y lo viran sutilmente hacia tonos fríos (azulados/violetas), emulando las reglas clásicas de colorimetría en pixel-art.
2. **Cresta de Luz Superior (`Rim Light`)**:
   - Resalta el borde superior de los acantilados o masas de césped con un pixel de brillo derivado de la paleta, dando sensación de relieve y luz solar incidente.

### Generación Simultánea de la Tríada (Blob 47 + Dual Grid 15 + Wang 16)

Tileset Builder permite generar la **tríada completa de autotiling** en un solo paso:
1. En el **Asistente** o en **Pattern Studio**, define tu paleta cromática (Terreno Base y Terreno Secundario) y elige una **Receta Visual** (ej. *Zelda Topdown*, *Retro 16-bit*, *Clean Pixel*).
2. Marca los formatos deseados (`[x] Blob 47`, `[x] Dual Grid 15`, `[x] Wang 16`).
3. Pulsa **"⚡ Generar Tríada Completa"**:
   - El motor sintetiza las 3 familias de autotiles compartiendo exactamente la misma paleta y estilizado de bordes.
   - Cada set se ubica de forma no superpuesta en el eje vertical (`originY`).
   - Puedes pintar inmediatamente con cualquiera de ellos en el **Map Tester** o descargarlos en un **📦 Omnibundle ZIP** que incluye las 3 hojas de sprites y los instaladores para Godot 4, Unity y Tiled.

---

## Módulo 3 · Estudio de Acabado, Materiales y Exportación

Una vez definidos los patrones geométricos (Blob 47, Dual Grid 15 o Wang 16), el **Estudio de Acabado y Materiales** permite refinar el tratamiento estético y exportar los assets listos para el motor de juego en una interfaz optimizada de dos columnas.

### 1. Panel de Controles (Columna Izquierda)
- **Paleta Cromática y Materiales**:
  - Ajuste interactivo con ruedas de color y valores HEX para el terreno base y secundario.
  - Opción de sincronizar cambios de color en toda la suite con un solo clic.
  - Generador de texturas asistido por plantillas IA para enriquecer el suelo con detalles temáticos (flores, rocas, líquenes).
- **Ruido Procedural y Textura de Superficie**:
  - `Pixel Dither`: Micro-trama retro tipo 1-bit / 16-bit para romper el color plano.
  - `Simplex / Perlin`: Ondulación orgánica continua de baja frecuencia.
  - `Gravilla Orgánica`: Moteado y piedrillas de alto contraste.
  - Control de intensidad (0 a 100%) y Semilla (`Seed`) con botón `🎲 Re-roll` para alternar variantes estocásticas.
- **Distorsión de Contornos y Bordes**:
  - Perfiles de transición: `clean`, `organic_neutral`, `grass_over_dirt`, `dirt_over_water`, etc.
  - Rugosidad / Jitter de borde (0 a 3) y Radio de esquina en píxeles.
  - Estilos de esquina: Curvo (`arc`) o Biselado a 45° (`chamfer`).
  - Contorno retro de 1px para estética arcade/SNES.
- **Iluminación y Sombras**:
  - Sombra proyectada (0 a 8px) con dirección Sur, Sur-Este u Omnidireccional.
  - Tintes cromáticos: Azul frío (`cool`), Cálido/Ámbar (`warm`), Místico (`mystic`) o Neutro.
  - Cresta de luz superior (`Rim Light`).
- **Variantes de Aleatoriedad**:
  - 1 a 5 variantes por máscara para eliminar patrones perceptibles de repetición en el mapa.

### 2. Vista Previa en Vivo & Mini-Sandbox (Columna Derecha)
- **Hoja de Sprites Nítida**: Muestra el atlas completo renderizado pixel-perfect con resolución y conteo de variantes.
- **Mini-Sandbox de Terreno Conectado**: Ensambla y autotilea al vuelo una escena de prueba (8×8) para evaluar cómo conectan las transiciones, el ruido y las sombras sin salir de la pestaña.

### 3. Exportación a Motores (Panel Inferior)
- **Omnibundle ZIP**: Descarga unificada con todos los sets de la suite y sus scripts de instalación organizados en carpetas.
- **Instalador Godot 4 (.zip)**: Con script `.gd` y asignación automática de peering bits.
- **Unity RuleTile (.zip)**: Con atlas PNG, script `CreateRuleTile.cs` y configuración RuleTile.
- **Tiled Map (.tsx .zip)**: Con archivo TSX preconfigurado para brochas de terreno.
- **Proyecto JSON**: Guarda y restaura el estado completo de la sesión de trabajo.

---

## Módulo 4 · Flujo Manual por Selección (Estilo Tilesetter)

Para artistas que dibujan sus propios tiles en Aseprite, Photoshop o Pyxel Edit, Tileset Builder ofrece un flujo idéntico a herramientas especializadas como Tilesetter.

### Los 3 Tipos de Autotile

1. **Blob 47 (16/47 Máscaras)**:
   - **Cuándo usarlo**: El estándar de la industria para terrenos orgánicos en juegos 2D top-down y plataformas.
   - **Estructura**: Cubre todas las combinaciones posibles de esquinas, bordes y centros (47 máscaras únicas).
   - **Multi-Banco Orgánico**: El generador sintetiza 3 variantes por máscara (141 tiles en total) con variaciones de contorno controladas, eliminando patrones repetitivos perceptibles al pintar mapas grandes.
2. **Dual Grid 15**:
   - **Cuándo usarlo**: Compatible con el paradigma *Dual Grid* (como el plugin [TileMapDual](https://github.com/pablogila/TileMapDual) de Godot 4).
   - **Estructura**: Atlas 4×4 que contiene las 15 combinaciones de esquinas para una cuadrícula desplazada medio tile, más el tile de fondo lógico.
   - **Ventaja**: Requiere solo 15 tiles para resolver transiciones perfectas en cualquier dirección.
3. **Wang 16**:
   - **Cuándo usarlo**: Terrenos esquemáticos, carreteras, caminos empedrados, dunas o puentes con empalmes predecibles en aristas.

### Pasos para Configurar un Set Manualmente

1. En la pestaña **Atlas**, asegúrate de que el **Tile Size** (ej. 16×16 px o 32×32 px) coincide con tus assets.
2. Pulsa **Importar grilla** o arrastra el ratón sobre la imagen para registrar los **Sources**.
3. En **Pattern Studio**:
   - Elige el tipo de set (`Blob 47`, `Dual Grid 15` o `Wang 16`).
   - En **Tile Properties**, asigna los tiles fuente:
     - En **Blob**: Selecciona el Tile Base y los 4 Border Sources (Norte, Sur, Este, Oeste).
     - *Atajo*: Si solo has dibujado el borde superior, pulsa **"Completar 4 por rotación"** para generar automáticamente los otros 3 lados.
   - Ajusta los **Cutoffs** (profundidad de penetración de las esquinas) si deseas transiciones más suaves o más pronunciadas.
   - Pulsa **"Build Borders"** para ensamblar el atlas final.

---

## Módulo 5 · Autotiles Animados

Los autotiles animados añaden movimiento orgánico a superficies líquidas o con viento directamente en la textura, sin requerir shaders adicionales en el motor.

### Perfiles de Animación Disponibles

- **`shore_ripples` (Oleaje en Costas)**:
  Simula la espuma y ondas que avanzan y retroceden periódicamente contra la ribera de tierra o arena.
- **`water_waves` (Ondas de Agua / Ríos)**:
  Ondulaciones sinusoidales continuas ideales para aguas abiertas, lagos o ríos.
- **`lava` (Lava Hirviente)**:
  Fluctuaciones densas de luminosidad con núcleos incandescentes que pulsan lentamente.
- **`wind` (Brisa / Viento Vegetal)**:
  Oscilación suave de las briznas superiores de hierba o follaje.

### Configuración y Ciclos
- **Frames por Ciclo**: Por defecto genera 4 frames en bucle perfecto (el último frame enlaza fluidamente con el primero sin cortes).
- **Velocidad de Animación (FPS)**: Configura la velocidad deseada (recomendado: 4 a 8 FPS para estética retro o 10 a 12 FPS para movimiento fluido).
- **Exportación de Animaciones**:
  El exportador organiza los frames en bancos horizontales sincronizados en la hoja de sprites y genera en el manifiesto JSON las duraciones exactas y coordenadas de cada frame.

---

## Módulo 6 · Map Tester y Exportación Agnóstica de Bundles

La pestaña **Map Tester** permite validar el comportamiento de los autotiles en un entorno de juego real antes de exportar los archivos al proyecto final.

### Herramientas del Map Tester

- **Pinceles Interactivos**:
  - **Lápiz / Pincel**: Pinta el terreno activo en el lienzo.
  - **Cubo de Pintura (Flood Fill)**: Rellena áreas conectadas del mismo terreno.
  - **Borrador**: Elimina celdas o restaura el terreno base.
- **Generadores Procedurales de Prueba**:
  - **Isla Orgánica**: Genera un mapa con archipiélago natural utilizando ruido Simplex/Perlin para evaluar las transiciones en todas las direcciones.
  - **Mazmorras / Cavernas**: Genera túneles subterráneos mediante autómatas celulares para verificar esquinas interiores y pasillos estrechos.
  - **Plataformas**: Crea cornisas y plataformas flotantes con esquinas redondeadas.
- **Reproductor de Animaciones en Vivo**:
  - Un switch permite activar o pausar la animación de los tiles en el canvas interactivo a los FPS configurados.

---

## Resumen del Formato y Archivos del Bundle

Al pulsar **"Descargar Bundle ZIP"**, el sistema genera un paquete autocontenido con los siguientes archivos:

### 1. `terrain_tiles.png`
- **Contenido**: Hoja de sprites (spritesheet) en formato PNG RGBA a resolución nativa pixel-perfect.
- **Organización**: Contiene todos los tiles canónicos y sus variantes organizados en una grilla ordenada de forma determinista. Si hay animaciones activas, incluye los bancos de frames correspondientes.

### 2. `terrain_bitmask_reference.png`
- **Contenido**: Hoja gráfica de referencia visual que superpone las conexiones y bits de adyacencia (peering bits) sobre cada tile.
- **Utilidad**: Permite verificar de un solo vistazo qué rol cumple cada casilla en el atlas sin tener que decodificar valores binarios.

### 3. `terrain_pattern.json`
- **Contenido**: Manifiesto agnóstico y estructurado en JSON estándar.
- **Estructura clave**:
  - `tile_size`: Ancho y alto de cada celda en píxeles.
  - `pattern_type`: `blob47`, `dual_grid15` o `wang16`.
  - `tiles`: Lista completa de tiles con su coordenada `(x, y)` en el PNG, su máscara lógica y sus bits de conexión (`top`, `bottom`, `left`, `right`, `top_left`, etc.).
  - `variants`: Información de variantes por máscara con su probabilidad uniforme.
  - `animations`: Metadatos de secuencias animadas, duración de cada frame en segundos y mapeo de coordenadas entre frames.
- **Compatibilidad**: Fácilmente consumible por scripts propios en Python, C#, C++, Rust, JavaScript o pipelines de importación personalizados.

### 4. `install_terrain_tileset.gd` (Godot 4)
- **Contenido**: Script GDScript listo para ejecutar como herramienta (`@tool`) o ejecutar en el editor de Godot 4.
- **Función**:
  - Carga `terrain_tiles.png`.
  - Crea un recurso nativo `TileSet` (`.tres`) configurando la fuente de atlas (`TileSetAtlasSource`).
  - Asigna los terrenos (Terrains) en `TileMapLayer` y pinta todos los peering bits automáticamente.
  - Configura la duración y secuencias de las animaciones en los tiles correspondientes.

### 5. `terrain_tileset.tsx` (Tiled Map Editor)
- **Contenido**: Archivo XML de Tileset estándar para [Tiled](https://www.mapeditor.org/).
- **Función**: Configura el tileset con Wang Sets y Terrain Sets nativos listos para usar con la herramienta de pincel de terrenos de Tiled.

---

## Preguntas Frecuentes y Consejos

> [!NOTE]
> **¿Por qué mis transiciones se ven pixeladas o sucias al importar en mi motor?**
> Asegúrate de configurar la textura con filtro **Nearest / Point** (sin filtrado bilineal ni mipmaps) tanto en Godot como en Unity o Tiled. El motor de `sprite-builder` está calibrado para preservar bordes 100% pixel-perfect sin alpha blending borroso.

> [!TIP]
> **¿Cómo combino varios biomas en un solo juego?**
> Genera cada par de terrenos como un set individual (ej. Pasto sobre Tierra, y Tierra sobre Agua). En Godot 4 o en tu motor, puedes crear capas de `TileMapLayer` independientes o registrar ambos en el mismo `TileSet` con diferentes IDs de terreno para que se conecten de forma jerárquica.
