"""Features de estado de cada equipo al comienzo del día del partido.

Patrón común (anti-fuga por construcción):
1. Con los partidos YA JUGADOS se calcula el estado de cada equipo DESPUÉS de
   cada partido (acumulados, medias móviles...).
2. Para cada partido a describir (jugado o futuro) del día D se toma el último
   estado con fecha estrictamente anterior a D (`merge_asof` sin coincidencias
   exactas). Nada del día D ni posterior puede entrar.

Todas las cuentas incluyen Premier League y Championship (así un recién
ascendido llega con historia), pero la tabla de posiciones es por división.
Limitación: solo partidos de liga (sin copas ni competiciones europeas).
"""

import numpy as np
import pandas as pd

POINTS = {"H": (3, 0), "D": (1, 1), "A": (0, 3)}


def team_long(matches: pd.DataFrame) -> pd.DataFrame:
    """Una fila por equipo y partido (dos por partido), con goles y puntos desde su perspectiva."""
    base = ["match_id", "date", "season_start", "division"]
    home = matches[base + ["home_team", "away_team", "home_goals", "away_goals"]].rename(columns={
        "home_team": "team", "away_team": "opponent", "home_goals": "gf", "away_goals": "ga"})
    home["is_home"] = True
    away = matches[base + ["away_team", "home_team", "away_goals", "home_goals"]].rename(columns={
        "away_team": "team", "home_team": "opponent", "away_goals": "gf", "home_goals": "ga"})
    away["is_home"] = False
    long = pd.concat([home, away], ignore_index=True)
    # Tiros y tiros al arco desde la perspectiva del equipo (NaN si el dataset no los trae).
    for name, own, opp in (("sh", "shots", "shots"), ("sot", "shots_on_target", "shots_on_target")):
        own_col, opp_col = f"home_{own}", f"away_{opp}"
        if own_col in matches and opp_col in matches:
            h_for, a_for = matches[f"home_{own}"].astype(float), matches[f"away_{own}"].astype(float)
            long[f"{name}_f"] = pd.concat([h_for, a_for], ignore_index=True)
            long[f"{name}_a"] = pd.concat([a_for, h_for], ignore_index=True)
        else:
            long[f"{name}_f"] = np.nan
            long[f"{name}_a"] = np.nan
    long["gf"] = long["gf"].astype(float)
    long["ga"] = long["ga"].astype(float)
    long["played"] = long["gf"].notna() & long["ga"].notna()
    long["points"] = np.select([long.gf > long.ga, long.gf == long.ga], [3.0, 1.0], 0.0)
    long.loc[~long["played"], "points"] = np.nan
    return long.sort_values(["team", "date"]).reset_index(drop=True)


def _asof_before(targets: pd.DataFrame, states: pd.DataFrame, by: list[str], cols: list[str]) -> pd.DataFrame:
    """Para cada fila de `targets` (con columna date), el último estado con date < target.date."""
    left = targets.reset_index().rename(columns={"index": "_row"}).sort_values("date")
    right = states[by + ["date"] + cols].rename(columns={"date": "state_date"}).sort_values("state_date")
    merged = pd.merge_asof(left, right, left_on="date", right_on="state_date", by=by,
                           direction="backward", allow_exact_matches=False)
    return merged.set_index("_row").sort_index()


def form_rest_features(matches: pd.DataFrame, form_window: int = 5, goals_halflife: float = 8.0) -> pd.DataFrame:
    """Forma reciente, goles ponderados, descanso y congestión, por equipo y partido.

    Devuelve una fila por (match_id, team) con:
      ppg_last{n}     puntos por partido en los últimos n partidos de liga jugados
      gf_ewm, ga_ewm  goles a favor / en contra, media exponencial (vida media en partidos)
      rest_days       días desde el último partido de liga (NaN si no hay previo)
      matches_last21  partidos de liga jugados en los 21 días previos (sin contar el día D)
      season_opener   primer partido de liga del equipo en la temporada
    """
    long = team_long(matches)
    played = long[long["played"]].copy()
    g = played.groupby("team", sort=False)
    played[f"ppg_last{form_window}"] = g["points"].transform(lambda s: s.rolling(form_window, min_periods=1).mean())
    played["gf_ewm"] = g["gf"].transform(lambda s: s.ewm(halflife=goals_halflife).mean())
    played["ga_ewm"] = g["ga"].transform(lambda s: s.ewm(halflife=goals_halflife).mean())
    played["n_played"] = g.cumcount() + 1
    played["last_date"] = played["date"]
    played["last_season"] = played["season_start"]

    cols = [f"ppg_last{form_window}", "gf_ewm", "ga_ewm", "n_played", "last_date", "last_season"]
    now = _asof_before(long[["match_id", "team", "date", "season_start"]], played, ["team"], cols)

    # Partidos jugados en [D-21, D): cantidad antes de D menos cantidad antes de D-21.
    shifted = long[["team", "date"]].assign(date=long["date"] - pd.Timedelta(days=21))
    before_window = _asof_before(shifted, played, ["team"], ["n_played"])["n_played"].fillna(0)

    out = now[["match_id", "team"]].copy()
    out[f"ppg_last{form_window}"] = now[f"ppg_last{form_window}"]
    out["gf_ewm"] = now["gf_ewm"]
    out["ga_ewm"] = now["ga_ewm"]
    out["rest_days"] = (now["date"] - now["last_date"]).dt.days
    out["matches_last21"] = (now["n_played"].fillna(0) - before_window.values).astype(int)
    out["season_opener"] = now["last_season"].ne(now["season_start"])
    return out.reset_index(drop=True)


