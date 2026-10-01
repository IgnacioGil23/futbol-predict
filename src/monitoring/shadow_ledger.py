"""Registros en paralelo de los modelos en evaluación.

* "tiros": el candidato de tiros (docs/preregistro_tiros.md).
* "elo": el modelo de producción anterior (Poisson sobre el Elo de resultados, congelado en models/elo/model.json),
  desde que el rating basado en cuotas pasó a producción (enmienda de docs/preregistro_cuotas.md): permite comparar
  los dos en vivo durante 2026-27.

Mismas reglas que src/monitoring/ledger.py (clave, solo partidos con fecha posterior al día de la corrida, la
primera predicción es la definitiva, solo se agregan filas), un archivo por modelo para no tocar el formato del
registro del modelo de producción. No se publican ni se evalúan durante la temporada: la comparación se hace una
sola vez, en julio.

Cada modelo en evaluación se describe con un `ShadowModel`: su predictor congelado, las columnas de sus
variables y cómo calcularlas para partidos concretos. Las filas del registro son: identificación del partido,
Elo de ambos equipos, las variables del modelo (para poder auditarlas) y su predicción.

La primera corrida de cada registro, con el archivo todavía inexistente, agrega una única vez los partidos ya
jugados de la temporada en curso con source = "reconstruido".

Uso (lo corre el workflow diario):
    python -m src.monitoring.shadow_ledger --model tiros --ledger monitoring/ledger/shadow_predictions.csv
    python -m src.monitoring.shadow_ledger --model elo --ledger monitoring/ledger/shadow_elo_predictions.csv
"""

import argparse
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PREMIER_LEAGUE, season_label, season_start_year
from src.monitoring.ledger import KEY, append_entries, read_ledger
from src.serving.shadow import SHOT_COLUMNS
from src.serving.store import MatchStore

logger = logging.getLogger(__name__)

DEFAULT_SHADOW_LEDGER = Path("monitoring/ledger/shadow_predictions.csv")
DEFAULT_LEDGERS = {"tiros": DEFAULT_SHADOW_LEDGER, "elo": Path("monitoring/ledger/shadow_elo_predictions.csv")}


def ledger_columns(feature_columns: list[str]) -> list[str]:
    return ["season", "season_start", "home_team", "away_team", "match_date",
            "logged_at_utc", "source", "model_version", "code_commit",
            "elo_home", "elo_away", *feature_columns,
            "lam", "mu", "p_home", "p_draw", "p_away"]


SHADOW_COLUMNS = ledger_columns(SHOT_COLUMNS)          # registro de tiros (formato fijo desde 2026-09-30)
SHADOW_ELO_COLUMNS = ledger_columns([])                 # registro del modelo anterior (formato fijo desde 2026-10-01)


@dataclass
class ShadowModel:
    name: str
    predictor: object                                   # .version y .predict(rows) -> lam, mu, probs
    feature_columns: list[str]
    features: Callable[[pd.DataFrame], pd.DataFrame]    # targets (date, home_team, away_team) -> + variables

    @property
    def columns(self) -> list[str]:
        return ledger_columns(self.feature_columns)


def shots_model(matches: pd.DataFrame, predictor=None) -> ShadowModel:
    from src.serving.shadow import ShadowPredictor, shot_features_for
    return ShadowModel("tiros", predictor or ShadowPredictor.load(), SHOT_COLUMNS,
                       lambda t: shot_features_for(matches, t))


class FrozenEloModel:
    """Adapta el predictor del modelo de Elo (artefacto JSON) a la interfaz de los modelos en evaluación."""

    def __init__(self, predictor):
        self.predictor = predictor
        self.version = predictor.version

    def predict(self, rows: pd.DataFrame):
        from src.models.scoreline import outcome_probabilities, score_matrix
        from src.serving.shadow import ShadowForecast
        lam, mu = self.predictor.rates(rows["elo_diff"].to_numpy(float))
        return ShadowForecast(lam=lam, mu=mu, probs=outcome_probabilities(score_matrix(lam, mu)))


def elo_model(predictor=None) -> ShadowModel:
    if predictor is None:
        from src.serving.predictor import EloPoissonPredictor
        from src.serving.production import ELO_MODEL_PATH
        predictor = FrozenEloModel(EloPoissonPredictor.load(ELO_MODEL_PATH))
    return ShadowModel("elo", predictor, [], lambda t: t.copy())


