# Perfiles de borde por pareja de materiales

Esta nota documenta las referencias visuales y las reglas originales usadas por
Pattern Studio. Las referencias se inspeccionaron a resolución nativa y con
escalado nearest-neighbor; no se incorpora ni se redistribuye arte de esos juegos.

## Referencias observadas

- **[LPC Terrains](https://opengameart.org/content/lpc-terrains)**, tiles de
  32×32: el borde de pasto no alterna píxeles al azar. Agrupa salientes de 1–3 px
  en pequeños mechones y deja tramos tranquilos entre ellos. La tierra usa masas
  más redondeadas y una franja visual continua de aproximadamente 2–4 px. El set
  distingue incluso `Water_Shallows_Dirt` de `Water_Shallows_Sand`, y su script
  genera combinaciones específicas de agua, orilla, tierra y pasto.
- **[Grassy Top-down Tileset](https://ringosnoop.itch.io/grassy-top-down-tileset)**,
  16×16 y CC0: el paquete declara dos aguas distintas, una para contacto con
  pasto y otra para contacto con tierra/arena. La separación por pareja confirma
  que un único ruido universal no describe bien ambos materiales.
- **[South Hyrule Field, The Minish Cap](https://zeldawiki.wiki/wiki/South_Hyrule_Field)**:
  en segmentos del mapa a resolución nativa, el camino de tierra usa grupos de
  borde corto separados por zonas estables. El agua no toca el pasto mediante
  una línea binaria ruidosa: aparece una ribera estructurada, con una masa
  continua y detalles secundarios. Esto favorece una frecuencia menor y menos
  dientes para tierra/agua.

Estas observaciones son reglas de composición, no plantillas copiadas. El código
genera curvas nuevas a partir de la máscara de cada patrón y de una semilla. La
misma gramática se puede aplicar a Dual Grid, Wang, Sides y Blob; en Blob/Sides
se conserva además la composición existente de Border Sources y corners.

### Descomposición de la referencia aportada

La captura de referencia está ampliada aproximadamente 2× con nearest-neighbor y
usa 21 colores RGBA duros. Al reducirla a su cuadrícula fuente, una sección
central de la orilla contiene, desde el agua hacia la tierra:

1. 1–2 px de sombra turquesa dentro del agua;
2. 1 px de ribete casi blanco;
3. hasta 1 px neutro intermitente;
4. 3–5 px de banco terroso con valores claros y oscuros;
5. terreno intacto después de la banda.

La silueta sólo oscila unos pocos píxeles. La lectura fuerte proviene del orden,
contraste y grosor variable de esas bandas, no de ruido aplicado a toda la curva.

## Gramáticas implementadas

| Perfil | Terreno A | Terreno B | Frecuencia | Sesgo visual |
| --- | --- | --- | --- | --- |
| `grass_over_dirt` | pasto | tierra | alta, agrupada | sombra de raíz y mechones claros |
| `dirt_over_water` | tierra | agua | baja | sombra acuática, ribete y banco por capas |
| `grass_over_water` | pasto | agua | media | línea húmeda rota y raíz vegetal |
| `clean` | cualquiera | cualquiera | ninguna | interpolación clásica |

## Contrato pixel-perfect

1. El perfil clásico y el nivel `0` sólo cambian propiedad A/B. Los perfiles
   materiales pueden derivar tonos RGB duros de las muestras A/B; conservan el
   alpha y nunca filtran ni mezclan alfa.
2. La intensidad tiene cuatro estados (`0..3`). El nivel `1` construye una banda
   mínima legible; el `3` combina hasta unos 2–3 px de silueta con sombra, ribete y
   banco o raíz de 1–4 px según el tamaño.
3. La semilla (`0..999999`) selecciona frecuencias y signo de un campo armónico
   determinista. Nunca existe ruido distinto entre ejecuciones.
4. El campo es periódico y covariante ante giros de 90 grados. En generación
   directa, Wang/Dual/Blob/Sides usan la cobertura matemática de su máscara. En
   sets TileSetter con Border Sources, Blob y Wang derivan la distancia desde
   el ownership real de los píxeles no transparentes: conservan Borders y
   corners authored y sólo estilizan la franja interior adyacente. Así no se
   crea una segunda transición en el centro de un tile.
5. Las máscaras vacía y completamente llena permanecen intactas. Los overrides
   manuales siguen teniendo prioridad total.

El resultado buscado es irregularidad legible, no aleatoriedad visible: bandas
ordenadas próximas al contorno, regiones interiores intactas y una variante
reproducible que puede guardarse en el proyecto y en `terrain_pattern.json`.
