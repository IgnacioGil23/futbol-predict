# Marcador Probable · cinco ligas

Modelo de Machine Learning que estima la **probabilidad de cada marcador exacto** de un partido de cinco ligas
(Premier League, LaLiga, Serie A, Bundesliga y Ligue 1; y de ahí local / empate / visitante), evaluado con honestidad
contra el mercado de apuestas. Incluye el pipeline de datos, la experimentación, una API y una web interactiva con
selector de liga.

[English version](README.md) · **[Web](https://ignaciogil23.github.io/futbol-predict/)** · **[Model card](docs/model_card.md)**

> **Resultado en una línea:** en test (2023-26), el modelo queda a 0,008 de log loss del mercado (Bet365 pre-cierre;
> IC 95% 0,001 a 0,014): **no le gana al mercado**, pero desde que usa un Elo que aprende de las cuotas de partidos
> anteriores la brecha bajó a un tercio (era 0,022). Está bien calibrado. Detalle en el [model card](docs/model_card.md).

**Después del modelo base** (todo preregistrado; detalle en el model card):

* **Comparación con la literatura:** RPS 0,1942 contra 0,1953 del mejor modelo de Ley et al. (2019), en los mismos
  3.300 partidos.
* **Lo que mejora:** un rating basado en cuotas de partidos anteriores (ELO-Odds, Wunderlich y Memmert 2018): −0,0084
  de log loss en 19.763 partidos de cinco ligas, IC 95% [−0,0100; −0,0067]; reduce a la mitad la brecha con Bet365,
  cumple la regla preregistrada y está en producción desde el 01/10/2026 (el modelo anterior se registra en
  paralelo). También los tiros (−0,004 a −0,005, replicado en otras cuatro ligas), que se registran en paralelo y se
  deciden en julio de 2027.
* **Descartado con evidencia:** Poisson bivariado, ventaja de local reciente y modelos combinados de 5 ligas, lineal y
  XGBoost. Dos experimentos con datos de terceros (Fantasy Premier League y Transfermarkt) se retiraron por los términos
  de uso de esas fuentes.
* **Análisis de errores:** la brecha con el mercado está en la información de cada partido (la mitad sale del 14% de
  partidos con mayor desacuerdo) y se duplica en las fechas 1 a 5.

## Cinco ligas

El producto cubre la Premier League (Inglaterra), LaLiga (España), la Serie A (Italia), la Bundesliga (Alemania) y la
Ligue 1 (Francia). La web tiene un selector de liga y todas las secciones (partidos y previas, tabla y proyección de la
temporada, estadísticas, fichas de equipo, revisión fuera de muestra, monitoreo) funcionan por liga; la API acepta
`league` (`ENG`, `ESP`, `ITA`, `GER`, `FRA`; por defecto `ENG`).

* **El mismo modelo en todas:** Elo basado en cuotas (ELO-Odds) → dos regresiones de Poisson (goles del local y del
  visitante) → probabilidad de cada marcador exacto. Las regresiones de cada liga se entrenan con sus propios partidos
  (Premier desde 2004-05, España y Francia desde 2005-06, Italia y Alemania desde 2006-07). Datos: primera y segunda
  división de Football-Data.co.uk (SP1/SP2, I1/I2, D1/D2, F1/F2); calendarios de openfootball (espana, italy,
  deutschland, europe/france).
* **Los parámetros de rating propios de cada liga se probaron y se descartaron.** Con un preregistro
  ([`docs/preregistro_ligas.md`](docs/preregistro_ligas.md), reporte `reports/leagues/parametros_2026-10-27.json`),
  los dos ratings de cada liga se reajustaron con su primera división 2004-05..2014-15 y se compararon fuera de muestra
  (2015-16..2025-26) con los parámetros de Inglaterra. Regla: adoptarlos solo si la diferencia media de log loss es
  ≤ −0,002 y el IC 99,375% (Bonferroni, 8 comparaciones) queda entero por debajo de 0. Ninguna de las 8 comparaciones
  la cumplió (liga menos Inglaterra entre −0,0002 y +0,0011), así que todas usan los parámetros ajustados en Inglaterra.

| Liga | Log loss del modelo | Bet365 pre-cierre |
|---|---|---|
| LaLiga | 0,9640 | 0,9529 |
| Serie A | 0,9771 | 0,9668 |
| Bundesliga | 0,9769 | 0,9614 |
| Ligue 1 | 0,9891 | 0,9819 |

Test 2023-24 a 2025-26 (las cifras de la Premier están arriba).

* **Simulación de la temporada por liga** (modelo con Elo de resultados), validada con el protocolo de la Premier
  (cortes proporcionales a la temporada: antes de la fecha 1 y tras el 26%, 53% y 79% de los partidos; plazas de
  descenso de cada liga; Francia 2019-20 omitida; reportes en `reports/season/<LIGA>_evaluacion_2026-10-27.json`).
  Habilidad contra el simulador con equipos iguales antes de la fecha 1, top 4: España 71%, Italia 50%, Alemania 49%,
  Francia 35%; campeón: España 27%, Italia 39%, Alemania 72%, Francia 50% (intervalos de 95% en los reportes). No
  modela el desempate por enfrentamiento directo (LaLiga, Serie A); en Bundesliga y Ligue 1 el 16.º juega un
  repechaje y no se cuenta como descendido.
* **Monitoreo en vivo:** el registro de la Premier sigue igual; el flujo de monitoreo también guarda las predicciones
  previas de las demás ligas (`ledger/<LIGA>_predictions.csv` en la rama `monitoring`). Su evaluación en vivo todavía
  no está implementada: solo se evalúa el registro de la Premier.
* Escudos (de las cinco ligas) y fotos de estadio de las otras ligas: de Wikimedia Commons (solo licencias libres, con créditos en cada
  ficha). Hay foto para 71 de los 76 clubes actuales y escudo para 32; el resto muestra iniciales de 3 letras (la
  mayoría de los escudos españoles y franceses tienen derechos de autor y no están en Commons). Los clubes de la Premier
  muestran iniciales: ninguno de sus escudos actuales está en Commons con licencia libre, y los términos de
  premierleague.com no permiten reutilizarlos.

## Qué hay adentro

| Etapa | Qué se hizo | Dónde |
|---|---|---|
| Datos | Descarga de Football-Data.co.uk (Premier + Championship, 2000-2026), parser robusto (recupera 90 partidos que un dataset derivado había perdido), validaciones automáticas | `src/data/` |
| EDA | Calidad de datos, auditoría de fuga temporal, distribución de goles, ventaja de local por era COVID, calibración del mercado | `notebooks/01_eda.ipynb` |
| Features | Elo propio partido a partido (ajustado solo con entrenamiento), forma, tabla, descanso, head-to-head; tests de "invariancia al futuro" contra la fuga | `src/features/`, `notebooks/02_features.ipynb` |
| Modelos | Frecuencias, logit sobre Elo, Dixon-Coles (MLE con gradiente analítico), Poisson GLM, XGBoost Poisson; split temporal, bootstrap pareado vs mercado, MLflow | `src/models/`, `notebooks/03_modelo.ipynb` |
| Servicio | Modelo exportado como JSON (sin pickle), consultas "a una fecha" sin fuga, FastAPI + Docker multi-etapa, deploy en Cloud Run | `src/serving/`, `src/api/`, `Dockerfile`, `docs/deploy_cloud_run.md` |
| Web | React + TypeScript + D3: próximas jornadas y previa con grilla de marcadores, simulación de la temporada, fichas de equipo (con la foto de su estadio, de Wikimedia Commons), revisión histórica fuera de muestra, monitoreo y metodología | `web/` |
| Automatización | CI, publicación de la web, deploy de la API, monitoreo diario y reentrenamiento por PR | `.github/workflows/` |

## Decisiones que vale la pena mirar

* **Auditar la fuente antes de modelar.** El README del dataset original decía "Bet365" para las cuotas; cruzándolo con
  los CSV originales resultó ser una mezcla de casas según la temporada. Por eso la fuente base cambió.
* **Anti-fuga verificada, no supuesta.** Toda variable del día *D* usa partidos de días anteriores. Tests que borran los
  resultados desde *D* y exigen que las variables del día *D* no cambien, en datos sintéticos y reales. Durante el
  desarrollo detectaron una fuga real (el Elo de arranque de un equipo recién ascendido, consultado antes de su debut,
  dependía de resultados posteriores) y un error de tipos; ambos quedaron corregidos y cubiertos por tests.
* **Lo simple ganó.** Con validación temporal y comparación pareada, ninguna variable extra ni modelo más complejo
  mejoró al Poisson con diferencia de Elo. Se reporta así.
* **El mismo modelo en Python y en TypeScript**, verificado a 10 decimales con vectores exportados desde Python: la
  previa "de hoy" se calcula en el navegador al instante; la API queda para fechas históricas.

## Monitoreo en producción

* **Registro inmutable** (rama `monitoring`): antes de cada partido se guarda la predicción, una sola vez, con la
  versión del modelo y las cuotas del momento. El workflow verifica que solo se agreguen filas.
* **Evaluación diaria** contra el resultado y el mercado: brecha de log loss, goles y empates esperados contra reales
  y residuo de localía, en ventanas de 190 partidos. Los umbrales salen de un backtest de 10 temporadas
  (`configs/monitoring_thresholds.json`), no de valores elegidos a ojo.
* **Alertas** como issues de GitHub, que disparan una evaluación de modelos candidatos.
* **Reentrenamiento champion/challenger**: el anual (1 de julio) llega como PR con controles de sanidad; los
  candidatos se promueven solo con una mejora ≥ 0,005 de log loss y un IC 95% pareado por debajo de 0.
* Página pública: `/#/monitoreo` en la web.

## Reproducir

```bash
python -m venv venv
venv\Scripts\activate                      # Windows (en Linux/macOS: source venv/bin/activate)
pip install -r requirements-dev.txt

python -m src.data.download                # Football-Data.co.uk (E0 + E1) y snapshots de ClubElo
python -m src.data.load                    # data/processed/matches.parquet + data_quality.json
python -m src.data.leagues                 # las otras cuatro ligas (primera y segunda división)
python -m src.features.tune_elo            # (opcional) re-ajusta el Elo -> configs/elo_params.json
python -m src.features.build               # features.parquet + elo_history.parquet
python -m src.models.experiments --stage validation   # selección (registra en MLflow: mlflow.db)
python -m src.models.experiments --stage test         # evaluación final (una sola vez)
python -m src.serving.production           # modelo de producción -> models/production/model.json
python -m src.serving.league_state         # estado del rating por liga
python -m src.serving.league_models --train           # modelos de Poisson por liga
python -m src.models.league_params         # control de parámetros de rating por liga
python -m src.models.season_eval --league ESP         # evaluación de la simulación de temporada (por liga)
python -m src.export.site --out web/public/data       # JSON para la web
pytest && ruff check .                     # tests y lint (igual que en CI)
```

API local:

```bash
uvicorn src.api.main:app --reload
```

Web local (requiere haber corrido el export):

```bash
cd web && npm install && npm run dev
```

## Despliegue

* **Web:** GitHub Pages, publicada por `.github/workflows/deploy.yml` (lunes y jueves, o a mano). La URL de la API se
  configura en la variable de Actions `API_URL`.
* **API:** Google Cloud Run, desplegada por `.github/workflows/deploy-api.yml` con Workload Identity Federation (sin
  claves JSON). Escala a cero, máximo 2 instancias; la imagen descarga y procesa los datos al construirse, así que los
  datos no se versionan. Configuración inicial paso a paso: [docs/deploy_cloud_run.md](docs/deploy_cloud_run.md).
* La imagen de la API es mínima (FastAPI, numpy, pandas: sin scipy ni pyarrow); arranca en ~5 s y usa ~125 MB de RAM
  con los datos completos (medido localmente).

## Datos y atribución

| Dato | Fuente |
|---|---|
| Resultados, estadísticas y cuotas | [Football-Data.co.uk](https://www.football-data.co.uk/) ([notes.txt](https://www.football-data.co.uk/notes.txt)) |
| Elo de comparación (ClubElo) | [Club Football Match Data](https://github.com/xgabora/Club-Football-Match-Data) (A. Gábor), `EloRatings.csv` |
| Calendario de las próximas jornadas | openfootball ([england](https://github.com/openfootball/england), [espana](https://github.com/openfootball/espana), [italy](https://github.com/openfootball/italy), [deutschland](https://github.com/openfootball/deutschland), [europe/france](https://github.com/openfootball/europe)) (dominio público) |
| Escudos (web, todas las ligas) | Logo de cada club en Wikidata, alojado en [Wikimedia Commons](https://commons.wikimedia.org/), solo con licencia libre (dominio público, CC0, CC BY/BY-SA con crédito); marcas registradas de cada club, mostradas solo como referencia visual (`src/export/league_media.py`) |
| Fotos de estadios (web) | Imagen principal del artículo de cada estadio en Wikipedia, en [Wikimedia Commons](https://commons.wikimedia.org/) con licencia CC BY / CC BY-SA; autor y licencia junto a cada foto (`src/export/stadiums.py`, `src/export/league_media.py`) |

Proyecto educativo. **No es una recomendación de apuestas.**

## Licencia

El código se publica con [licencia MIT](LICENSE). Los datos, escudos y fotos pertenecen a sus fuentes y conservan
sus propios términos (ver la tabla de arriba).
