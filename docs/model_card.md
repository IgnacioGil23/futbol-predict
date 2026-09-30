# Model card · Marcador Probable (Premier League)

Ficha del modelo en el formato de *model cards* (Mitchell et al., 2019, "Model Cards for Model Reporting").
Todas las cifras salen de los artefactos del repositorio (`models/production/model.json`, notebooks 01-03) con
datos hasta el **20/09/2026**.

## 1. Qué es

| | |
|---|---|
| **Tarea** | Estimar, antes de un partido de Premier League, la distribución de probabilidad del marcador exacto y, a partir de ella, de local / empate / visitante. |
| **Modelo** | Dos regresiones de Poisson (goles del local y goles del visitante, en la línea de Maher 1982) con una sola variable: la diferencia de Elo previa al partido. Marcador = producto de las dos distribuciones de Poisson, recortado en 10 goles y renormalizado. |
| **Parámetros** | 4 (intercepto y pendiente de cada regresión) + 6 del Elo. Artefacto en JSON, sin pickle. |
| **Entrenamiento** | 9.120 partidos de Premier League, temporadas 2002-03 a 2025-26 (se reentrena una vez por temporada). |
| **Uso previsto** | Divulgación y portfolio: mostrar cómo se construye, valida y comunica un modelo probabilístico. |
| **Fuera de alcance** | Apuestas o decisiones con dinero. El modelo **no** le gana al mercado (sección 5). |

## 2. Datos

