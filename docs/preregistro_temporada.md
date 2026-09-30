# Preregistro: simulación de la temporada y su evaluación histórica

Fijado el 30/09/2026, **antes** de escribir el simulador y de ver cualquier resultado. Esta evaluación no elige un
modelo: el producto se publica igual. Sirve para mostrar, con reglas fijadas de antemano, qué tan creíbles son sus
probabilidades.

## El simulador (versión del producto)

* **Estado inicial** en la fecha de corte D: tabla con los partidos jugados antes de D (puntos, diferencia de gol, goles
  a favor) y Elo de cada equipo a D (el Elo previo a su primer partido desde D, que ya incluye el ajuste de inicio de
  temporada).
* **Partidos restantes:** los de la temporada con fecha ≥ D, en orden cronológico (en la temporada en curso, el
  calendario de openfootball).
* **Cada partido simulado:** goles esperados con el modelo de producción (Poisson sobre la diferencia de Elo); marcador
  sorteado de la grilla de marcadores exactos; **el Elo de los dos equipos se actualiza** con ese marcador con la misma
  regla y los mismos parámetros del Elo real (`configs/elo_params.json`).
* **10.000 temporadas simuladas**, semilla fija.
* **Orden final:** puntos, diferencia de gol, goles a favor (criterios de la Premier que el proyecto ya modela); los
  empates que quedan se resuelven al azar. No se modelan descuentos administrativos de puntos.
* **Salidas por equipo:** probabilidad de campeón, de terminar 1º a 4º, 1º a 6º y en los 3 últimos (descenso), puntos
  esperados y la distribución de posiciones finales.

## Evaluación histórica

* **Temporadas:** 2015-16 a 2025-26. Cada una con el modelo de producción entrenado con 2002-03 hasta la anterior.
* **Cortes:** antes de la fecha 1 y después de 100, 200 y 300 partidos jugados: D = fecha del partido número 1, 101, 201
  y 301 de la temporada en orden cronológico (44 simulaciones en total).
* **Eventos evaluados** (resultado real de la tabla final con los mismos criterios de orden):
  * campeón (una probabilidad por equipo, suma 1);
  * top 4 y descenso (una probabilidad por equipo y evento).
* **Métrica principal:** Brier score. Campeón: Brier multiclase por simulación (suma sobre los 20 equipos de
  (p − y)²). Top 4 y descenso: Brier medio por equipo.
* **Métrica secundaria:** log loss con suavizado (p = (conteo + 0,5) / (10.000 + 0,5·k), k = 20 equipos para campeón, 2
  para los eventos binarios), para no dar infinito cuando un evento con 0 simulaciones ocurre.
* **Línea base:** el mismo simulador con **todos los equipos iguales** (Elo idéntico y fijo): conoce la tabla del corte
  pero no la fuerza de los equipos. Mide cuánto aportan las fuerzas.
* **Comparación descriptiva:** la variante con el Elo **fijo** durante la simulación.
* **Se reporta:** Brier y log loss por evento y por corte, del producto, la línea base y la variante fija, con IC 95% por
  bootstrap de temporadas (las 11 temporadas como unidades); habilidad frente a la línea base (1 − Brier / Brier base);
  calibración de las probabilidades de top 4 y descenso por tramos (0-5%, 5-20%, 20-50%, 50-80%, 80-95%, 95-100%).

## Salvedades declaradas de antemano

* Los parámetros del Elo se ajustaron con 2002-03 a 2020-21, que incluye parte de estas temporadas: el resultado es algo
  optimista.
* 11 temporadas son pocas para evaluar el evento "campeón" (11 campeones): los intervalos van a ser anchos.
* Los cortes de las distintas temporadas no son independientes dentro de una misma temporada.

## Qué pasa según el resultado

La sección "Temporada" de la web se publica igual y muestra esta evaluación, sea cual sea. Si el producto no supera a la
línea base, se dice en la web.
