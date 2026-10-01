# Preregistro: rating basado en cuotas (ELO-Odds, candidatos O1 y O2)

Fijado el 01/10/2026, **antes** de escribir el código del candidato y antes de ver cualquier resultado. Cualquier
cambio posterior queda en el historial de git y tiene que justificarse en el propio commit.

## Motivación

* El análisis de errores (`reports/analysis/analisis_errores_2026-09-30.json`) ubica la brecha con el mercado en la
  información de cada partido: la mitad sale del 14% de partidos con mayor desacuerdo, y se duplica en las fechas 1 a
  5 y con equipos ascendidos.
* Wunderlich y Memmert (2018, *PLoS ONE* 13(6): e0198668) proponen un Elo que, en lugar del resultado, usa las
  probabilidades del mercado **antes** de cada partido ya jugado ("ELO-Odds"). En unos 15.000 partidos de cuatro ligas
  (2007-08 a 2016-17) supera de forma muy significativa al Elo basado en goles. Absorbe lo que el mercado supo en
  partidos anteriores (fichajes, lesiones largas, cambios de entrenador), que es lo que nuestro Elo no ve.
* Fuente: cuotas de Bet365 de Football-Data.co.uk (uso permitido: predicción de partidos de liga). Cobertura de 98% a
  100% por temporada desde 2002-03 en las primeras y segundas divisiones de las cinco ligas (verificado el 01/10/2026).

## El rating (ELO-Odds)

* Misma estructura que el Elo del proyecto (`src/features/elo.py`): partido a partido sobre primera y segunda
  división, ventaja de local h, rating inicial, equipos nuevos y regresión a la media entre temporadas.
* Diferencia única: en la actualización, el resultado (1 / 0,5 / 0) se reemplaza por el puntaje que el mercado
  esperaba **antes** de ese partido, a = p_local + 0,5 · p_empate, con las probabilidades de Bet365 sin margen por el
  método de Shin. El factor k es constante (sin diferencia de gol). Sin cuotas, el partido no actualiza.
* Anti-fuga: el rating previo a un partido del día D solo usa cuotas de partidos jugados antes de D. Las cuotas del
  propio partido nunca se usan.
* Parámetros: k, regresión entre temporadas, ventaja inicial de la primera división y desvío de los equipos nuevos se
  ajustan con el mismo criterio y la misma búsqueda que el Elo del proyecto (`src/features/tune_elo.py`: log loss de un
  logit multinomial del resultado sobre la diferencia de rating), **solo con partidos de Premier de 2004-05 a 2014-15**
  (2002-03 y 2003-04 son el arranque del rating). h se fija por calibración: el h con el que el puntaje esperado de
  dos equipos iguales coincide con el a medio del local en esas temporadas. Grillas: k ∈ {10, 15, 20, 30, 40, 50, 60,
  80, 100, 125, 150}; las demás, las de `tune_elo.py`. En las otras ligas se usan los parámetros de Inglaterra, sin
  reajustar.

## Candidatos (dos, fijos)

* **B0 (base):** el modelo de producción, Poisson sobre `elo_diff` (α = 1e-4).
* **O1:** el mismo modelo con la diferencia de ELO-Odds **en lugar de** `elo_diff`.
* **O2:** el mismo modelo con `elo_diff` **y** la diferencia de ELO-Odds.
* Todos con validación temporal de ventana expansiva: cada temporada de 2015-16 a 2025-26 se predice con un modelo
  entrenado con las anteriores, desde 2004-05 en Inglaterra (arranque del ELO-Odds) y desde la temporada de
  `src/models/replication.py` en las otras ligas (2005-06 o 2006-07).

## Evaluación

* **Principal:** las cinco ligas juntas (Inglaterra, España, Italia, Alemania y Francia), 2015-16 a 2025-26. Métrica:
  log loss de local/empate/visitante, candidato − B0, IC por bootstrap pareado estratificado por liga (10.000
  remuestreos, semilla 0).
  * **Señal:** el IC 95% queda completamente por debajo de 0.
  * **Cumple la regla:** diferencia media ≤ −0,005 **y** el IC 97,5% (corrección de Bonferroni por los dos
    candidatos) completamente por debajo de 0.
* **Secundarios (no deciden):** la Premier sola y cada liga; brecha contra Bet365 de B0 y de cada candidato; en la
  Premier, los cortes del análisis de errores (fechas 1 a 5 = `games_played_home` ≤ 4, partidos con un ascendido y
  desacuerdo entre B0 y el mercado: < 5, 5-10 y ≥ 10 puntos en P(local)).
* **Descriptivo:** O2 + tiros (el candidato de tiros más la diferencia de ELO-Odds) contra el candidato de tiros, para
  saber si las cuotas agregan información sobre los tiros.

## Qué pasa en cada escenario

* **Cumple la regla:** el mejor candidato que la cumpla (menor diferencia media) se congela, se registra en paralelo
  en la Premier durante el resto de 2026-27 y entra en la decisión de julio de 2027 con su propio preregistro de la
  evaluación final. Si en julio cumplen él y el de tiros, se elige el de menor log loss en los partidos comunes; ante
  una diferencia no concluyente, el de tiros (registrado antes).
* **Señal sin cumplir la regla, o sin señal:** se documenta en la model card y no se registra en paralelo. El
  proyecto se da por terminado con el modelo de producción actual y el candidato de tiros en observación.
* El test 2023-24 a 2025-26 ya se usó en confirmaciones anteriores: forma parte del período evaluado y no se reserva.
