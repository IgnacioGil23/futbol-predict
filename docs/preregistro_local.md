# Preregistro: ventaja de local estimada con temporadas recientes (candidato L)

Fijado el 30/09/2026, **antes** de construir el candidato. Motivación: el análisis de errores
(`reports/analysis/analisis_errores_2026-09-30.json`) mostró que el modelo le da al local 46,2% de victorias contra
44,5% del mercado y 44,3% real, en las 11 temporadas de 2015-16 a 2025-26. La causa probable: el nivel de goles
(interceptos) se estima con toda la historia desde 2002-03, cuando la ventaja de local era mayor.

## Candidato L (único)

* Igual que el modelo de producción (dos regresiones de Poisson sobre la diferencia de Elo, α = 1e-4, entrenadas con
  la ventana expansiva), salvo los **interceptos**: se reestiman con las **3 temporadas completas anteriores** a la
  predicha, manteniendo fija la pendiente del Elo.
* Estimación: con la pendiente fija, el intercepto de máxima verosimilitud de Poisson tiene forma cerrada,
  b0 = log(Σ goles / Σ exp(pendiente · x)), en esas 3 temporadas. Sin penalización y sin elegir nada.
* 3 temporadas es un número fijado acá, no ajustado; no se excluye ninguna temporada (tampoco las sin público).

## Evaluación

* **Principal:** España, Italia, Alemania y Francia (datos y Elo de `docs/preregistro_replicacion.md`), cada temporada
  de 2015-16 a 2025-26 (15.583 partidos), base y candidato con la misma ventana de entrenamiento.
  * Métrica: log loss de local/empate/visitante, candidato − base; IC 95% por bootstrap pareado estratificado por liga
    (10.000 remuestreos, semilla 0).
  * **Señal:** el IC 95% del conjunto queda completamente por debajo de 0.
  * **Cumple la regla:** además, la diferencia media es ≤ −0,005.
* **Secundarios (no deciden):** cada liga; la Premier 2015-16 a 2025-26 (descriptivo: esas temporadas ya se usaron);
  probabilidad media de victoria local del modelo, del candidato y la real, por liga.

## Qué pasa en cada escenario

* **Señal (con o sin cumplir la regla):** L se congela (pendiente de producción; interceptos con 2023-24 a 2025-26) y se
  registra en paralelo en la Premier durante 2026-27; se decide en julio de 2027 con la regla de siempre, con su propio
  preregistro de la evaluación final.
* **Sin señal:** se documenta; el sesgo de local queda como limitación conocida.
