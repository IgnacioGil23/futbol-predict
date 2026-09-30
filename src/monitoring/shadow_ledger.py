"""Registro en paralelo del modelo en evaluación (docs/preregistro_tiros.md).

Mismas reglas que src/monitoring/ledger.py (clave, solo partidos con fecha posterior al día de la
corrida, la primera predicción es la definitiva, solo se agregan filas), en un archivo aparte para
no tocar el formato del registro del modelo de producción. No se publica ni se evalúa durante la
temporada: la comparación se hace una sola vez, en julio (src/models/confirm_shots.py --final).

La primera corrida, con el archivo todavía inexistente, agrega una única vez los partidos ya jugados
de la temporada en curso con source = "reconstruido".

Uso (lo corre el workflow diario):
    python -m src.monitoring.shadow_ledger --ledger monitoring/ledger/shadow_predictions.csv
"""

import argparse
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PREMIER_LEAGUE, season_label, season_start_year
from src.data.fixtures import fetch_fixtures
from src.monitoring.ledger import KEY, append_entries, read_ledger
from src.serving.shadow import SHOT_COLUMNS, ShadowPredictor, shot_features_for
from src.serving.store import MatchStore

logger = logging.getLogger(__name__)

DEFAULT_SHADOW_LEDGER = Path("monitoring/ledger/shadow_predictions.csv")
SHADOW_COLUMNS = [
    "season", "season_start", "home_team", "away_team", "match_date",
    "logged_at_utc", "source", "model_version", "code_commit",
    "elo_home", "elo_away", *SHOT_COLUMNS,
    "lam", "mu", "p_home", "p_draw", "p_away",
]


def _rows(targets: pd.DataFrame, matches: pd.DataFrame, store: MatchStore, predictor: ShadowPredictor,
          now: datetime, source: str, code_commit: str) -> pd.DataFrame:
    """Predicción del candidato para `targets` (date, home_team, away_team); descarta los que no tengan Elo."""
    if targets.empty:
        return pd.DataFrame(columns=SHADOW_COLUMNS)
    rows = shot_features_for(matches, targets)
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
        return pd.DataFrame(columns=SHADOW_COLUMNS)
    rows["elo_diff"] = rows["elo_home"] - rows["elo_away"]
    fc = predictor.predict(rows)
    starts = [season_start_year(d.date()) for d in rows["date"]]
    return pd.DataFrame({
        "season": [season_label(s) for s in starts], "season_start": starts,
        "home_team": rows["home_team"], "away_team": rows["away_team"],
        "match_date": rows["date"].dt.date.astype(str),
        "logged_at_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "source": source, "model_version": predictor.version, "code_commit": code_commit,
        "elo_home": rows["elo_home"], "elo_away": rows["elo_away"], **{c: rows[c] for c in SHOT_COLUMNS},
        "lam": fc.lam, "mu": fc.mu, "p_home": fc.probs[:, 0], "p_draw": fc.probs[:, 1], "p_away": fc.probs[:, 2],
    })[SHADOW_COLUMNS]


def _not_logged(df: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    logged = set(map(tuple, existing[KEY].astype(str).to_numpy())) if len(existing) else set()
    keys = zip((str(season_start_year(d.date())) for d in df["date"]), df["home_team"], df["away_team"])
    keep = [k not in logged for k in keys]
    return df[keep].drop_duplicates(["home_team", "away_team", "date"])


def new_live_entries(fixtures: pd.DataFrame, matches: pd.DataFrame, store: MatchStore, predictor: ShadowPredictor,
                     existing: pd.DataFrame, now: datetime, code_commit: str) -> pd.DataFrame:
    """Partidos con fecha posterior a hoy (UTC) que todavía no estén en el registro."""
    today = now.astimezone(timezone.utc).date()
    t = pd.DataFrame({"date": pd.to_datetime(fixtures["date"]), "home_team": fixtures["HomeTeam"],
                      "away_team": fixtures["AwayTeam"]})
    t = t[t["date"].dt.date > today]
    return _rows(_not_logged(t, existing), matches, store, predictor, now, "vivo", code_commit)


def reconstructed_entries(matches: pd.DataFrame, store: MatchStore, predictor: ShadowPredictor, now: datetime,
                          code_commit: str) -> pd.DataFrame:
    """Partidos de Premier ya jugados de la temporada en curso (una sola vez, al crear el registro)."""
    current = season_start_year(now.astimezone(timezone.utc).date())
    played = matches[(matches.division == PREMIER_LEAGUE) & (matches.season_start == current)
                     & matches.home_goals.notna()]
    return _rows(played[["date", "home_team", "away_team"]], matches, store, predictor, now, "reconstruido",
                 code_commit)


def main() -> None:
    from src.data.load import load_matches

    parser = argparse.ArgumentParser(description="Registra predicciones del modelo en evaluación")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_SHADOW_LEDGER)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    now = datetime.now(timezone.utc)
    commit = os.getenv("GITHUB_SHA", "local")[:12]
    matches, store, predictor = load_matches(), MatchStore.load(), ShadowPredictor.load()

    if not args.ledger.exists():
        seeded = append_entries(args.ledger, reconstructed_entries(matches, store, predictor, now, commit),
                                columns=SHADOW_COLUMNS)
        logger.info("Registro nuevo: %d partidos ya jugados agregados como reconstruidos", seeded)
    existing = read_ledger(args.ledger, columns=SHADOW_COLUMNS)
    entries = new_live_entries(fetch_fixtures(), matches, store, predictor, existing, now, commit)
    added = append_entries(args.ledger, entries, columns=SHADOW_COLUMNS)
    logger.info("Modelo en evaluación %s · registrados ahora: %d · total: %d", predictor.version, added,
                len(existing) + added)


if __name__ == "__main__":
    main()
