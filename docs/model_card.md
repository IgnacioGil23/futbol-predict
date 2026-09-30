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

### Comparación con un resultado publicado

Ley, Van de Wiele y Van Eetvelde (2019) compararon 10 modelos en la Premier League 2008-09 a 2017-18, fechas 6 a
38 (3.300 partidos), con el RPS (misma fórmula que la nuestra). En esos partidos, cada temporada predicha con el modelo
entrenado con las anteriores:

| Modelo | RPS | IC 95% |
|---|---|---|
| Ley et al.: Poisson bivariado, 1 parámetro por equipo (el mejor de su estudio) | 0,1953 | no publicado |
| Ley et al.: Poisson independiente, 1 parámetro por equipo | 0,1954 | no publicado |
| **Nuestro modelo (Poisson + diferencia de Elo)** | **0,1942** | 0,1896 a 0,1987 |
| Mercado: Bet365 pre-cierre | 0,1917 | 0,1869 a 0,1965 |
| Mercado: Pinnacle cierre (desde 2012-13, n = 1.980) | 0,1899 | 0,1836 a 0,1961 |

* **Lectura:** nuestro modelo queda **al nivel** del mejor modelo del estudio (0,0011 menos de RPS), pero su valor cae
  dentro de nuestro intervalo: no se puede afirmar que sea mejor. Sin sus predicciones por partido no hay prueba pareada.
  Ninguno de los dos alcanza al mercado.
* **Diferencias de protocolo:**
  * Ellos reajustan el modelo en cada fecha con los dos años previos; nosotros, una vez por temporada con toda la
    historia (y el Elo, partido a partido).
  * Sin número de fecha en nuestros datos, "fechas 6 a 38" se aproxima quitando los primeros 50 partidos de cada
    temporada. Quitando en cambio los partidos en que algún equipo jugaba su quinto partido o uno anterior, el resultado
    es el mismo (0,1945, n = 3.294).
* **Ambos resultados son algo optimistas:** los parámetros de nuestro Elo se ajustaron con las temporadas de
  entrenamiento (2002-03 a 2020-21), que incluyen estas. La vida media de cada modelo de Ley et al. también se eligió
  como la de menor RPS en estos mismos partidos.
* Script: `src/analysis/literature_benchmark.py`; reporte: `reports/benchmarks/ley2019.json`.

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
* **Confirmación en temporadas no usadas para elegirlo** (2023-24 a 2025-26, 1.140 partidos; candidato único fijado
  antes de correr, misma regla): −0,0052 de log loss, IC 95% [−0,0111; +0,0006]. Mejora en las 3 temporadas
  (−0,0023, −0,0084, −0,0050), pero el IC incluye el 0: **no confirma**. Sumando ambas evaluaciones, el candidato
  mejoró en 11 de 11 temporadas; la decisión queda para cuando haya más partidos no vistos. Reporte:
  `reports/challengers/confirmacion_tiros_2026-09-30.json`; script: `src/models/confirm_shots.py`.
* **Registro en paralelo durante 2026-27** ([preregistro](preregistro_tiros.md)): el candidato quedó congelado
  (`models/shadow/model.json`, versión `ec5a7a4752bc`, entrenado con 2002-03 a 2025-26) y el monitoreo diario guarda
  su predicción antes de cada partido en `ledger/shadow_predictions.csv` (rama `monitoring`). Sus variables se calculan
  con la misma función que en el entrenamiento; en los 50 partidos ya jugados de 2026-27 coinciden con la tabla de
  features salvo el redondeo a 6 decimales del CSV. La decisión se toma una sola vez, en julio de 2027.

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

### xG y fuerza de la alineación con datos de Fantasy Premier League (30/09/2026) · **A en observación, B descartado**

* **Datos:** archivo histórico de Fantasy (`vaastav/Fantasy-Premier-League`, commit fijado), 2022-23 a 2025-26:
  380/380 partidos por temporada vinculados a Football-Data con el mismo marcador; precio de cada jugador en cada fecha
  del torneo, verificado contra el precio inicial (100%) y contra la API oficial (30/30). Controles y correcciones en
  `src/data/fpl_archive.py` y `reports/fpl/calidad_archivo.json`.
* **Preregistro** ([docs/preregistro_fpl.md](preregistro_fpl.md)), commiteado antes de construir las variables:
  * **A:** xG a favor y en contra, media exponencial con vida media 4, información de días antes.
  * **B:** precio de los 11 titulares respecto de los 5 partidos anteriores, información de una hora antes. B es además una
    cota del valor de conocer las lesiones.
  * Ambos como corrección sin intercepto sobre el modelo de producción; 2023-24 a 2025-26; la regla de siempre.

