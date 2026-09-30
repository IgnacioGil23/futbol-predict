"""Variables de los candidatos A (xG) y B (fuerza de la alineación), según docs/preregistro_fpl.md.

Entrada: data/processed/fpl_player_matches.parquet (src/data/fpl_archive.py), una fila por jugador y
partido. Salida: una fila por partido de Premier con las variables del local y del visitante.

* A: xG a favor y en contra, media exponencial (vida media 4 partidos) de los partidos del equipo con xG
  registrado jugados ANTES del día del partido.
* B: desviación relativa entre el precio de los 11 titulares del partido y el promedio de los 5 partidos
  anteriores del equipo con titulares registrados. Usa la alineación del propio partido: es información de
  una hora antes, no de días antes.
* Control de B: la desviación del partido anterior del equipo (información de días antes).

Las series de cada equipo no se cortan entre temporadas.
"""

import numpy as np
import pandas as pd

from src.features.team_state import _asof_before

XG_HALFLIFE = 4
USUAL_WINDOW = 5
A_COLUMNS = [f"{s}_{side}" for side in ("home", "away") for s in ("xg_f_hl4", "xg_a_hl4")]
B_COLUMNS = ["xi_dev_home", "xi_dev_away"]
B_CONTROL_COLUMNS = ["xi_dev_prev_home", "xi_dev_prev_away"]


def team_matches(players: pd.DataFrame, dates: pd.DataFrame) -> pd.DataFrame:
    """Una fila por equipo y partido: xG a favor y en contra y valor del XI (NaN si el archivo no lo registró).

    `dates`: match_id y date (la fecha de Football-Data, la misma que usan las demás variables)."""
    recorded = players["starts"].notna()
    g = players.assign(xi_price=np.where(players["starts"] == 1, players["price"], 0.0)).groupby(
        ["match_id", "team"], sort=False)
    tm = pd.DataFrame({
        "season_start": g["season_start"].first(), "is_home": g["is_home"].first(),
        "xg_f": g["expected_goals"].sum(min_count=1),
        "xi_value": g["xi_price"].sum(),
        "recorded": recorded.groupby([players["match_id"], players["team"]]).all(),
    }).reset_index()
    tm.loc[~tm["recorded"], ["xg_f", "xi_value"]] = np.nan
    opp = tm[["match_id", "team", "xg_f"]].rename(columns={"team": "opponent", "xg_f": "xg_a"})
    tm = tm.merge(opp, on="match_id")
    tm = tm[tm["team"] != tm["opponent"]].drop(columns="opponent")
    tm = tm.merge(dates[["match_id", "date"]], on="match_id", how="left", validate="many_to_one")
    if tm["date"].isna().any():
        raise ValueError("Partidos del archivo sin fecha de Football-Data")
    return tm.sort_values(["team", "date"]).reset_index(drop=True)


def xg_features(tm: pd.DataFrame) -> pd.DataFrame:
    """A: por (match_id, team), la media exponencial del xG de los partidos anteriores al día del partido."""
    rec = tm[tm["recorded"]].copy()
    g = rec.groupby("team", sort=False)
    for col in ("xg_f", "xg_a"):
        rec[f"{col}_hl4"] = g[col].transform(lambda s: s.ewm(halflife=XG_HALFLIFE).mean())
    cols = ["xg_f_hl4", "xg_a_hl4"]
    return _asof_before(tm[["match_id", "team", "date"]], rec, ["team"], cols)[["match_id", "team"] + cols]


def lineup_features(tm: pd.DataFrame) -> pd.DataFrame:
    """B y su control: por (match_id, team), la desviación del XI respecto del habitual.

    Habitual = promedio de los 5 partidos anteriores con titulares registrados (los que haya, al menos 1);
    sin partidos anteriores, desviación 0. Partidos sin titulares registrados: NaN (no calculable)."""
    rec = tm[tm["recorded"]].sort_values(["team", "date"]).copy()
    usual = rec.groupby("team", sort=False)["xi_value"].transform(
        lambda s: s.shift(1).rolling(USUAL_WINDOW, min_periods=1).mean())
    rec["xi_dev"] = (rec["xi_value"] / usual - 1).fillna(0.0)
    rec["xi_dev_prev"] = rec.groupby("team", sort=False)["xi_dev"].shift(1).fillna(0.0)
    out = tm[["match_id", "team"]].merge(rec[["match_id", "team", "xi_dev", "xi_dev_prev"]],
                                         on=["match_id", "team"], how="left")
    return out


def match_features(players: pd.DataFrame, dates: pd.DataFrame) -> pd.DataFrame:
    """Una fila por partido (match_id) con las variables de A, B y el control, para local y visitante."""
    tm = team_matches(players, dates)
    per_team = tm[["match_id", "team", "is_home"]].merge(xg_features(tm), on=["match_id", "team"]).merge(
        lineup_features(tm), on=["match_id", "team"])
    cols = ["xg_f_hl4", "xg_a_hl4", "xi_dev", "xi_dev_prev"]
    home = per_team[per_team["is_home"]].set_index("match_id")[cols].add_suffix("_home")
    away = per_team[~per_team["is_home"]].set_index("match_id")[cols].add_suffix("_away")
    return home.join(away, how="inner").reset_index()
