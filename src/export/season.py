"""Simulación de la temporada en curso para la web (sección "Temporada").

Estado a hoy: tabla real (Football-Data), Elo actual de cada equipo y partidos que faltan según el calendario de
openfootball (todo cruce local-visitante que todavía no tiene resultado, en orden cronológico; incluye partidos
postergados). Se simulan con src.models.season_sim, tal como fija docs/preregistro_temporada.md, y se adjunta el
resumen de la evaluación histórica (reports/season/).
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from src.config import PREMIER_LEAGUE, PROJECT_ROOT, season_label, season_start_year
from src.data.schedule import fetch_schedule
from src.data.teams import display_name, slug
from src.features.build import load_elo_params
from src.models.season_sim import N_SIMS, SeasonState, simulate, summarize
from src.serving.predictor import EloPoissonPredictor
from src.serving.store import MatchStore

logger = logging.getLogger(__name__)

EVAL_DIR = PROJECT_ROOT / "reports" / "season"


def current_state(store: MatchStore, schedule: pd.DataFrame, today: pd.Timestamp) -> SeasonState:
    season = season_start_year(today.date())
    teams = sorted(set(schedule.home_team) | set(schedule.away_team))
    table = store.standings(PREMIER_LEAGUE, season, today + pd.Timedelta(days=1)).set_index("team")
    table = table.reindex(teams).fillna(0)
    results = store.matches[(store.matches.division == PREMIER_LEAGUE) & (store.matches.season_start == season)
                            & store.matches.home_goals.notna()]
    played = set(zip(results.home_team, results.away_team))
    rest = schedule[[(h, a) not in played for h, a in zip(schedule.home_team, schedule.away_team)]]
    rest = rest.assign(_t=rest["time_uk"].fillna("")).sort_values(["date", "_t", "home_team"])
    day = today + pd.Timedelta(days=1)                        # incluye los partidos de hoy ya cargados
    elo = np.array([store.elo_as_of(t, day) for t in teams], dtype=float)
    return SeasonState(teams=teams, points=table["points"].to_numpy(), goal_diff=table["gd"].to_numpy(),
                       goals_for=table["gf"].to_numpy(), played=table["played"].to_numpy(), elo=elo,
                       fixtures=list(zip(rest["home_team"], rest["away_team"])))


def evaluation_summary() -> dict | None:
    reports = sorted(EVAL_DIR.glob("evaluacion_*.json"))
    if not reports:
        return None
    r = json.loads(reports[-1].read_text(encoding="utf-8"))
    table = [{"event": key.split("@")[0], "cutoff": int(key.split("@")[1]),
              **{v: {"brier": e["brier"], "skill": e["skill_vs_base"], "skill_ci": e["skill_ci"]}
                 for v, e in entry.items()}} for key, entry in r["summary"].items()]
    return {"seasons": r["seasons"], "n_sims": r["n_sims"], "table": table, "calibration": r["calibration"],
            "champion_probability": r["champion_probability"], "report": reports[-1].name}


def build_season(store: MatchStore, predictor: EloPoissonPredictor, today: pd.Timestamp) -> dict | None:
    season = season_start_year(today.date())
    try:
        schedule = fetch_schedule(season)
    except requests.RequestException as err:
        logger.warning("Sin calendario, no se simula la temporada: %s", err)
        return None
    state = current_state(store, schedule, today)
    summary = summarize(state, simulate(state, predictor.rates, load_elo_params()))
    teams = [{"team": r.team, "name": display_name(r.team), "slug": slug(r.team), "elo": round(float(r.elo), 1),
              "points": int(r.points_now), "played": int(r.played), "expected_points": round(float(r.expected_points), 1),
              "p_champion": round(float(r.p_champion), 4), "p_top4": round(float(r.p_top4), 4),
              "p_top6": round(float(r.p_top6), 4), "p_relegation": round(float(r.p_relegation), 4),
              "positions": [round(float(x), 4) for x in r.positions]} for r in summary.itertuples()]
    return {"as_of": today.date().isoformat(), "season": season_label(season), "n_sims": N_SIMS,
            "remaining_matches": len(state.fixtures), "model_version": predictor.version, "teams": teams,
            "evaluation": evaluation_summary()}
