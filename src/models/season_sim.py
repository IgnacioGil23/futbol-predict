"""Simulación de Monte Carlo del resto de una temporada (docs/preregistro_temporada.md, commit 02aff79).

Las N temporadas simuladas avanzan juntas, partido por partido en orden cronológico: para cada partido se calculan los
goles esperados con el modelo de producción a partir del Elo de ESA simulación, se sortea el marcador y se actualizan la
tabla y el Elo de esa simulación con la misma regla que el Elo real. Así, un equipo que gana varios partidos seguidos en
una simulación se vuelve más fuerte en esa simulación, y la incertidumbre crece con la distancia, como en la realidad.

El orden final usa puntos, diferencia de gol y goles a favor; los empates restantes se resuelven al azar.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.features.elo import EloParams
from src.models.scoreline import MAX_GOALS

N_SIMS = 10_000
SEED = 0
TOP4, TOP6, RELEGATED = 4, 6, 3


@dataclass
class SeasonState:
    """Estado en la fecha de corte: equipos, tabla, Elo y partidos que faltan (en orden)."""
    teams: list[str]
    points: np.ndarray
    goal_diff: np.ndarray
    goals_for: np.ndarray
    played: np.ndarray
    elo: np.ndarray
    fixtures: list[tuple[str, str]]


def _poisson_capped(rng: np.random.Generator, rate: np.ndarray) -> np.ndarray:
    """Goles ~ Poisson(rate) recortado como la grilla del modelo (0..MAX_GOALS): se vuelve a sortear lo que excede."""
    goals = rng.poisson(rate)
    over = goals > MAX_GOALS
    while over.any():
        goals[over] = rng.poisson(rate[over])
        over = goals > MAX_GOALS
    return goals


def simulate(state: SeasonState, rates, elo_params: EloParams, n_sims: int = N_SIMS, seed: int = SEED,
             update_elo: bool = True) -> dict:
    """`rates(elo_diff) -> (lam, mu)` vectorizado. Devuelve posiciones finales (n_sims × equipos) y puntos."""
    rng = np.random.default_rng(seed)
    idx = {t: i for i, t in enumerate(state.teams)}
    n = len(state.teams)
    points = np.tile(state.points.astype(float), (n_sims, 1))
    gd = np.tile(state.goal_diff.astype(float), (n_sims, 1))
    gf = np.tile(state.goals_for.astype(float), (n_sims, 1))
    elo = np.tile(state.elo.astype(float), (n_sims, 1))
    rows = np.arange(n_sims)
    for home, away in state.fixtures:
        h, a = idx[home], idx[away]
        lam, mu = rates(elo[:, h] - elo[:, a])
        hg, ag = _poisson_capped(rng, lam), _poisson_capped(rng, mu)
        points[:, h] += np.where(hg > ag, 3, np.where(hg == ag, 1, 0))
        points[:, a] += np.where(ag > hg, 3, np.where(hg == ag, 1, 0))
        gd[:, h] += hg - ag
        gd[:, a] += ag - hg
        gf[:, h] += hg
        gf[:, a] += ag
        if update_elo:
            expected = 1.0 / (1.0 + 10.0 ** ((elo[:, a] - elo[:, h] - elo_params.home_advantage) / 400.0))
            result = np.where(hg > ag, 1.0, np.where(hg == ag, 0.5, 0.0))
            k = elo_params.k0 * (1.0 + np.abs(hg - ag)) ** elo_params.lam
            delta = k * (result - expected)
            elo[rows, h] += delta
            elo[rows, a] -= delta
    # clave de orden: puntos, luego diferencia de gol, luego goles a favor, luego azar
    key = points * 1e6 + (gd + 500) * 1e3 + gf + rng.random((n_sims, n)) * 0.5
    order = np.argsort(-key, axis=1)
    positions = np.empty_like(order)
    positions[rows[:, None], order] = np.arange(1, n + 1)
    return {"positions": positions, "points": points, "elo": elo}


def summarize(state: SeasonState, sim: dict) -> pd.DataFrame:
    pos, n = sim["positions"], len(state.teams)
    dist = np.stack([(pos == p).mean(axis=0) for p in range(1, n + 1)], axis=1)   # equipos × posiciones
    out = pd.DataFrame({
        "team": state.teams, "elo": state.elo, "points_now": state.points, "played": state.played,
        "expected_points": sim["points"].mean(axis=0),
        "p_champion": dist[:, 0], "p_top4": dist[:, :TOP4].sum(axis=1), "p_top6": dist[:, :TOP6].sum(axis=1),
        "p_relegation": dist[:, n - RELEGATED:].sum(axis=1),
    })
    out["positions"] = list(dist)
    return out.sort_values(["expected_points", "p_champion"], ascending=False).reset_index(drop=True)


def final_table(matches: pd.DataFrame) -> pd.DataFrame:
    """Tabla final real con los mismos criterios (puntos, diferencia de gol, goles; luego nombre)."""
    rows = {}
    for r in matches.itertuples(index=False):
        for team, f, a in ((r.home_team, r.home_goals, r.away_goals), (r.away_team, r.away_goals, r.home_goals)):
            row = rows.setdefault(team, {"team": team, "points": 0, "gd": 0, "gf": 0})
            row["points"] += 3 if f > a else (1 if f == a else 0)
            row["gd"] += int(f - a)
            row["gf"] += int(f)
    t = pd.DataFrame(rows.values()).sort_values(["points", "gd", "gf", "team"], ascending=[False, False, False, True])
    t["position"] = np.arange(1, len(t) + 1)
    return t.reset_index(drop=True)


def state_from_matches(season: pd.DataFrame, cutoff: pd.Timestamp) -> SeasonState:
    """Estado de una temporada pasada en la fecha de corte, desde la tabla de variables (elo_home/elo_away son el
    Elo previo a cada partido). El Elo de cada equipo a la fecha de corte es el previo a su primer partido desde ella."""
    season = season.sort_values(["date", "match_id"])
    teams = sorted(set(season.home_team) | set(season.away_team))
    known = season[season.date < cutoff]
    table = final_table(known) if len(known) else pd.DataFrame({"team": teams, "points": 0, "gd": 0, "gf": 0})
    table = table.set_index("team").reindex(teams).fillna(0)
    played = pd.Series(0, index=teams)
    for side in ("home_team", "away_team"):
        played = played.add(known[side].value_counts(), fill_value=0)
    rest = season[season.date >= cutoff]
    elo = {}
    for r in rest.itertuples(index=False):
        elo.setdefault(r.home_team, r.elo_home)
        elo.setdefault(r.away_team, r.elo_away)
    return SeasonState(teams=teams, points=table["points"].to_numpy(), goal_diff=table["gd"].to_numpy(),
                       goals_for=table["gf"].to_numpy(), played=played.reindex(teams).to_numpy(),
                       elo=np.array([elo[t] for t in teams]),
                       fixtures=list(zip(rest["home_team"], rest["away_team"])))
