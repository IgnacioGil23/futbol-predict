# Preregistro: parámetros por liga y simulación de la temporada en España, Italia, Alemania y Francia

Fijado el 27/10/2026, **antes** de ajustar ningún parámetro por liga y antes de correr la simulación de la temporada
fuera de Inglaterra. Lo único ya visto de estas ligas es lo publicado en `reports/challengers/cuotas_2026-10-01.json`
(el modelo de producción con los parámetros de Inglaterra, liga por liga) y la integridad de los datos
(`reports/replication/calidad_ligas.json`). Cualquier cambio posterior queda en el historial de git y tiene que
justificarse en el propio commit.

## Motivación

La web pasa a publicar, además de la Premier, la primera división de España (LaLiga), Italia (Serie A), Alemania
(Bundesliga) y Francia (Ligue 1), con el mismo modelo: Elo basado en cuotas → dos regresiones de Poisson → probabilidad
de cada marcador. El modelo ya se evaluó fuera de muestra en esas ligas (2015-16 a 2025-26) con los parámetros del
rating ajustados en Inglaterra, y mejoró al modelo anterior en todas. Falta saber si conviene ajustar los parámetros en
cada liga, y qué tan creíble es la simulación de la temporada fuera de Inglaterra.

## Qué se ajusta y qué no

* **Las regresiones de Poisson** ya se entrenan en cada liga con sus propios partidos (α = 1e-4, el de producción). No
  cambian.
* **Los parámetros de cada rating** (k, regresión entre temporadas, ventaja inicial de la primera división, desvío de
  los equipos nuevos; y λ en el Elo de resultados) pueden ajustarse por liga. Son dos ratings:
  * **Elo de cuotas** (el del modelo publicado): misma búsqueda y grilla que `src/features/odds_elo.py`.
  * **Elo de resultados** (el de la simulación de la temporada, que actualiza el rating con resultados simulados):
    misma búsqueda y grilla que `src/features/tune_elo.py`.
* **Ajuste:** en cada liga, solo con partidos de su primera división de **2004-05 a 2014-15** (2002-03 y 2003-04 son el
  arranque del rating), con el criterio de siempre (log loss de un logit multinomial del resultado sobre la diferencia
  de rating); la ventaja de local se fija por calibración con esa misma liga y esas temporadas. Las temporadas de la
  evaluación (2015-16 en adelante) no intervienen.

## Evaluación (por liga y por rating: 8 comparaciones)

* **Modelos:** Poisson sobre la diferencia del rating (el de producción para el Elo de cuotas; el de la simulación
  para el Elo de resultados), validación temporal de ventana expansiva: cada temporada de 2015-16 a 2025-26 se predice
  con un modelo entrenado desde la temporada de `FIRST_TRAIN` de `src/models/odds_elo_eval.py` (España y Francia
  2005-06; Italia y Alemania 2006-07) hasta la anterior.
* **Comparación:** parámetros propios de la liga (L) contra los de Inglaterra (E). Métrica: log loss de
  local/empate/visitante por partido, L − E, con IC por bootstrap pareado de partidos (10.000 remuestreos, semilla 0).
* **Regla (se adopta L):** diferencia media ≤ −0,002 **y** el IC de 99,375% (Bonferroni por las 8 comparaciones)
  completamente por debajo de 0. Si no se cumple, la liga usa los parámetros de Inglaterra: más parámetros sin una
  mejora clara sería sobreajuste.
* **Se reporta también:** cada temporada, cuántas mejoran, y la brecha contra Bet365 de E y de L.
* Inglaterra no se reajusta: conserva sus parámetros (`configs/odds_elo_params.json` y `configs/elo_params.json`).

## Simulación de la temporada en cada liga

* **El simulador** es el de la Premier (`docs/preregistro_temporada.md`), con el Elo de resultados y los parámetros que
  resulten de la regla anterior, y el modelo de Poisson de la simulación entrenado en esa liga.
* **Orden final:** puntos, diferencia de gol, goles a favor y azar. LaLiga y la Serie A desempatan primero por
  enfrentamientos directos: no se modela, y se declara en la web.
* **Eventos evaluados:** campeón, top 4 y descenso directo, con estos puestos de descenso directo por liga:
  Inglaterra, España e Italia 3; Alemania 2; Francia 3 en 2015-16, 2 de 2016-17 a 2021-22, 4 en 2022-23 y 2 desde
  2023-24. La promoción (16.º en Alemania y en Francia desde 2016-17) no cuenta como descenso.
* **Temporadas y cortes:** 2015-16 a 2025-26, antes de la fecha 1 y después del 26%, 53% y 79% de los partidos de la
  temporada (los 100, 200 y 300 de 380 de la Premier, redondeado hacia abajo con 306 partidos: 80, 161 y 241).
* **Métricas, línea base (todos los equipos iguales), variante con Elo fijo, IC y calibración:** las de
  `docs/preregistro_temporada.md`, por liga.
* **Qué pasa según el resultado:** la tabla y la proyección de cada liga se publican igual, con su evaluación a la
  vista. Si en una liga el producto no supera a la línea base, se dice en la web.

## Salvedades declaradas de antemano

* Los parámetros de Inglaterra del Elo de resultados se ajustaron con 2002-03 a 2020-21; en las otras ligas no hay
  fuga (se ajustaron con otra liga), pero la comparación L − E no es del todo simétrica.
* Francia 2019-20 está incompleta (temporada suspendida): se usan los partidos jugados y esa temporada no se simula.
* 11 temporadas por liga son pocas para el evento "campeón": intervalos anchos.
