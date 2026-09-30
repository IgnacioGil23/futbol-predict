# Marcador Probable · Premier League

Modelo de Machine Learning que estima la **probabilidad de cada marcador exacto** de un partido de la Premier League
(y de ahí local / empate / visitante), evaluado con honestidad contra el mercado de apuestas. Incluye el pipeline de
datos, la experimentación, una API y una web interactiva.

> **Resultado en una línea:** en test (2023-26), el modelo queda a ~0,02 de log loss del mercado (Bet365 pre-cierre),
> una brecha estadísticamente significativa: **no le gana al mercado**, pero está bien calibrado y un modelo de 4
> parámetros empata con Dixon-Coles y XGBoost. Detalle en el [model card](docs/model_card.md).

## Qué hay adentro

| Etapa | Qué se hizo | Dónde |
|---|---|---|
| Datos | Descarga de Football-Data.co.uk (Premier + Championship, 2000-2026), parser robusto (recupera 90 partidos que un dataset derivado había perdido), validaciones automáticas | `src/data/` |
| EDA | Calidad de datos, auditoría de fuga temporal, distribución de goles, ventaja de local por era COVID, calibración del mercado | `notebooks/01_eda.ipynb` |
| Features | Elo propio partido a partido (ajustado solo con entrenamiento), forma, tabla, descanso, head-to-head; tests de "invariancia al futuro" contra la fuga | `src/features/`, `notebooks/02_features.ipynb` |
| Modelos | Frecuencias, logit sobre Elo, Dixon-Coles (MLE con gradiente analítico), Poisson GLM, XGBoost Poisson; split temporal, bootstrap pareado vs mercado, MLflow | `src/models/`, `notebooks/03_modelo.ipynb` |
| Servicio | Modelo exportado como JSON (sin pickle), consultas "a una fecha" sin fuga, FastAPI + Docker multi-etapa, deploy en Cloud Run | `src/serving/`, `src/api/`, `Dockerfile`, `docs/deploy_cloud_run.md` |
| Web | React + TypeScript + D3: próximas jornadas y previa con grilla de marcadores, fichas de equipo, revisión histórica fuera de muestra, ventaja de local, metodología | `web/` |
| Automatización | CI (tests Python y TS, build de la web, build y smoke test de la imagen), publicación de la web y deploy de la API dos veces por semana | `.github/workflows/` |

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

## Reproducir

```bash
python -m venv venv
venv\Scripts\activate                      # Windows (en Linux/macOS: source venv/bin/activate)
pip install -r requirements-dev.txt

python -m src.data.download                # Football-Data.co.uk (E0 + E1) y snapshots de ClubElo
python -m src.data.load                    # data/processed/matches.parquet + data_quality.json
python -m src.features.tune_elo            # (opcional) re-ajusta el Elo -> configs/elo_params.json
python -m src.features.build               # features.parquet + elo_history.parquet
python -m src.models.experiments --stage validation   # selección (registra en MLflow: mlflow.db)
python -m src.models.experiments --stage test         # evaluación final (una sola vez)
python -m src.serving.production           # modelo de producción -> models/production/model.json
python -m src.export.site --out web/public/data       # JSON para la web
pytest
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
| Calendario de las próximas jornadas | [openfootball/england](https://github.com/openfootball/england) (dominio público) |

Proyecto educativo. **No es una recomendación de apuestas.**
