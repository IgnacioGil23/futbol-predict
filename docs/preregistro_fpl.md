# Preregistro: prueba histórica de xG (candidato A) y fuerza de la alineación (candidato B)

Fijado el 30/09/2026, **antes** de construir las variables y antes de ver cualquier resultado de estos
candidatos. Lo único que se miró de los datos es su integridad (`reports/fpl/calidad_archivo.json`):
ningún resultado, ninguna relación entre las variables y los goles. Cualquier cambio posterior queda en el
historial de git y tiene que justificarse en el propio commit.

## Preguntas

* **A.** ¿El xG reciente de cada equipo mejora la predicción hecha **días antes** del partido?
* **B.** ¿Saber **qué once titulares juegan** mejora la predicción hecha **una hora antes** del partido?
  B es además una cota aproximada del valor de conocer las lesiones: la alineación confirmada contiene más
  información que la lista de lesionados. Si B no mejora, no se construye la recolección de lesiones.

## Datos

* Archivo de Fantasy Premier League (`vaastav/Fantasy-Premier-League`, commit `9779cdb`), procesado y
  controlado por `src/data/fpl_archive.py`: 2022-23 a 2025-26, 380/380 partidos por temporada vinculados a
  Football-Data con el mismo marcador. En 2022-23, titulares y xG existen desde la fecha 16 (antes: faltantes).
* Football-Data: resultados y cuotas (Bet365 pre-cierre y Pinnacle al cierre).

## Variables (todas con datos estrictamente anteriores al partido, salvo la alineación del propio partido en B)

Se trabaja por equipo y partido de Premier League del archivo, en orden cronológico y sin cortar entre
temporadas (un equipo que desciende y vuelve continúa su serie; uno que asciende por primera vez desde 2022-23
empieza sin historia).

**A. xG móvil** (información disponible días antes):

* xG a favor de un equipo en un partido = suma de `expected_goals` de sus jugadores en ese partido.
* xG en contra = xG a favor del rival en ese partido (no se usa `expected_goals_conceded`, que es por jugador
  y solo cuenta el tiempo que estuvo en cancha).
* Variable: media exponencial con **vida media de 4 partidos** (misma vida media que el candidato de tiros,
  fijada, no elegida acá), `pandas.ewm(halflife=4)`, sobre los partidos anteriores del equipo con xG registrado,
  tomada de los partidos jugados **antes del día** del partido (igual que las demás variables del proyecto).
* Cuatro variables por partido: xG a favor y en contra del local y del visitante.
* Sin historia (primeros partidos de 2022-23 con datos, o equipos recién llegados): se imputa la mediana del
  conjunto de entrenamiento, como en el modelo de producción.

**B. Fuerza de la alineación** (información disponible una hora antes):

* Valor del XI de un equipo en un partido = suma de los precios de Fantasy (en esa fecha del torneo) de sus
  11 titulares.
* Valor habitual = promedio del valor del XI en los **5 partidos anteriores** del equipo con titulares
  registrados (con al menos 1; si hay menos de 5, los que haya).
* Variable: desviación relativa = valor del XI / valor habitual − 1.
* Dos variables por partido: la desviación del local y la del visitante.
* Sin partidos anteriores: desviación 0 (sin información no hay desviación).

## Modelo: corrección sobre el modelo de producción (offset)

Para cada temporada evaluada *S*:

1. El modelo de producción (Poisson sobre la diferencia de Elo, α = 1e-4) se entrena con 2002-03 a *S*−1,
   igual que en toda la evaluación del proyecto. Da log λ y log μ de cada partido.
2. El candidato agrega **solo** un término por regresión, sin intercepto:
   log λ' = log λ + x·β_local y log μ' = log μ + x·β_visitante, con x = variables del candidato
   estandarizadas (media y desvío del entrenamiento) y β estimado por máxima verosimilitud de Poisson con la
   misma penalización L2 que producción (α = 1e-4, objetivo de `sklearn.PoissonRegressor`).
3. β se estima con los partidos del archivo de temporadas anteriores a *S* (desde 2022-23; para A y B solo los
   partidos con la variable registrada o calculable). El modelo de producción que da el offset de esos partidos
   es el mismo del paso 1.
4. Si β = 0, el candidato es idéntico al modelo de producción.

Sin intercepto, el candidato no puede ganar por recalibrar el nivel de goles de una temporada: solo por la
información de sus variables.

## Evaluación

* **Temporadas:** 2023-24, 2024-25 y 2025-26 (1.140 partidos), cada una predicha con β estimado en las
  anteriores (para 2023-24: la segunda mitad de 2022-23 en B; todo 2022-23 con xG desde la fecha 16 en A).
* **Métrica:** log loss de local/empate/visitante, candidato − producción, en los mismos partidos; IC 95%
  por bootstrap pareado de partidos (10.000 remuestreos, semilla 0).
* **Regla (la de `src/models/challenger.py`), por candidato:** se promueve si la diferencia media es
  ≤ −0,005 **y** el IC 95% queda completamente por debajo de 0.
* **Reportes secundarios (no deciden):** diferencia por temporada; RPS; contra el mercado con la misma
  información (A contra Bet365 pre-cierre; B contra Pinnacle al cierre, en los partidos con esas cuotas);
  β estimados; y un **control para B**: la desviación del partido anterior del equipo (información disponible
  días antes), con el mismo modelo y los mismos partidos.

## Qué pasa en cada escenario

* **B cumple la regla:** se diseña la recolección diaria de lesiones de Fantasy y la predicción una hora antes
  del partido (con su propio plan y preregistro).
* **B no cumple:** se descarta la recolección de lesiones.
* **A cumple la regla:** se planifica llevar el xG a producción (xG en vivo desde la API de Fantasy), con
  registro en paralelo como el de tiros antes de reemplazar al modelo.
* **A no cumple:** se documenta; el candidato de tiros sigue su propio preregistro.
* Todos los resultados, favorables o no, se documentan en la model card.

## Limitaciones conocidas de antemano

* Con 1.140 partidos el IC 95% mide del orden de ±0,006: solo un efecto grande sale concluyente.
* Poca historia para estimar β (una temporada para predecir 2023-24), mitigado por estimar solo 2 a 4
  coeficientes sobre el modelo de producción.
* Las temporadas 2023-24 a 2025-26 se usaron para confirmar el candidato de tiros; para A y B no se usaron.
