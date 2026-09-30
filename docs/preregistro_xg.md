# Preregistro: evaluación final del candidato A (xG) y elección entre A y el modelo con tiros

Fijado el 30/09/2026, **antes** de congelar el candidato A y antes de que exista cualquier predicción suya para
2026-27. Complementa [preregistro_fpl.md](preregistro_fpl.md) (prueba histórica de A) y
[preregistro_tiros.md](preregistro_tiros.md) (candidato de tiros). Cualquier cambio posterior queda en el
historial de git y tiene que justificarse en el propio commit.

## Antecedentes

| Candidato | Evaluación | Partidos | Diferencia de log loss | IC 95% |
|---|---|---|---|---|
| Tiros (Elo + tiros + tiros al arco, vida media 4) | confirmación 2023-24 a 2025-26 | 1.140 | −0,0052 | [−0,0111; +0,0006] |
| A (xG móvil, corrección sobre producción) | prueba preregistrada 2023-24 a 2025-26 | 1.140 | −0,0059 | [−0,0115; −0,0002] |

Reportes: `reports/challengers/confirmacion_tiros_2026-09-30.json` y `reports/challengers/fpl_2026-09-30.json`.

## Candidato A (único, no se vuelve a elegir)

* Exactamente la definición de `docs/preregistro_fpl.md`: xG a favor y en contra, media exponencial con vida
  media 4, como corrección sin intercepto sobre el modelo de producción (α = 1e-4).
* Se congela **una sola vez**: corrección estimada con las temporadas 2022-23 a 2025-26 del archivo de Fantasy
  (commit `9779cdb`), sobre el modelo de producción entrenado con 2002-03 a 2025-26 (versión `ced0b252cafe`).
  Queda en `models/shadow_xg/model.json` con su hash de versión, incluidos los valores de imputación.
* No se reentrena durante 2026-27.

## xG de 2026-27

* Por jugador y partido desde la API de Fantasy (`element-summary`, que separa los partidos de una misma fecha).
* Por equipo y partido, en `ledger/xg_team_matches.csv` (rama `monitoring`): una fila por equipo y partido con la
  fecha de captura; el archivo solo admite agregar filas y **el primer valor capturado es el definitivo**. Las
  predicciones usan solo el xG capturado antes del día del partido.
* Las variables se calculan con la misma función que en la prueba histórica (`src/features/fpl_features.py`),
  sobre la historia del archivo más la serie de 2026-27.

## Registro

* `ledger/shadow_xg_predictions.csv` (rama `monitoring`), con las mismas reglas que los demás registros: una
  predicción por partido, solo partidos con fecha posterior al día de la corrida, la primera es la definitiva, el
  archivo solo admite agregar filas.
* Los partidos de 2026-27 ya jugados al arrancar se agregan una sola vez con `source = reconstruido`.
* No se miran resultados parciales durante la temporada; la web solo muestra cuántos partidos se registraron.

## Evaluación (julio de 2027, al terminar 2026-27)

* **Datos:** las diferencias partido a partido de 2023-24 a 2025-26 de la prueba preregistrada, más los partidos
  de 2026-27 registrados por **ambos** (producción en `ledger/predictions.csv`, A en
  `ledger/shadow_xg_predictions.csv`), con el resultado real.
* **Métrica y regla:** las de `docs/preregistro_tiros.md` (log loss de local/empate/visitante, IC 95% por
  bootstrap pareado, 10.000 remuestreos, semilla 0; se cumple con diferencia media ≤ −0,005 e IC 95% por debajo
  de 0).
* **Secundarios:** solo 2026-27, solo partidos en vivo, por temporada.
* Script: `python -m src.models.fpl_eval --final`.

## Elección entre A y el candidato de tiros

1. **Solo uno cumple su regla:** se promueve ese.
2. **Cumplen los dos:** se comparan entre sí, partido a partido (A − tiros), en los partidos de 2023-24 a 2026-27
   que tengan predicción de ambos, con el mismo bootstrap:
   * si el IC 95% de la diferencia queda completamente por debajo de 0, se elige A;
   * si queda completamente por encima de 0, se eligen los tiros;
   * **si incluye el 0, se eligen los tiros:** vienen de Football-Data, de la que el proyecto ya depende, y no
     agregan una API no documentada.
3. **No cumple ninguno:** se mantiene el modelo de producción. Los tiros siguen lo que fija su preregistro
   (extender a 2027-28); A se descarta.
4. Combinar tiros y xG sería un candidato nuevo, con su propio preregistro, recién para 2027-28.

## Qué pasa si el registro falla

Los partidos sin predicción de A quedan fuera de la comparación y se informa cuántos fueron. No se reconstruyen
después.
