# Orquestación multiagente

El planner principal coordina artefactos, no memoria conversacional. Cada worker
recibe archivos versionados y devuelve outputs con hashes, métricas y estado.

| Agente | Entrada | Salida y gate |
|---|---|---|
| Planner principal | BatchSpec/JobSpec y manifests | Orden de etapas, retries y decisión final |
| Game Art Director | Brief y referencias | Reglas de estilo aprobadas |
| Character Bible | Descripción y análisis local | `bible.yaml`, `palette.json` |
| Prompt Engineering | Bible + pose/fase | Prompt estable por request |
| Codex Image Generation | Request + referencias | Un PNG por llamada integrada `image_gen` |
| Consistency QA | Canon + frames alineados | Drift por dirección: pass/review/reject |
| Postprocessing | PNG fuente | RGBA recortado, escalado y cuantizado |
| Torso Anchor | Frames lógicos + overrides | Anchors, confianza y frames alineados |
| Godot Export | Frames aprobados | Sheet, JSON y `SpriteFrames .tres` |
| Test/Validation | Código + fixtures | pytest, Ruff, mypy y smoke Godot |
| Documentation | Interfaces verificadas | README y guía operativa |

## Contrato de handoff

1. `prepare` crea requests deterministas por dirección, frame y candidato.
2. `image_gen` debe ser la última acción del turno.
3. El siguiente turno copia e ingiere el PNG; el hash impide reemplazos
   silenciosos.
4. Postprocesado y alignment escriben manifests independientes.
5. `manual_review`, `reject` o `CELL_OVERFLOW` bloquean exportación.
6. Los overrides humanos se conservan como JSON versionable.

## Paralelismo seguro

- Personajes y jobs independientes pueden procesarse en paralelo.
- Los frames pueden generarse en paralelo sólo cuando no usan continuidad con
  el frame anterior; el default de personajes principales es secuencial.
- Postprocesado puede paralelizarse por frame.
- Alignment y QA temporal deben ejecutarse en orden por dirección.
- Export sólo comienza cuando todos los frames de esa animación aprobaron.

La generación nunca se delega a HTTP, SDK o API key: el worker visual usa la
skill local `sprite-builder` y la herramienta integrada de Codex.
