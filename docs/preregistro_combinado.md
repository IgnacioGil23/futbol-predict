# Preregistro: modelos entrenados con las cinco ligas (candidatos P-GLM y P-XGB)

Fijado el 30/09/2026, **antes** de construir los candidatos.

**Motivación:** en la Premier sola, XGBoost con todas las variables empató con el modelo lineal (≈ 9.000 partidos). Con
las cinco ligas hay unas cinco veces más datos, la relación Elo → goles es casi la misma en todas
(`docs/model_card.md`, análisis entre ligas) y la señal de los tiros se replica. La pregunta: ¿un modelo entrenado con
todas las ligas, lineal o no lineal, encuentra patrones que un modelo por liga no encuentra?

## Datos

* Primera división de Inglaterra, España, Italia, Alemania y Francia, con las variables de `src/features/build.py`
  (mismo código en todas; Elo con los parámetros de Inglaterra).
* **Variables (fijas):** diferencia de Elo; goles a favor y en contra con ponderación exponencial; tabla (puntos y
  diferencia de gol por partido, puntos en los últimos 5, primer partido de la temporada); descanso y partidos en los
  últimos 21 días; residuo del cara a cara; tiros y tiros al arco con vida media 4 (las 8 del candidato de tiros); y un
  indicador por liga (nivel de goles propio de cada liga). Se excluye el indicador "sin público", que usa fechas de
  Inglaterra.

## Candidatos (dos, fijos)

* **P-GLM:** dos regresiones de Poisson (goles del local y del visitante) con todas las variables, α = 1e-4
  (`PoissonGLMModel`).
* **P-XGB:** gradient boosting con objetivo Poisson (`XGBPoissonModel`) con los hiperparámetros ya definidos en el
  proyecto, sin ajustar: 300 árboles, profundidad 2, tasa 0,03, min_child_weight 50, subsample 0,8, semilla 0.

Ambos se entrenan con **las cinco ligas juntas**, temporadas desde 2006-07 (primera con tiros completos en todas) hasta
la anterior a la predicha.

## Comparaciones

* **Base (B0):** el modelo de cada liga, Poisson sobre la diferencia de Elo, entrenado solo con esa liga (como en la
  replicación).
* **Referencia (B1):** el candidato de tiros de cada liga, entrenado solo con esa liga.

## Evaluación

* **Principal:** España, Italia, Alemania y Francia, 2015-16 a 2025-26 (15.583 partidos), cada candidato contra B0 en los
  mismos partidos; IC 95% por bootstrap pareado estratificado por liga (10.000 remuestreos, semilla 0).
  * **Señal:** IC 95% completamente por debajo de 0. **Cumple la regla:** además, diferencia media ≤ −0,005.
  * Son dos candidatos: el margen de la regla es el que ya compensa probar varios.
* **Secundarios (no deciden):** cada candidato contra B1 (¿agrega algo más allá de los tiros?); cada liga; la Premier
  2015-16 a 2025-26 (descriptivo); importancia de las variables en P-XGB.

## Qué pasa en cada escenario

* **Un candidato cumple la regla:** se congela (entrenado con 2006-07 a 2025-26) y se registra en paralelo en la Premier
  durante 2026-27, con su propio preregistro de la evaluación final.
* **Solo señal:** se documenta.
* **Ninguno:** se documenta que combinar ligas y usar un modelo no lineal no agrega sobre el modelo por liga.
