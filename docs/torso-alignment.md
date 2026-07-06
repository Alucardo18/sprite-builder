# Alineación por torso

El centro del alpha o bounding box es inestable: una lanza, látigo o efecto
desplaza su centro sin que el cuerpo se haya movido. El pipeline alinea el
`torso_anchor` contra un punto constante del canvas.

## Calibración

En la pose canónica se confirman hombros izquierdo/derecho y caderas
izquierda/derecha:

```text
torso_anchor = promedio(hombro_i, hombro_d, cadera_i, cadera_d)
torso_width  = distancia(hombros)
torso_height = distancia(medio_hombros, medio_caderas)
```

Se guarda un template RGBA/máscara del torso, histograma CIELAB, descriptores,
paletas de cuerpo/arma y coordenada normalizada.

## Estimación por frame

1. `foreground = alpha > threshold`.
2. Una apertura morfológica elimina extensiones delgadas.
3. El distance transform favorece el cuerpo ancho.
4. Flujo óptico robusto predice el anchor desde el frame previo.
5. Template matching busca sólo alrededor de esa predicción.
6. La similitud de paleta y el prior temporal desempatan candidatos.

```text
score =
  0.40 * template +
  0.20 * color +
  0.20 * core_body +
  0.20 * temporal_prior
```

Paletas declaradas como arma no aportan al score. Ramas con gran distancia
geodésica al torso tampoco. Si template y flujo difieren más del 8% de la
altura corporal, disminuye la confianza.

```text
confianza =
  0.35 * template +
  0.25 * optical_flow_inliers +
  0.20 * color +
  0.20 * agreement
```

- `>= 0.85`: aceptar.
- `0.65–0.84`: warning y preview.
- `< 0.65`: revisión obligatoria.

## Traslación y overflow

Cada frame se traslada para hacer coincidir su anchor detectado con
`canonical_canvas_anchor`. La escala corporal no cambia. Después se verifican
todos los extremos: si uno no cabe, se devuelve `CELL_OVERFLOW`; nunca se
encoge un frame aislado.

Los datos por frame pueden incluir `torso_anchor`, `foot_anchor`,
`weapon_socket`, `effect_origin`, confianza y override. Sólo el torso determina
la estabilización del cuerpo.

## Revisión visual

El overlay de anchors coloca una cruz sobre cada torso y bordes de celda. Busque:

- trayectoria suave del torso;
- pies que se muevan por la animación, no por recentrado;
- tocado estable;
- armas/VFX cruzando celdas sin arrastrar al cuerpo.

Toda corrección manual debe registrar valor automático, override, razón y autor.
