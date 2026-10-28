"""Simulación de la temporada en curso para la web (sección "Temporada").

Estado a hoy: tabla real (Football-Data), Elo actual de cada equipo y partidos que faltan según el calendario de
openfootball (todo cruce local-visitante que todavía no tiene resultado, en orden cronológico; incluye partidos
postergados). Se simulan con src.models.season_sim, tal como fija docs/preregistro_temporada.md, y se adjunta el
resumen de la evaluación histórica (reports/season/). Cada liga con su calendario, su modelo y sus puestos de
descenso (src/data/leagues.py; docs/preregistro_ligas.md).
"""

import json
import logging

import numpy as np
import pandas as pd
import requests

from src.config import PREMIER_LEAGUE, PROJECT_ROOT, season_label, season_start_year
from src.data.teams import slug
from src.models.season_sim import N_SIMS, SeasonState, simulate, summarize
from src.serving.store import MatchStore

logger = logging.getLogger(__name__)

EVAL_DIR = PROJECT_ROOT / "reports" / "season"


def current_state(store: MatchStore, schedule: pd.DataFrame, today: pd.Timestamp,
                  division: str = PREMIER_LEAGUE) -> SeasonState:
    season = season_start_year(today.date())
    teams = sorted(set(schedule.home_team) | set(schedule.away_team))
    table = store.standings(division, season, today + pd.Timedelta(days=1)).set_index("team")
    table = table.reindex(teams).fillna(0)
    results = store.matches[(store.matches.division == division) & (store.matches.season_start == season)
                            & store.matches.home_goals.notna()]
    played = set(zip(results.home_team, results.away_team))
    rest = schedule[[(h, a) not in played for h, a in zip(schedule.home_team, schedule.away_team)]]
    rest = rest.assign(_t=rest["time_uk"].fillna("")).sort_values(["date", "_t", "home_team"])
    day = today + pd.Timedelta(days=1)                        # incluye los partidos de hoy ya cargados
    elo = np.array([store.elo_as_of(t, day) for t in teams], dtype=float)
    return SeasonState(teams=teams, points=table["points"].to_numpy(), goal_diff=table["gd"].to_numpy(),
                       goals_for=table["gf"].to_numpy(), played=table["played"].to_numpy(), elo=elo,
                       fixtures=list(zip(rest["home_team"], rest["away_team"])))


def evaluation_summary(reports: list) -> dict | None:
    """Resumen de la última evaluación histórica de la simulación (`reports`: los JSON de esa liga, ordenados)."""
    if not reports:
        return None
    r = json.loads(reports[-1].read_text(encoding="utf-8"))
    table = [{"event": key.split("@")[0], "cutoff": int(key.split("@")[1]),
              **{v: {"brier": e["brier"], "skill": e["skill_vs_base"], "skill_ci": e["skill_ci"]}
                 for v, e in entry.items()}} for key, entry in r["summary"].items()]
    return {"seasons": r["seasons"], "n_sims": r["n_sims"], "table": table, "calibration": r["calibration"],
            "champion_probability": r["champion_probability"], "report": reports[-1].name,
            "cutoffs_label": r.get("cutoffs_label")}


def unknown_teams(store: MatchStore, schedule: pd.DataFrame) -> set[str]:
    """Equipos del calendario sin ningún partido en los datos (nombre sin traducir o club nuevo). Antes de la fecha 1
    todos los demás tienen historia (la temporada anterior, en primera o en segunda)."""
    return (set(schedule.home_team) | set(schedule.away_team)) - set(store.by_team)


def build_season(ctx, today: pd.Timestamp) -> dict | None:
    """Simulación de la temporada en curso de la liga de `ctx` (src.export.league_context.LeagueContext)."""
    season = season_start_year(today.date())
    try:
        schedule = ctx.schedule(season)
    except requests.RequestException as err:
        logger.warning("%s: sin calendario, no se simula la temporada: %s", ctx.code, err)
        return None
    unknown = unknown_teams(ctx.store, schedule)
    if unknown:
        logger.warning("%s: equipos del calendario sin datos %s; no se simula la temporada", ctx.code, sorted(unknown))
        return None
    state = current_state(ctx.store, schedule, today, division=ctx.top)
    relegated = ctx.league["relegation"]
    summary = summarize(state, simulate(state, ctx.sim_predictor.rates, ctx.sim_elo_params), relegated=relegated)
    teams = [{"team": r.team, "name": ctx.name_of(r.team), "slug": slug(r.team), "elo": round(float(r.elo), 1),
              "points": int(r.points_now), "played": int(r.played), "expected_points": round(float(r.expected_points), 1),
              "p_champion": round(float(r.p_champion), 4), "p_top4": round(float(r.p_top4), 4),
              "p_top6": round(float(r.p_top6), 4), "p_relegation": round(float(r.p_relegation), 4),
              "positions": [round(float(x), 4) for x in r.positions]} for r in summary.itertuples()]
    return {"as_of": today.date().isoformat(), "season": season_label(season), "n_sims": N_SIMS,
            "remaining_matches": len(state.fixtures), "model_version": ctx.sim_predictor.version, "teams": teams,
            "zones": {"relegation": relegated, "playoff": ctx.league["playoff"],
                      "head_to_head": ctx.league["head_to_head"]},
            "evaluation": evaluation_summary(ctx.season_reports())}