| Candidato (diferencia contra producción) | Log loss | IC 95% | Por temporada |
|---|---|---|---|
| **A: xG móvil** | **−0,0059** | [−0,0115; −0,0002] | +0,0064 · −0,0191 · −0,0050 |
| B: fuerza de la alineación | +0,0006 | [−0,0023; +0,0036] | +0,0021 · −0,0022 · +0,0020 |
| Control: alineación del partido anterior | −0,0001 | [−0,0052; +0,0049] | — |

* **B: no mejora.** Conocer los 11 titulares no aporta sobre el Elo; por el preregistro, **se descarta la recolección de
  lesiones** (la alineación confirmada contiene más información que la lista de lesionados).
* **A: cumple la regla, con fragilidad.** El IC queda apenas por debajo de 0 y, corrigiendo por los 2 candidatos
  (IC 97,5%), incluye el 0 ([−0,0123; +0,0007]). Empeora en 2023-24, la temporada con menos datos para estimar la
  corrección (234 partidos). La mejora no depende de pocos partidos: los 20 de mayor diferencia van, en conjunto, en
  contra de A. Reduce la brecha con Bet365 de +0,022 a +0,016.
* **Decisión, como fija el preregistro:** A no pasa directo a producción. Se registra en paralelo durante 2026-27 y se
  decide en julio de 2027 junto con el candidato de tiros; como probablemente miden la misma señal, se elegirá uno.
* Reporte: `reports/challengers/fpl_2026-09-30.json`; código: `src/features/fpl_features.py`, `src/models/fpl_eval.py`.
* **Registro en paralelo durante 2026-27** ([preregistro](preregistro_xg.md), commiteado antes de congelar el
  candidato): A quedó congelado (`models/shadow_xg/model.json`, versión `a12662418789`, corrección estimada con 1.369
  partidos sobre el modelo de producción `ced0b252cafe`, cuyos parámetros se copian dentro del artefacto). El monitoreo
  diario captura el xG por equipo de cada partido terminado desde la API de Fantasy (`ledger/xg_team_matches.csv`,
  solo se agregan filas y el primer valor es el definitivo) y registra la predicción de A antes de cada partido
  (`ledger/shadow_xg_predictions.csv`). Controles: el xG capturado en vivo coincide con el del archivo en la fecha 1
  de 2026-27 (20/20 equipos-partido) y las variables calculadas con la historia guardada coinciden con las de la prueba
  histórica. En julio de 2027 se decide con la regla de siempre y, si A y los tiros cumplen, con el desempate
  preregistrado (ante una diferencia no concluyente, los tiros).

### Análisis de errores: dónde pierde el modelo contra el mercado (30/09/2026)

Descriptivo (no elige ningún modelo). Premier 2015-16 a 2025-26 (4.180 partidos), cada temporada predicha por el
modelo de producción entrenado con las anteriores, contra Bet365 pre-cierre. Brecha media: +0,016 de log loss. Cortes
fijados antes de mirar (`src/analysis/error_analysis.py`, `reports/analysis/analisis_errores_2026-09-30.json`):

* **Sesgo de local.** Probabilidad media de victoria local: modelo 46,2%, mercado 44,5%, realidad 44,3% (visitante:
  30,3%, 31,8% y 32,0%). El modelo queda por encima del mercado en las 11 temporadas: la ventaja de local se estima con
  toda la historia desde 2002-03, cuando era mayor (ver la limitación sobre la ventaja de local).
* **Primeras fechas y ascendidos.** En las fechas 1 a 5 la brecha es +0,031 (el doble del promedio; 25% de la brecha con
  13% de los partidos), y +0,050 cuando juega un ascendido. Desde la fecha 20, +0,014.
* **Desacuerdo.** Cuando modelo y mercado difieren en menos de 5 puntos en P(local) (53% de los partidos), la brecha es
  +0,001; cuando difieren 10 puntos o más (14%), +0,059: la mitad de la brecha total.
* **Consecuencias:** candidatos preregistrados a partir de acá (ventaja de local reciente, información de pretemporada
  y un modelo con las cinco ligas); ver las secciones siguientes.

### Replicación de los tiros en otras ligas y relación Elo → goles entre ligas (30/09/2026)

* **Preregistro** ([docs/preregistro_replicacion.md](preregistro_replicacion.md)), commiteado antes de evaluar. Mismo
  candidato y mismo modelo de base que en la Premier, en España, Italia, Alemania y Francia (primera y segunda división de
  Football-Data, mismos controles; `reports/replication/calidad_ligas.json`), Elo con los parámetros de Inglaterra sin
  reajustar, temporadas 2015-16 a 2025-26 (15.583 partidos). Es evidencia complementaria: no cambia la decisión de julio
  de 2027 sobre la Premier.

