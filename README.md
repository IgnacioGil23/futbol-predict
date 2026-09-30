# Football Match Predictor — Premier League

Modelo de goles esperados (Poisson, estilo Maher 1982 / Dixon-Coles 1997) para la Premier League,
evaluado contra las probabilidades implícitas del mercado de apuestas. **En construcción.**

## Estado

- [x] Datos: descarga, parser robusto y validación (`src/data/`)
- [x] EDA y auditoría de fuga temporal (`notebooks/01_eda.ipynb`)
- [x] Feature engineering: Elo propio ajustado, forma, tabla, head-to-head, congestión (`src/features/`, `notebooks/02_features.ipynb`)
- [ ] Modelo + tracking con MLflow
- [ ] API (FastAPI + Docker) y web
- [ ] Model card

## Reproducir

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
python -m src.data.download   # Football-Data.co.uk (E0 + E1) y snapshots de Elo
python -m src.data.load       # data/processed/matches.parquet + data_quality.json
python -m src.features.tune_elo   # (opcional) re-ajusta el Elo -> configs/elo_params.json
python -m src.features.build  # data/processed/features.parquet + elo_history.parquet
pytest
```

## Datos

| Dato | Fuente |
|---|---|
| Resultados, estadísticas y cuotas | [Football-Data.co.uk](https://www.football-data.co.uk/) ([notes.txt](https://www.football-data.co.uk/notes.txt)) |
| Elo de comparación (ClubElo) | [Club Football Match Data](https://github.com/xgabora/Club-Football-Match-Data) (A. Gábor), `EloRatings.csv` |

Hallazgos de calidad de datos y decisiones: ver `notebooks/01_eda.ipynb`.
