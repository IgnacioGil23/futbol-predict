# Preregistro: valor de mercado del plantel (Transfermarkt) como información de pretemporada (candidato V)

Fijado el 30/09/2026, **antes** de evaluar. De los datos solo se miró la integridad y la plausibilidad
(`reports/transfermarkt/calidad_transfermarkt.json`): ninguna relación con los resultados.

**Motivación:** el análisis de errores mostró que la brecha con el mercado se duplica en las fechas 1 a 5 (+0,050 con un
ascendido): el Elo tarda en incorporar los cambios de plantel del verano. El valor de mercado del plantel los refleja
en cuanto ocurren.

## Datos

* `dcaribou/transfermarkt-datasets` (valuaciones y transferencias), procesado por `src/data/transfermarkt.py`. Valor del
  plantel de cada club en la fecha de cada partido, con eventos **anteriores** a esa fecha: club de cada jugador por su
  último evento (transferencia o valuación), valor por su último evento, se descartan jugadores sin eventos en 400 días,
  suma de los 25 valores más altos.
* Clubes vinculados a Football-Data por partidos con la misma fecha y marcador: 99,9%-100% de los partidos en las 5
  ligas. Cobertura de 2015-16 a 2025-26: 100%.
* **Limitaciones:** los valores son estimaciones de Transfermarkt, no transferencias reales; el dataset es una foto
  tomada en 2026 (si Transfermarkt corrigió datos viejos después, no se puede saber); la recolección se detuvo en julio
  de 2026, así que **aunque funcione, hoy no hay fuente para usarlo en producción**.

## Candidato V (único)

* Variable: d = log(valor del plantel local) − log(valor del plantel visitante). Una sola variable, sin escala y sin
  centrar con información de otros partidos.
* Corrección sin intercepto sobre el modelo base de cada liga (Poisson sobre la diferencia de Elo, α = 1e-4), en las dos
  regresiones: log λ' = log λ + β_local·z, log μ' = log μ + β_visitante·z, con z = d estandarizada; β por máxima
  verosimilitud con la misma penalización (`src/models/fpl_eval.OffsetPoisson`), estimado en cada liga con sus
  temporadas desde 2012-13 hasta la anterior a la predicha. Si faltara el valor, d = 0.

## Evaluación

* **Principal:** España, Italia, Alemania y Francia, 2015-16 a 2025-26 (15.583 partidos), base y candidato en los mismos
  partidos; IC 95% por bootstrap pareado estratificado por liga (10.000 remuestreos, semilla 0).
  * **Señal:** IC 95% completamente por debajo de 0. **Cumple la regla:** además, diferencia media ≤ −0,005.
* **Secundarios (no deciden):** cada liga; fechas 1 a 5 contra el resto (partidos en que el local jugó 0 a 4 partidos
  de esa temporada); la Premier 2015-16 a 2025-26 (descriptivo); β estimados.

## Qué pasa en cada escenario

* **Señal:** se documenta como la variable de pretemporada que falta; no se lleva a producción mientras no haya una
  fuente en vivo (si se consigue, se congela y se registra en paralelo con su propio preregistro).
* **Sin señal:** se documenta y se descarta el valor de mercado como variable.