def _rows(targets: pd.DataFrame, model: ShadowModel, store: MatchStore, now: datetime, source: str,
          code_commit: str) -> pd.DataFrame:
    """Predicción del modelo para `targets` (date, home_team, away_team); descarta los que no tengan Elo."""
    if targets.empty:
        return pd.DataFrame(columns=model.columns)
    rows = model.features(targets)
    elo = []
    for r in rows.itertuples(index=False):
        try:
            elo.append((store.elo_as_of(r.home_team, r.date), store.elo_as_of(r.away_team, r.date)))
        except KeyError:
            elo.append((None, None))
    rows["elo_home"] = [np.nan if h is None else h for h, _ in elo]
    rows["elo_away"] = [np.nan if a is None else a for _, a in elo]
    missing = rows[["elo_home", "elo_away"]].isna().any(axis=1)
    for r in rows[missing].itertuples(index=False):
        logger.warning("Sin Elo para %s vs %s, no se registra", r.home_team, r.away_team)
    rows = rows[~missing].reset_index(drop=True)
    if rows.empty:
        return pd.DataFrame(columns=model.columns)
    rows["elo_diff"] = rows["elo_home"] - rows["elo_away"]
    fc = model.predictor.predict(rows)
    starts = [season_start_year(d.date()) for d in rows["date"]]
    return pd.DataFrame({
        "season": [season_label(s) for s in starts], "season_start": starts,
        "home_team": rows["home_team"], "away_team": rows["away_team"],
        "match_date": rows["date"].dt.date.astype(str),
        "logged_at_utc": now.astimezone(UTC).isoformat(timespec="seconds"),
        "source": source, "model_version": model.predictor.version, "code_commit": code_commit,
        "elo_home": rows["elo_home"], "elo_away": rows["elo_away"], **{c: rows[c] for c in model.feature_columns},
        "lam": fc.lam, "mu": fc.mu, "p_home": fc.probs[:, 0], "p_draw": fc.probs[:, 1], "p_away": fc.probs[:, 2],
    })[model.columns]


def _not_logged(df: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    logged = set(map(tuple, existing[KEY].astype(str).to_numpy())) if len(existing) else set()
    keys = zip((str(season_start_year(d.date())) for d in df["date"]), df["home_team"], df["away_team"])
    keep = [k not in logged for k in keys]
    return df[keep].drop_duplicates(["home_team", "away_team", "date"])


def new_live_entries(fixtures: pd.DataFrame, model: ShadowModel, store: MatchStore, existing: pd.DataFrame,
                     now: datetime, code_commit: str) -> pd.DataFrame:
    """Partidos con fecha posterior a hoy (UTC) que todavía no estén en el registro."""
    today = now.astimezone(UTC).date()
    t = pd.DataFrame({"date": pd.to_datetime(fixtures["date"]), "home_team": fixtures["HomeTeam"],
                      "away_team": fixtures["AwayTeam"]})
    t = t[t["date"].dt.date > today]
    return _rows(_not_logged(t, existing), model, store, now, "vivo", code_commit)


def reconstructed_entries(matches: pd.DataFrame, model: ShadowModel, store: MatchStore, now: datetime,
                          code_commit: str) -> pd.DataFrame:
    """Partidos de Premier ya jugados de la temporada en curso (una sola vez, al crear el registro)."""
    current = season_start_year(now.astimezone(UTC).date())
    played = matches[(matches.division == PREMIER_LEAGUE) & (matches.season_start == current)
                     & matches.home_goals.notna()]
    return _rows(played[["date", "home_team", "away_team"]], model, store, now, "reconstruido", code_commit)


def load_model(name: str, matches: pd.DataFrame) -> ShadowModel:
    if name == "tiros":
        return shots_model(matches)
    if name == "elo":
        return elo_model()
    raise ValueError(f"Modelo en evaluación desconocido: {name}")


def main() -> None:
    from src.data.fixtures import fetch_fixtures
    from src.data.load import load_matches

    parser = argparse.ArgumentParser(description="Registra predicciones de un modelo en evaluación")
    parser.add_argument("--model", choices=sorted(DEFAULT_LEDGERS), default="tiros")
    parser.add_argument("--ledger", type=Path, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ledger = args.ledger or DEFAULT_LEDGERS[args.model]
    now = datetime.now(UTC)
    commit = os.getenv("GITHUB_SHA", "local")[:12]
    matches, store = load_matches(), MatchStore.load()
    model = load_model(args.model, matches)

    if not ledger.exists():
        seeded = append_entries(ledger, reconstructed_entries(matches, model, store, now, commit),
                                columns=model.columns)
        logger.info("Registro nuevo (%s): %d partidos ya jugados agregados como reconstruidos", model.name, seeded)
    existing = read_ledger(ledger, columns=model.columns)
    entries = new_live_entries(fetch_fixtures(), model, store, existing, now, commit)
    added = append_entries(ledger, entries, columns=model.columns)
    logger.info("Modelo en evaluación %s (%s) · registrados ahora: %d · total: %d", model.name,
                model.predictor.version, added, len(existing) + added)


if __name__ == "__main__":
    main()
