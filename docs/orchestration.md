# Orquestación multiagente

El planner principal coordina artefactos, no memoria conversacional. Cada worker
recibe archivos versionados y devuelve outputs con hashes, métricas y estado.

| Agente | Entrada | Salida y gate |
|---|---|---|
| Planner principal | BatchSpec/JobSpec y manifests | Orden de etapas, retries y decisión final |
| Game Art Director | Brief y referencias | Reglas de estilo aprobadas |
| Character Bible | Descripción y análisis local | `bible.yaml`, `palette.json` |
| Prompt Engineering | Bible + animación completa | Prompt detallado estable por hoja/request |
| GPT Image 2 Generation | Request + referencias | Una hoja PNG nativa por dirección/candidato |
| Native sheet QA | Hoja + canon + regiones lógicas | Tamaño, alpha, hash y layout: pass/review/reject |
| Godot Export | Hoja y regiones aprobadas | PNG nativo, JSON y `SpriteFrames .tres` con AtlasTexture |
| Test/Validation | Código + fixtures | pytest, Ruff, mypy y smoke Godot |
| Documentation | Interfaces verificadas | README y guía operativa |

## Contrato de handoff

1. `prepare` crea requests deterministas por dirección y candidato; cada una
   contiene el plan completo de fases.
2. `generate-openai` llama GPT Image 2 una vez por hoja y conserva sus bytes.
3. La ingestión verifica el tamaño nativo; el hash impide reemplazos silenciosos.
4. `sheet-source-validate` escribe un manifest metadata-only y no materializa crops.
5. Sheet Studio remueve alpha manualmente; `sheet-native-export` sólo publica
   la fuente íntegra y regiones lógicas.
6. `manual_review`, `reject` o un tamaño nativo incorrecto bloquean exportación.

## Paralelismo seguro

- Personajes y jobs independientes pueden procesarse en paralelo.
- Las hojas de direcciones independientes pueden generarse en paralelo; los
  candidatos de una misma dirección conservan su orden determinista.
- La remoción manual y la revisión de regiones ocurren por sesión de hoja.
- Export sólo comienza cuando todas las hojas y sus regiones lógicas aprobaron.

La generación canónica usa el ejecutor GPT Image 2 con `OPENAI_API_KEY`; nunca
se improvisan llamadas HTTP ni se usa un SDK fuera de `generate-openai`.
