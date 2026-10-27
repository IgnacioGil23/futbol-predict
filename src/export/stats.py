"""Estadísticas de la temporada para la sección Estadísticas de la web.

Solo métricas que se usan en el análisis de partidos, calculadas con las columnas de Football-Data que ya tiene el
proyecto (resultado final y al entretiempo, tiros, tiros al arco, tarjetas, árbitro y cuotas de Bet365). Los datos no
tienen el minuto de cada gol: las remontadas se miden según el marcador al entretiempo.

Las probabilidades del mercado son las de Bet365 pre-cierre con el margen quitado por el método de Shin, como en el
resto del sitio.
"""

import numpy as np
import pandas as pd

from src.config import PREMIER_LEAGUE, season_label
from src.odds import shin_probabilities

ODDS_COLUMNS = ["b365_home", "b365_draw", "b365_away"]
REFERENCE_SEASONS = 10   # contexto histórico: las 10 temporadas anteriores, partidos agrupados


def r4(x) -> float:
    return round(float(x), 4)


def _ratio(num, den) -> float | None:
    """num / den redondeado; None si no hay denominador (equipo sin partidos, columna vacía)."""
    return None if not den else r4(num / den)


def _points(gf, ga) -> np.ndarray:
    return np.select([gf > ga, gf == ga], [3, 1], 0)


def team_match_rows(matches: pd.DataFrame) -> pd.DataFrame:
    """Dos filas por partido jugado (una por equipo), ordenadas por fecha, con lo que hizo y recibió cada equipo."""
    m = matches[matches["home_goals"].notna()].sort_values(["date", "match_id"]).reset_index(drop=True)
    odds = m[ODDS_COLUMNS].to_numpy(dtype=float, na_value=np.nan)
    valid = ~np.isnan(odds).any(axis=1) & (odds > 1).all(axis=1)
    market = np.full(odds.shape, np.nan)
    if valid.any():
        market[valid] = shin_probabilities(odds[valid])

    sides = []
    for is_home, us, them, p_win in ((True, "home", "away", market[:, 0]), (False, "away", "home", market[:, 2])):
        sides.append(pd.DataFrame({
            "match_id": m["match_id"], "date": m["date"],
            "team": m[f"{us}_team"], "opponent": m[f"{them}_team"], "is_home": is_home,
            "gf": m[f"{us}_goals"], "ga": m[f"{them}_goals"],
            "gf_ht": m[f"ht_{us}_goals"], "ga_ht": m[f"ht_{them}_goals"],
            "shots": m[f"{us}_shots"], "shots_against": m[f"{them}_shots"],
            "sot": m[f"{us}_shots_on_target"], "sot_against": m[f"{them}_shots_on_target"],
            "yellow": m[f"{us}_yellow"], "red": m[f"{us}_red"],
            "p_win": p_win, "p_draw": market[:, 1],
        }))
    rows = pd.concat(sides, ignore_index=True)
    rows["points"] = _points(rows["gf"], rows["ga"])
    rows["ht_state"] = np.select([rows["gf_ht"] > rows["ga_ht"], rows["gf_ht"] < rows["ga_ht"]],
                                 ["leading", "trailing"], "level")
    return rows.sort_values(["date", "match_id", "is_home"], ascending=[True, True, False]).reset_index(drop=True)


def league_summary(rows: pd.DataFrame) -> dict:
    """Números de la liga, contados por partido (la fila del local de cada partido)."""
    h = rows[rows["is_home"]]
    n = len(h)
    goals = h["gf"] + h["ga"]
    with_leader = h[h["ht_state"] != "level"]
    leader_won = ((with_leader["ht_state"] == "leading") & (with_leader["points"] == 3)) | \
                 ((with_leader["ht_state"] == "trailing") & (with_leader["points"] == 0))
    trailer_won = ((with_leader["ht_state"] == "trailing") & (with_leader["points"] == 3)) | \
                  ((with_leader["ht_state"] == "leading") & (with_leader["points"] == 0))
    return {
        "matches": int(n),
        "home_win_pct": _ratio((h["points"] == 3).sum(), n),
        "draw_pct": _ratio((h["points"] == 1).sum(), n),
        "away_win_pct": _ratio((h["points"] == 0).sum(), n),
        "goals_per_match": _ratio(goals.sum(), n),
        "first_half_goals_share": _ratio((h["gf_ht"] + h["ga_ht"]).sum(), goals.sum()),
        "btts_pct": _ratio(((h["gf"] > 0) & (h["ga"] > 0)).sum(), n),
        "over25_pct": _ratio((goals >= 3).sum(), n),
        "ht_leader_win_pct": _ratio(leader_won.sum(), len(with_leader)),
        "ht_trailer_comeback_pct": _ratio(trailer_won.sum(), len(with_leader)),
    }


def _record(g: pd.DataFrame) -> dict:
    return {"played": int(len(g)), "won": int((g["points"] == 3).sum()), "drawn": int((g["points"] == 1).sum()),
            "lost": int((g["points"] == 0).sum()), "points_per_game": _ratio(g["points"].sum(), len(g)),
            "gf": int(g["gf"].sum()), "ga": int(g["ga"].sum())}


def _streak(flags: pd.Series) -> int:
    """Partidos seguidos, contando desde el último hacia atrás, en que se cumple la condición."""
    n = 0
    for ok in reversed(flags.to_numpy()):
        if not ok:
            break
        n += 1
    return n