| Liga | Partidos | Candidato − base (log loss) | IC 95% | Temporadas que mejora |
|---|---|---|---|---|
| España | 4.180 | −0,0041 | [−0,0069; −0,0013] | 8/11 |
| Italia | 4.180 | −0,0062 | [−0,0091; −0,0034] | 11/11 |
| Alemania | 3.366 | −0,0054 | [−0,0088; −0,0019] | 9/11 |
| Francia | 3.857 | −0,0039 | [−0,0065; −0,0012] | 8/11 |
| **Las cuatro (principal)** | **15.583** | **−0,0049** | **[−0,0063; −0,0035]** | — |

* **La señal se replica:** mejora en las cuatro ligas, cada una con su IC por debajo de 0, y en el conjunto. **No alcanza
  la "magnitud relevante" preregistrada** (≤ −0,005): queda en −0,0049. El efecto es consistente con la Premier
  (−0,0042 en la selección, −0,0052 en la confirmación): los tiros aportan de verdad, y el tamaño está justo en el borde
  del margen de promoción. Con el sesgo en contra declarado (segundas divisiones sin tiros antes de 2017-18), es
  probablemente una estimación conservadora.
* **Contexto:** el modelo de base queda detrás de Bet365 pre-cierre en todas las ligas (de +0,016 a +0,022 de log loss),
  como en la Premier.

**Relación Elo → goles, 2005-06 a 2025-26** (IC 95% por bootstrap de partidos):

| Liga | Goles del local con Elo parejo | × por cada 100 puntos a favor | Goles del visitante con Elo parejo | × por cada 100 puntos a favor del local | Empates |
|---|---|---|---|---|---|
| Inglaterra | 1,48 [1,45; 1,50] | 1,18 [1,17; 1,19] | 1,14 [1,12; 1,17] | 0,85 [0,84; 0,85] | 24,3% |
| España | 1,46 [1,44; 1,49] | 1,19 [1,18; 1,21] | 1,08 [1,06; 1,11] | 0,85 [0,84; 0,86] | 24,9% |
| Italia | 1,44 [1,41; 1,46] | 1,16 [1,15; 1,18] | 1,13 [1,11; 1,15] | 0,85 [0,84; 0,86] | 26,4% |
| Alemania | 1,61 [1,58; 1,64] | 1,18 [1,17; 1,20] | 1,27 [1,24; 1,30] | 0,85 [0,84; 0,86] | 25,1% |
| Francia | 1,40 [1,37; 1,42] | 1,19 [1,17; 1,20] | 1,07 [1,04; 1,09] | 0,84 [0,83; 0,85] | 27,3% |

* **La forma de la relación es casi universal:** 100 puntos de Elo a favor multiplican los goles del local por 1,16 a
  1,19 y los del visitante por 0,84 a 0,85 en las cinco ligas. Lo que cambia es el **nivel**: la Bundesliga tiene más
  goles con Elo parejo y la Ligue 1, menos.
* **Transferencia** (modelo entrenado en otra liga, prediciendo 2023-24 a 2025-26): las diferencias contra el modelo de la
  propia liga van de −0,002 a +0,005; la mayoría no se distinguen de 0. Las que empeoran de forma clara son, sobre todo,
  por el nivel de goles (por ejemplo, España predicha con el modelo de Alemania: +0,0042).
* **Lectura:** por eso sumar ligas no mejoraría el modelo de la Premier (la pendiente ya está bien estimada y el nivel
  es propio de cada liga), pero sí sirve para validar que una señal no es una casualidad de una liga.
* Reporte: `reports/replication/replicacion_2026-09-30.json`; código: `src/data/leagues.py`, `src/models/replication.py`.

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
* Ley, C., Van de Wiele, T., y Van Eetvelde, H. (2019). Ranking soccer teams on the basis of their current strength: A comparison of maximum likelihood approaches. *Statistical Modelling*, 19(1).
* Karlis, D., y Ntzoufras, I. (2003). Analysis of sports data by using bivariate Poisson models. *The Statistician*, 52(3).
* Hvattum, L. M., y Arntzen, H. (2010). Using ELO ratings for match result prediction in association football. *International Journal of Forecasting*, 26(3).
* Štrumbelj, E. (2014). On determining probability forecasts from betting odds. *International Journal of Forecasting*, 30(4).
* Constantinou, A. C., y Fenton, N. E. (2012). Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models. *JQAS*, 8(1).
* Wheatcroft, E. (2019). Evaluating probabilistic forecasts of football matches: the case against the ranked probability score. arXiv:1908.08980.
* Mitchell, M., et al. (2019). Model Cards for Model Reporting. *FAT\* '19*.
