"""xG por club para la web (pestaña Equipos): calidad de las ocasiones creadas y concedidas.

Fuentes (agregadas por equipo y partido, sin datos de jugadores):
* temporadas 2022-23 a 2025-26: la historia guardada con el candidato A (models/shadow_xg/xg_history.csv), que viene
  del archivo de Fantasy Premier League (en 2022-23, desde la fecha 16: antes el archivo no registró xG);
* temporada en curso: el registro diario de la rama monitoring (ledger/xg_team_matches.csv), si está disponible.

El xG (expected goals) mide la calidad de las ocasiones según los tiros de cada partido. No es lo mismo que los
"goles esperados" que muestra la web en cada partido, que son la predicción del modelo a partir del Elo.
"""

from pathlib import Path

import pandas as pd

from src.config import PREMIER_LEAGUE, season_label
from src.data.teams import display_name, slug
from src.serving.shadow_xg import XG_HISTORY_PATH
from src.serving.store import MatchStore

SERIES_SEASONS = 2          # partido a partido: la temporada en curso y la anterior


def team_matches(store: MatchStore, history: pd.DataFrame, live: pd.DataFrame | None) -> pd.DataFrame:
    """Una fila por equipo y partido con xG a favor/en contra y goles a favor/en contra."""
    pl = store.matches[(store.matches.division == PREMIER_LEAGUE) & store.matches.home_goals.notna()]
    res = pl[["match_id", "date", "season_start", "home_team", "away_team", "home_goals", "away_goals"]]
    hist = history.merge(res, on=["match_id", "season_start"], how="inner", suffixes=("", "_m"))
    hist["date"] = hist["date_m"]
    frames = [hist]
    if live is not None and len(live):
        lv = live.assign(date=pd.to_datetime(live["match_date"]), season_start=live["season_start"].astype(int),
                         is_home=live["is_home"].astype(str).str.lower() == "true")
        lv = lv.merge(res, on=["date", "home_team", "away_team", "season_start"], how="inner")
        frames.append(lv)
    tm = pd.concat([f[["match_id", "season_start", "date", "team", "is_home", "xg_f", "xg_a", "home_team",
                       "away_team", "home_goals", "away_goals"]] for f in frames], ignore_index=True)
    tm = tm.drop_duplicates(["match_id", "team"])
    tm["gf"] = tm["home_goals"].where(tm["is_home"], tm["away_goals"]).astype(float)
    tm["ga"] = tm["away_goals"].where(tm["is_home"], tm["home_goals"]).astype(float)
    tm["opponent"] = tm["away_team"].where(tm["is_home"], tm["home_team"])
    return tm.sort_values(["date", "match_id", "team"]).reset_index(drop=True)


def season_table(g: pd.DataFrame) -> dict:
    teams = g.groupby("team").agg(played=("match_id", "size"), xg_for=("xg_f", "sum"), xg_against=("xg_a", "sum"),
                                  goals_for=("gf", "sum"), goals_against=("ga", "sum")).reset_index()
    rows = [{"team": r.team, "name": display_name(r.team), "slug": slug(r.team), "played": int(r.played),
             "xg_for": round(float(r.xg_for), 2), "xg_against": round(float(r.xg_against), 2),
             "goals_for": int(r.goals_for), "goals_against": int(r.goals_against)} for r in teams.itertuples()]
    return {"teams": sorted(rows, key=lambda r: -(r["xg_for"] - r["xg_against"]) / r["played"]),
            "league": {"xg_per_team_game": round(float(g["xg_f"].mean()), 3),
                       "goals_per_team_game": round(float(g["gf"].mean()), 3)},
            "first_date": str(g["date"].min().date()), "last_date": str(g["date"].max().date()),
            "matches": int(g["match_id"].nunique())}


def build_xg(store: MatchStore, live_ledger: Path | None = None) -> dict:
    history = pd.read_csv(XG_HISTORY_PATH)
    live = pd.read_csv(live_ledger) if live_ledger is not None and Path(live_ledger).exists() else None
    tm = team_matches(store, history, live)
    seasons = []
    for s, g in sorted(tm.groupby("season_start"), key=lambda x: -x[0]):
        table = season_table(g)
        # temporada con datos desde más adelante que su primera fecha (2022-23): se avisa
        pl = store.matches[(store.matches.division == PREMIER_LEAGUE) & (store.matches.season_start == s)]
        table["partial_start"] = bool(pd.Timestamp(table["first_date"]) > pl["date"].min())
        seasons.append({"season": season_label(int(s)), **table})
    recent = sorted(tm["season_start"].unique())[-SERIES_SEASONS:]
    series = {}
    for team, g in tm[tm["season_start"].isin(recent)].groupby("team"):
        series[slug(team)] = [{"date": str(r.date.date()), "season": season_label(int(r.season_start)),
                               "opponent": display_name(r.opponent), "home": bool(r.is_home),
                               "xg_for": round(float(r.xg_f), 2), "xg_against": round(float(r.xg_a), 2),
                               "goals_for": int(r.gf), "goals_against": int(r.ga)} for r in g.itertuples()]
    return {"source": "Fantasy Premier League (estadísticas por jugador agregadas por equipo)",
            "seasons": seasons, "series": series}