def _team(team: str, g: pd.DataFrame) -> dict:
    n = len(g)
    ht = {}
    for state in ("leading", "level", "trailing"):
        s = g[g["ht_state"] == state]
        ht[state] = {"n": int(len(s)), "won": int((s["points"] == 3).sum()), "drawn": int((s["points"] == 1).sum()),
                     "lost": int((s["points"] == 0).sum())}
    gf_2h, ga_2h = g["gf"] - g["gf_ht"], g["ga"] - g["ga_ht"]
    shots, shots_a, sot, sot_a = (g[c].sum() for c in ("shots", "shots_against", "sot", "sot_against"))
    conversion, save_pct = _ratio(g["gf"].sum(), sot), (None if not sot_a else r4(1 - g["ga"].sum() / sot_a))
    priced = g[g["p_win"].notna()]
    expected = (3 * priced["p_win"] + priced["p_draw"]).sum()
    return {
        "team": team, "played": int(n),
        "home": _record(g[g["is_home"]]), "away": _record(g[~g["is_home"]]),
        "halves": {"gf_1h": int(g["gf_ht"].sum()), "ga_1h": int(g["ga_ht"].sum()),
                   "gf_2h": int(gf_2h.sum()), "ga_2h": int(ga_2h.sum()),
                   "points_1h": int(_points(g["gf_ht"], g["ga_ht"]).sum()),
                   "points_2h": int(_points(gf_2h, ga_2h).sum())},
        "ht": {**ht,
               "points_dropped_leading": int((3 - g.loc[g["ht_state"] == "leading", "points"]).sum()),
               "points_won_trailing": int(g.loc[g["ht_state"] == "trailing", "points"].sum())},
        "goals": {"gf_per_game": _ratio(g["gf"].sum(), n), "ga_per_game": _ratio(g["ga"].sum(), n),
                  "clean_sheet_pct": _ratio((g["ga"] == 0).sum(), n),
                  "failed_to_score_pct": _ratio((g["gf"] == 0).sum(), n),
                  "btts_pct": _ratio(((g["gf"] > 0) & (g["ga"] > 0)).sum(), n),
                  "over25_pct": _ratio((g["gf"] + g["ga"] >= 3).sum(), n)},
        "shots": {"shots_per_game": _ratio(shots, n), "shots_against_per_game": _ratio(shots_a, n),
                  "sot_per_game": _ratio(sot, n), "sot_against_per_game": _ratio(sot_a, n),
                  "shot_share": _ratio(shots, shots + shots_a), "sot_share": _ratio(sot, sot + sot_a),
                  "accuracy": _ratio(sot, shots), "conversion": conversion, "save_pct": save_pct,
                  "pdo": None if conversion is None or save_pct is None else round(1000 * (conversion + save_pct), 1)},
        "discipline": {"yellow_per_game": _ratio(g["yellow"].sum(), n), "red_total": int(g["red"].sum())},
        "market": {"market_matches": int(len(priced)), "points": int(priced["points"].sum()),
                   "expected_points": r4(expected) if len(priced) else None,
                   "difference": r4(priced["points"].sum() - expected) if len(priced) else None},
        "streaks": {"unbeaten": _streak(g["points"] > 0), "winless": _streak(g["points"] < 3),
                    "scoring": _streak(g["gf"] > 0)},
    }


def team_stats(rows: pd.DataFrame) -> list[dict]:
    """Un resumen por equipo (filas en orden cronológico, como las deja team_match_rows)."""
    return [_team(team, g) for team, g in rows.groupby("team", sort=True)]


def referee_stats(matches: pd.DataFrame, min_matches: int = 3) -> list[dict]:
    """Tarjetas por partido de cada árbitro (sumando los dos equipos), de más a menos amarillas por partido."""
    m = matches[matches["home_goals"].notna()].assign(referee=matches["referee"].fillna("").astype(str).str.strip())
    m = m[m["referee"] != ""]
    out = []
    for referee, g in m.groupby("referee"):
        if len(g) >= min_matches:
            out.append({"referee": referee, "matches": int(len(g)),
                        "yellow_per_game": r4((g["home_yellow"] + g["away_yellow"]).sum() / len(g)),
                        "red_total": int((g["home_red"] + g["away_red"]).sum())})
    return sorted(out, key=lambda r: (-r["yellow_per_game"], r["referee"]))


def remaining_difficulty(fixtures: list[tuple[str, str]], ratings: dict[str, float]) -> dict[str, dict]:
    """Rating medio de los rivales que le quedan a cada equipo; rank 1 = el calendario más difícil."""
    rivals: dict[str, list[float]] = {}
    for home, away in fixtures:
        rivals.setdefault(home, []).append(ratings[away])
        rivals.setdefault(away, []).append(ratings[home])
    avg = {team: float(np.mean(r)) for team, r in rivals.items()}
    order = sorted(avg, key=lambda t: -avg[t])
    return {team: {"remaining": len(rivals[team]), "avg_opponent_rating": round(avg[team], 1),
                   "rank": order.index(team) + 1} for team in avg}


def build_stats(matches: pd.DataFrame, season_start: int, difficulty: dict | None,
                referees_next: dict | None, division: str = PREMIER_LEAGUE) -> dict:
    """Todo lo que muestra la página para una temporada de la primera división `division`."""
    pl = matches[(matches["division"] == division) & matches["home_goals"].notna()]
    season = pl[pl["season_start"] == season_start]
    reference = pl[pl["season_start"].between(season_start - REFERENCE_SEASONS, season_start - 1)]
    rows = team_match_rows(season)
    return {
        "season": season_label(season_start), "matches_played": int(len(season)),
        "league": league_summary(rows), "league_reference": league_summary(team_match_rows(reference)),
        "reference_seasons": f"{season_label(season_start - REFERENCE_SEASONS)} a {season_label(season_start - 1)}",
        "teams": team_stats(rows), "referees": referee_stats(season),
        "difficulty": difficulty, "referees_next": referees_next,
    }
