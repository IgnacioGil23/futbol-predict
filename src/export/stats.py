"""Estadísticas de la temporada para la sección Estadísticas de la web.

Solo métricas que se usan en el análisis de partidos, calculadas con las columnas de Football-Data que ya tiene el
proyecto (resultado final y al entretiempo, tiros, tiros al arco, tarjetas, árbitro y cuotas de Bet365). Los datos no
tienen el minuto de cada gol: las remontadas se miden según el marcador al entretiempo.

Las probabilidades del mercado son las de Bet365 pre-cierre con el margen quitado por el método de Shin, como en el
resto del sitio.
"""

import numpy as np
import pandas as pd

from src.odds import shin_probabilities

ODDS_COLUMNS = ["b365_home", "b365_draw", "b365_away"]


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