SHOTS_HALFLIVES = (4, 8, 16)
SHOT_STATS = ("sh_f", "sh_a", "sot_f", "sot_a")


def shot_features(matches: pd.DataFrame, halflives: tuple[int, ...] = SHOTS_HALFLIVES) -> pd.DataFrame:
    """Tiros y tiros al arco a favor / en contra, media exponencial de los partidos ANTERIORES.

    Mismo patrón anti-fuga que el resto: estado después de cada partido jugado y
    as-of estricto antes del día del partido. Una columna por estadística y vida
    media (en partidos): p. ej. sot_f_hl8 = tiros al arco a favor, vida media 8.
    """
    long = team_long(matches)
    played = long[long["played"]].copy()
    g = played.groupby("team", sort=False)
    cols = []
    for hl in halflives:
        for stat in SHOT_STATS:
            col = f"{stat}_hl{hl}"
            played[col] = g[stat].transform(lambda s, hl=hl: s.ewm(halflife=hl).mean())
            cols.append(col)
    now = _asof_before(long[["match_id", "team", "date"]], played, ["team"], cols)
    return now[["match_id", "team"] + cols].reset_index(drop=True)


def table_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Tabla de la temporada (por división) al comienzo del día del partido.

    Devuelve una fila por (match_id, team) con games_played, points, goal_diff,
    goals_for, ppg, gdpg y position. La posición sigue los primeros criterios del
    reglamento de la Premier League (regla C.17: puntos, diferencia de gol, goles a
    favor); el resto de los desempates (head-to-head, desempate) no se modela y los
    empates restantes se resuelven por orden alfabético. Los puntos son los
    obtenidos en cancha: los datos no incluyen descuentos administrativos.
    """
    long = team_long(matches)
    played = long[long["played"]].copy()
    g = played.groupby(["team", "season_start", "division"], sort=False)
    played["t_games"] = g.cumcount() + 1
    played["t_points"] = g["points"].cumsum()
    played["t_gd"] = (played["gf"] - played["ga"]).groupby([played.team, played.season_start, played.division]).cumsum()
    played["t_gf"] = g["gf"].cumsum()
    state_cols = ["t_games", "t_points", "t_gd", "t_gf"]

    # Todos los equipos de la división en cada fecha con partidos (para poder rankear).
    members = long[["season_start", "division", "team"]].drop_duplicates()
    dates = long[["season_start", "division", "date"]].drop_duplicates()
    grid = dates.merge(members, on=["season_start", "division"])
    standing = _asof_before(grid, played, ["team", "season_start", "division"], state_cols)
    standing[state_cols] = standing[state_cols].fillna(0.0)
    standing = standing.sort_values(
        ["season_start", "division", "date", "t_points", "t_gd", "t_gf", "team"],
        ascending=[True, True, True, False, False, False, True],
    )
    standing["position"] = standing.groupby(["season_start", "division", "date"]).cumcount() + 1

    out = long[["match_id", "team", "season_start", "division", "date"]].merge(
        standing[["season_start", "division", "date", "team", "position"] + state_cols],
        on=["season_start", "division", "date", "team"], how="left",
    )
    out = out.rename(columns={"t_games": "games_played", "t_points": "points", "t_gd": "goal_diff", "t_gf": "goals_for"})
    games = out["games_played"].replace(0, np.nan)
    out["ppg"] = out["points"] / games
    out["gdpg"] = out["goal_diff"] / games
    # Sin partidos jugados la posición no significa nada (todos empatados en 0).
    out.loc[out["games_played"] == 0, "position"] = np.nan
    return out[["match_id", "team", "games_played", "points", "goal_diff", "goals_for", "ppg", "gdpg", "position"]]
