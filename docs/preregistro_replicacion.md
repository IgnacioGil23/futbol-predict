# Preregistro: replicación del candidato de tiros en otras ligas y análisis entre ligas

Fijado el 30/09/2026, **antes** de evaluar el candidato en otras ligas. De esos datos solo se miró la integridad
(`reports/replication/calidad_ligas.json`) y la cobertura de las variables: ningún resultado, ninguna relación
entre variables y goles. Cualquier cambio posterior queda en el historial de git y tiene que justificarse.

## Pregunta

El candidato de tiros mejoró el log loss en la Premier en 11 de 11 temporadas, pero sin alcanzar la regla de
promoción (selección: −0,0042, IC [−0,0078; −0,0007]; confirmación 2023-26: −0,0052, IC [−0,0111; +0,0006]).
¿La señal existe también en España, Italia, Alemania y Francia?

**Alcance:** evidencia complementaria. La decisión sobre la Premier sigue siendo la de
[preregistro_tiros.md](preregistro_tiros.md), en julio de 2027 (el candidato con xG se retiró el 01/10/2026: ver la
model card); esta
replicación no la reemplaza ni la modifica.

## Datos

* Football-Data.co.uk, primera y segunda división de cada país (SP1/SP2, I1/I2, D1/D2, F1/F2), 2000-01 a 2025-26,
  con el mismo lector y los mismos controles que la Premier (`src/data/leagues.py`).
* Limitaciones conocidas, que juegan **en contra** de replicar (diluyen el efecto):
  * las segundas divisiones tienen tiros recién desde 2017-18: antes, los equipos que ascienden llegan sin tiros
    recientes (su variable queda desactualizada o se imputa);
  * el Elo usa los parámetros ajustados en Inglaterra (`configs/elo_params.json`), sin reajustar para cada liga.
* Francia 2019-20 (primera y segunda) está incompleta en los datos (279 y 280 de 380 partidos), y a la Ligue 2 le
  falta un partido en 2023-24 y otro en 2025-26: se usan los partidos jugados.

## Modelos (idénticos a la Premier)

* **Base:** dos regresiones de Poisson (goles del local y del visitante) sobre la diferencia de Elo, α = 1e-4.
* **Candidato:** la misma base más tiros y tiros al arco a favor y en contra, local y visitante, media
  exponencial con vida media 4 (`src/models/confirm_shots.CANDIDATE`). No se vuelve a elegir nada.

## Protocolo

* **Evaluación:** cada temporada de 2015-16 a 2025-26 (11 temporadas; 15.583 partidos de primera división en
  total) se predice con modelos entrenados desde la primera temporada con tiros completos en la primera división
  de esa liga (España y Francia 2005-06; Italia y Alemania 2006-07) hasta la anterior. Base y candidato usan la
  misma ventana.
* **Métrica:** log loss de local/empate/visitante, candidato − base, en los mismos partidos.
* **Resultado principal:** las cuatro ligas juntas, con IC 95% por bootstrap pareado **estratificado por liga**
  (10.000 remuestreos, semilla 0).
  * **Señal replicada:** el IC 95% queda completamente por debajo de 0.
  * **Magnitud relevante:** además, la diferencia media es ≤ −0,005 (el margen de la regla de promoción).
* **Secundarios (no deciden):** cada liga con su IC; temporadas en que mejora; log loss de Bet365 pre-cierre en
  los mismos partidos, como contexto.

## Análisis entre ligas (descriptivo, no decide nada)

* **Relación Elo → goles** en cada liga (y en la Premier), temporadas 2005-06 a 2025-26: goles esperados del local
  y del visitante con Elo parejo, y cuánto se multiplican cada 100 puntos de diferencia, con IC 95% por bootstrap
  de partidos; tasa de empates.
* **Transferencia:** para 2023-24 a 2025-26 de cada liga destino, el modelo base entrenado con cada liga origen
  contra el de la propia liga (misma ventana expansiva).

## Qué pasa en cada escenario

* **Señal replicada con magnitud relevante:** evidencia fuerte de que los tiros aportan; se documenta como apoyo
  al candidato de tiros, sin cambiar la regla de julio de 2027.
* **Señal replicada sin magnitud relevante:** la señal es real pero chica; se documenta.
* **No se replica:** se documenta como evidencia en contra de que la mejora en la Premier sea general.
* En todos los casos, el resultado y el análisis entre ligas van a la model card.
