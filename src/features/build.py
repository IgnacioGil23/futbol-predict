"""Construye la tabla de features (una fila por partido de Premier League).

Uso:
    python -m src.features.build

Entrada: data/processed/matches.parquet (E0 + E1). Los partidos sin resultado
(temporada en curso) también reciben features: es exactamente lo que se usa para
predecir partidos futuros.

Salida: data/processed/features.parquet y data/processed/elo_history.parquet.
"""

import json
import logging
from pathlib import Path

import pandas as pd

from src import eras
from src.config import FEATURES_PATH_NAME, PREMIER_LEAGUE, PROCESSED_DIR, PROJECT_ROOT
from src.data.load import load_matches
from src.features.elo import EloParams, compute_elo
from src.features.h2h import h2h_features
from src.features.team_state import SHOT_STATS, SHOTS_HALFLIVES, form_rest_features, shot_features, table_features

logger = logging.getLogger(__name__)

ELO_PARAMS_PATH = PROJECT_ROOT / "configs" / "elo_params.json"
FEATURES_PATH = PROCESSED_DIR / FEATURES_PATH_NAME
ELO_HISTORY_PATH = PROCESSED_DIR / "elo_history.parquet"

FORM_WINDOW = 5
GOALS_HALFLIFE = 8.0
H2H_SHRINKAGE = 5.0

# Columnas que se conocen DESPUÉS del partido: target y estadísticas del propio
# partido. Nunca pueden ser feature de ese partido (test en tests/test_features.py).
POST_MATCH_COLUMNS = [
    "home_goals", "away_goals", "result", "ht_home_goals", "ht_away_goals", "ht_result",
    "home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target",
    "home_fouls", "away_fouls", "home_corners", "away_corners",
    "home_yellow", "away_yellow", "home_red", "away_red",
]
TEAM_FEATURES = [
    f"ppg_last{FORM_WINDOW}", "gf_ewm", "ga_ewm", "rest_days", "matches_last21", "season_opener",
    "games_played", "ppg", "gdpg", "position",
    *[f"{stat}_hl{hl}" for hl in SHOTS_HALFLIVES for stat in SHOT_STATS],
]


def load_elo_params(path: Path = ELO_PARAMS_PATH) -> EloParams:
    if path.exists():
        return EloParams(**json.loads(path.read_text(encoding="utf-8"))["params"])
    logger.warning("No existe %s: se usan los parámetros por defecto del Elo", path)
    return EloParams()


def build_features(matches: pd.DataFrame, elo_params: EloParams | None = None,
                   division: str = PREMIER_LEAGUE) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Features de todos los partidos de `division`, usando la historia de todas las divisiones."""
    elo_params = elo_params or load_elo_params()
    elo, history = compute_elo(matches, elo_params, top_division=division)
    form = form_rest_features(matches, FORM_WINDOW, GOALS_HALFLIFE)
    table = table_features(matches)
    shots = shot_features(matches)
    team = form.merge(table, on=["match_id", "team"], how="outer").merge(shots, on=["match_id", "team"], how="outer")
    h2h = h2h_features(matches, elo, H2H_SHRINKAGE)

    keep = ["match_id", "division", "season", "season_start", "date", "time", "home_team", "away_team",
            *POST_MATCH_COLUMNS,
            "b365_home", "b365_draw", "b365_away", "psc_home", "psc_draw", "psc_away",
            "clubelo_home", "clubelo_away", "clubelo_provisional"]
    out = matches.loc[matches["division"] == division, keep].copy()
    out = out.merge(elo, on="match_id", how="left")
    out["elo_diff"] = out["elo_home"] - out["elo_away"]
    out["clubelo_diff"] = out["clubelo_home"] - out["clubelo_away"]
    for side in ("home", "away"):
        side_feats = team.rename(columns={c: f"{c}_{side}" for c in TEAM_FEATURES})
        out = out.merge(side_feats[["match_id", "team"] + [f"{c}_{side}" for c in TEAM_FEATURES]],
                        left_on=["match_id", f"{side}_team"], right_on=["match_id", "team"], how="left"
                        ).drop(columns="team")
    out = out.merge(h2h, on="match_id", how="left")
    # Las eras son las fechas de Inglaterra: en otras ligas (replicación) hay partidos fuera de ellas (p. ej. la
    # Bundesliga volvió en mayo de 2020) y cuentan como "no sin público". En la Premier no hay ninguno.
    out["no_crowds"] = (eras.assign_era(out["date"]) == eras.NO_CROWDS).fillna(False).astype(int)
    out["played"] = out["home_goals"].notna()
    return out.sort_values(["date", "match_id"]).reset_index(drop=True), history


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    matches = load_matches()
    features, history = build_features(matches)
    features.to_parquet(FEATURES_PATH, index=False)
    history.to_parquet(ELO_HISTORY_PATH, index=False)
    logger.info("Guardado %s: %d partidos (%d sin jugar)", FEATURES_PATH, len(features), (~features.played).sum())


if __name__ == "__main__":
    main()