* **Fuente base:** [Football-Data.co.uk](https://www.football-data.co.uk/): resultados y cuotas de Premier League (E0) y
  Championship (E1), 2000-01 a 2026-27 (9.930 y 14.447 partidos). Columnas documentadas en
  [notes.txt](https://www.football-data.co.uk/notes.txt).
* **Por qué no el dataset derivado que se usaba al principio** (*Club Football Match Data*, A. Gábor): la auditoría del
  notebook 01 encontró que le faltaban 90 partidos (filas con campos extra en el CSV original, descartadas por su
  parser), que su columna `OddHome` mezcla casas distintas según la temporada aunque el README la describe como Bet365,
  y que su Elo posterior a junio de 2025 es una continuación provisional porque la API pública de ClubElo dejó de
  funcionar. De ese dataset se usa solo el Elo de ClubElo, como comparación.
* **Validaciones automáticas** (el pipeline se detiene si fallan): resultado coherente con los goles, sin duplicados,
  cada temporada cerrada con 20 equipos y 19 partidos de local y 19 de visitante contra todos, cuotas imposibles anuladas
  con reporte.
* **Los datos no se versionan**: se descargan con `python -m src.data.download`.

## 3. Variables y anti-fuga

* **Regla:** toda variable de un partido del día *D* se calcula con partidos jugados en días anteriores a *D*.
  Lo verifican tests de "invariancia al futuro": se borran todos los resultados desde *D* y las variables del día *D*
  deben quedar idénticas, tanto en una liga sintética como sobre los datos reales.
* **Elo propio**, partido a partido sobre Premier + Championship, con el factor por diferencia de goles de Hvattum y
  Arntzen (2010): k = k0 · (1 + |dif. de gol|)^λ. Ajustado solo con temporadas de entrenamiento:
  k0 = 7,5; λ = 1,0; ventaja de local = 59,4 puntos (fijada por calibración); regresión a la media entre temporadas = 0,05;
  ventaja inicial de la Premier = 250; ascendidos desde League One = −50 respecto de la media de la Championship.
* **Variables evaluadas y descartadas** (no mejoraron la validación): forma reciente, goles con ponderación exponencial,
  tabla (puntos y diferencia de gol por partido), descanso, congestión, head-to-head, indicador de era sin público,
  decaimiento temporal y corrección de Dixon-Coles para marcadores bajos.

## 4. Protocolo de evaluación

* **Split temporal:** entrenamiento 2002-03 a 2020-21 · validación 2021-22 y 2022-23 (selección) · **test 2023-24 a
  2025-26, evaluado una sola vez**. 2000-01 y 2001-02 son el período de arranque del Elo.
* Reentrenamiento anual con ventana expansiva; Dixon-Coles clásico se reajusta cada semana.
* **Benchmark:** probabilidades implícitas del mercado con el margen quitado por el método de Shin (Štrumbelj 2014):
  Bet365 pre-cierre (misma ventana de información que el modelo) y Pinnacle al cierre (el más exigente).
* **Métricas:** log loss (principal), RPS (Constantinou y Fenton 2012; secundaria, ver Wheatcroft 2019), Brier,
  accuracy, ECE y log loss del marcador exacto. Diferencias contra el mercado con IC 95% por bootstrap pareado.

## 5. Resultados

### Validación (760 partidos) — mejor configuración de cada familia

| Modelo | Log loss | RPS | Accuracy |
|---|---|---|---|
| Mercado: Pinnacle cierre | 0,9491 | 0,1932 | 56,6% |
| Mercado: Bet365 pre-cierre | 0,9511 | 0,1939 | 57,0% |
| **Poisson + diferencia de Elo (elegido)** | **0,9688** | 0,1998 | 54,9% |
| Dixon-Coles clásico (ξ = 0,004) | 0,9692 | 0,1997 | 54,5% |
| XGBoost Poisson (todas las variables) | 0,9693 | 0,1999 | 54,6% |
| Logit multinomial sobre Elo | 0,9698 | 0,1998 | 54,9% |
| Frecuencias históricas | 1,0613 | 0,2319 | 45,7% |

Las familias no se distinguen entre sí (IC pareados de ±0,004 a ±0,009 que incluyen el 0): se eligió la más simple.

### Test (1.140 partidos; Pinnacle solo tiene cuotas para 970)

| Modelo | Log loss | RPS | Brier | Accuracy | ECE |
|---|---|---|---|---|---|
| Mercado: Pinnacle cierre (n = 970) | 0,9443 | 0,1906 | 0,5591 | 56,2% | 0,019 |
| Mercado: Bet365 pre-cierre | 0,9657 | 0,1956 | 0,5744 | 54,2% | 0,023 |
| Dixon-Coles clásico | 0,9877 | 0,2027 | 0,5891 | 52,3% | 0,023 |
| **Poisson + diferencia de Elo (producción)** | **0,9879** | 0,2030 | 0,5896 | 51,6% | 0,022 |
| XGBoost Poisson | 0,9895 | 0,2035 | 0,5905 | 51,7% | 0,028 |
| Logit multinomial sobre Elo | 0,9901 | 0,2036 | 0,5907 | 51,6% | 0,024 |
| Frecuencias históricas | 1,0746 | 0,2329 | 0,6507 | 43,2% | 0,019 |

**Diferencia del modelo de producción contra el mercado** (log loss del modelo − del mercado, mismos partidos):
+0,022 frente a Bet365 pre-cierre (IC 95% 0,013 a 0,031) y +0,028 frente a Pinnacle cierre (IC 95% 0,017 a 0,038).
**El modelo no supera al mercado**; la brecha es estable temporada a temporada. Está bien calibrado (ECE 0,022).

## 5 bis. Experimentos posteriores al modelo de producción

### Tiros y tiros al arco (30/09/2026) · **no se promovió**

* **Hipótesis:** los tiros y los tiros al arco miden el rendimiento con menos azar que los goles, y el modelo no los usaba.
* **Protocolo, fijado antes de ver los resultados:** validación temporal en 8 temporadas (2015-16 a 2022-23, 3.040 partidos);
  6 candidatos (Elo + tiros al arco, con o sin tiros, con vida media de 4, 8 o 16 partidos) contra el modelo de
  producción, en los mismos partidos. Regla: se promueve solo si mejora el log loss en al menos 0,005 **y** el IC 95%
  pareado queda completamente por debajo de 0. El test 2023-26 no se usó.
* **Resultado del mejor candidato** (Elo + tiros + tiros al arco, vida media 4): −0,0042 de log loss, IC 95%
  [−0,0078; −0,0007]. Mejora en las **8 de 8 temporadas** (test de signos, p = 0,004).
* **Decisión: no se promueve.** La mejora no alcanza el margen de 0,005 y, corrigiendo por haber probado 6
  candidatos (IC 99,2%), el intervalo incluye el 0 ([−0,0090; +0,0006]).
* **Lectura:** el efecto parece real pero chico (~20% de la brecha con el mercado). Las variables de tiros quedan
  en el pipeline y se vuelven a evaluar en el reentrenamiento anual, en temporadas que no se usaron para elegir el
  candidato (2023-24 en adelante). Reporte completo: `reports/challengers/challengers_2026-09-30.json`.

### Poisson bivariado, solo y con tiros al arco (30/09/2026) · **no se promovió**

* **Hipótesis:** los goles de los dos equipos están correlacionados (Karlis y Ntzoufras 2003) y el modelo, que los
  trata como independientes, subestima los empates.
* **Diagnóstico previo, solo en temporadas de entrenamiento** (2003-04 a 2014-15, 4.560 partidos, cada una predicha
  con un modelo entrenado con las anteriores): empates observados / esperados = 1,08 (IC 95% 1,03 a 1,13); 2-2 = 1,17;
  3-3 o más = 1,50. Covarianza residual de los goles 0,082 (IC 0,044 a 0,120), positiva en 11 de 12 temporadas.
  Pasó el filtro fijado de antemano. Script: `src/analysis/draw_diagnostic.py`.
* **Candidatos:** Poisson bivariado sobre las mismas regresiones, con covarianza constante, proporcional a los goles
  esperados, o proporcional + diagonal inflada (0-0 a 3-3, ecuación 5 del paper); cada uno con Elo y con Elo + tiros al
  arco (vida media 4). Estimación en dos etapas: las regresiones fijan los goles esperados y la dependencia se estima
  por máxima verosimilitud del marcador exacto.
* **Protocolo:** las mismas 8 temporadas que la evaluación de tiros. Regla fijada de antemano: se promueve si (a) mejora
  el log loss de local/empate/visitante en al menos 0,005 con IC 95% por debajo de 0, o (b) mejora igual el log loss del
  marcador exacto sin empeorar local/empate/visitante.

| Candidato (diferencia contra producción) | Local/empate/visitante | Marcador exacto |
|---|---|---|
| Bivariado constante | −0,0000 [−0,0008; +0,0008] | **+0,0026** [+0,0006; +0,0046] |
| Bivariado proporcional | −0,0001 [−0,0008; +0,0006] | **+0,0022** [+0,0003; +0,0040] |
| Bivariado + diagonal | +0,0006 [−0,0006; +0,0019] | **+0,0024** [+0,0002; +0,0047] |
| Tiros al arco (referencia) | −0,0030 [−0,0057; −0,0004] | −0,0025 [−0,0062; +0,0010] |
| Tiros al arco + bivariado proporcional | −0,0032 [−0,0060; −0,0004] | −0,0002 [−0,0045; +0,0040] |
| Dixon-Coles (referencia) | +0,0003 [−0,0004; +0,0011] | −0,0002 [−0,0013; +0,0008] |

* **Decisión: no se promueve ninguno.** El bivariado **empeora** el marcador exacto (IC por encima de 0) y no cambia
  local/empate/visitante; sumado a los tiros no agrega nada a lo que ya aportan los tiros solos.
* **Por qué** (análisis posterior a la decisión): el exceso de empates de 2003-2015 no se repite en 2015-2023. En esas
  temporadas el modelo actual acierta los empates (711 observados, 715 esperados) y la covarianza residual es −0,03
  (IC −0,08 a +0,02). El λ₃ estimado baja en cada temporada que se suma (de 0,086 para 2015-16 a 0,040 para 2022-23), pero sigue arrastrando la
  correlación del período anterior y sobreestima los empates (735 esperados).
* **Lectura:** la correlación entre los goles existió pero no es estable; un modelo que la fije con la historia
  empeora. Reporte completo: `reports/bivariate/evaluacion_2026-09-30.json`.

## 6. Limitaciones

* No conoce lesiones, suspensiones, alineaciones, fichajes ni cambios de entrenador: el mercado sí, y por eso predice mejor.
* Solo partidos de liga: no ve FA Cup, League Cup ni competiciones europeas. Descanso y congestión son "de liga".
* La ventaja de local cambió con el tiempo (+0,39 goles antes de 2020, +0,08 sin público, +0,27 desde 2021); el modelo
  la estima con todos los datos hasta cada temporada.
* El marcador exacto es intrínsecamente incierto: en las 8.030 predicciones históricas, el marcador más probable nunca
  superó el 15%.
* Datos semanales; los próximos partidos se publican pocos días antes.
* Predicciones para fechas históricas: solo si ambos equipos jugaban Premier o Championship esa temporada.

## 7. Referencias

* Maher, M. J. (1982). Modelling association football scores. *Statistica Neerlandica*, 36(3).
* Dixon, M. J., y Coles, S. G. (1997). Modelling association football scores and inefficiencies in the football betting market. *JRSS C*, 46(2).
* Karlis, D., y Ntzoufras, I. (2003). Analysis of sports data by using bivariate Poisson models. *The Statistician*, 52(3).
* Hvattum, L. M., y Arntzen, H. (2010). Using ELO ratings for match result prediction in association football. *International Journal of Forecasting*, 26(3).
* Štrumbelj, E. (2014). On determining probability forecasts from betting odds. *International Journal of Forecasting*, 30(4).
* Constantinou, A. C., y Fenton, N. E. (2012). Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models. *JQAS*, 8(1).
* Wheatcroft, E. (2019). Evaluating probabilistic forecasts of football matches: the case against the ranked probability score. arXiv:1908.08980.
* Mitchell, M., et al. (2019). Model Cards for Model Reporting. *FAT\* '19*.
