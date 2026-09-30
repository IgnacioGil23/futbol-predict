# Preregistro: evaluación final del modelo con tiros

Fijado el 30/09/2026, **antes** de implementar el registro en paralelo y antes de que exista
cualquier predicción de este modelo para la temporada 2026-27. Cualquier cambio posterior a este
documento queda en el historial de git y tiene que justificarse en el propio commit.

## Antecedentes

| Evaluación | Temporadas | Partidos | Diferencia de log loss | IC 95% | Resultado |
|---|---|---|---|---|---|
| Selección (6 candidatos) | 2015-16 a 2022-23 | 3.040 | −0,0042 | [−0,0078; −0,0007] | no promueve (margen) |
| Confirmación (candidato único) | 2023-24 a 2025-26 | 1.140 | −0,0052 | [−0,0111; +0,0006] | no confirma (IC incluye 0) |

Reportes: `reports/challengers/challengers_2026-09-30.json` y
`reports/challengers/confirmacion_tiros_2026-09-30.json`.

## Candidato (único, no se vuelve a elegir)

Dos regresiones de Poisson (goles del local y del visitante), goles independientes, sobre
9 variables: `elo_diff` y, para local y visitante, tiros y tiros al arco a favor y en contra
con media exponencial de vida media 4 partidos (`sh_f_hl4`, `sh_a_hl4`, `sot_f_hl4`, `sot_a_hl4`).
Mismo α = 1e-4 que el modelo de producción.

* Se entrena **una sola vez**, con las temporadas 2002-03 a 2025-26, y queda congelado en
  `models/shadow/model.json` (con su hash de versión) durante toda la temporada 2026-27.
* Sus variables se calculan con la misma función que en el entrenamiento
  (`src/features/team_state.shot_features`), con datos estrictamente anteriores al día del partido.

## Registro

* Archivo `ledger/shadow_predictions.csv` en la rama `monitoring`, con las mismas reglas que el
  registro del modelo de producción: una predicción por partido, solo partidos con fecha posterior
  al día de la corrida, la primera es la definitiva, y el archivo solo admite agregar filas.
* Los partidos de 2026-27 ya jugados al arrancar el registro se agregan una sola vez con
  `source = reconstruido`: son fuera de muestra (el modelo solo vio hasta 2025-26), pero no se
  registraron antes del partido.
* **No se miran resultados parciales durante la temporada.** La web solo muestra cuántos partidos
  se registraron. No hay decisión anticipada.

## Evaluación (julio de 2027, al terminar 2026-27)

* **Datos:** las diferencias partido a partido de 2023-24 a 2025-26 (validación temporal con
  ventana expansiva, igual que en la confirmación) más los partidos de 2026-27 registrados por
  **ambos** modelos (producción en `ledger/predictions.csv`, candidato en
  `ledger/shadow_predictions.csv`), con el resultado real.
* **Métrica:** diferencia de log loss de local/empate/visitante (candidato − producción) en los
  mismos partidos; IC 95% por bootstrap pareado de partidos (10.000 remuestreos, semilla 0).
* **Regla:** se promueve si la diferencia media es ≤ −0,005 **y** el IC 95% queda completamente por
  debajo de 0 (la regla de `src/models/challenger.py`).
* **Reportes secundarios** (no deciden): el resultado solo con 2026-27, solo con los partidos
  registrados en vivo, y la diferencia por temporada.
* Script: `python -m src.models.confirm_shots --final` (reporte en `reports/challengers/`).

## Qué pasa en cada escenario

1. **Cumple la regla:** se promueve con un PR aparte (API, web, reentrenamiento anual y umbrales
   del monitoreo recalculados), como indica la model card.
2. **No cumple:** se mantiene el modelo de producción y el registro en paralelo se extiende a
   2027-28 con el mismo candidato **reentrenado** con la regla anual (2002-03 a 2026-27) y esta misma
   regla, sumando 2027-28 a los datos. Si en julio de 2028 tampoco cumple, los tiros se descartan
   definitivamente.
3. **El registro falla** (partidos sin predicción del candidato): esos partidos quedan fuera de la
   comparación y se informa cuántos fueron. Los partidos no se reconstruyen después.
