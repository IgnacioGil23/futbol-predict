"""xG por equipo y partido de la temporada en curso, desde la API de Fantasy Premier League.

La API no está documentada oficialmente; se usan tres llamadas públicas (sin clave):
* bootstrap-static: equipos (id de la temporada -> código estable) y jugadores;
* fixtures: partidos con su fecha del torneo, equipos y si terminaron;
* event/{fecha}/live: quién tuvo participación en qué partido de esa fecha (para no consultar a todos);
* element-summary/{jugador}: estadísticas POR PARTIDO (xG incluido). Es la única que separa los dos partidos de
  un equipo en una fecha doble; event/live suma la fecha entera.

xG a favor de un equipo = suma del xG de sus jugadores en el partido; xG en contra = el del rival (misma
definición que la prueba histórica, docs/preregistro_fpl.md).
"""

import logging
import time

import numpy as np
import pandas as pd
import requests

from src.data.download import _session
from src.data.fpl_archive import FPL_API, FPL_TEAM_CODES, ArchiveQualityError

logger = logging.getLogger(__name__)

REQUEST_PAUSE_SECONDS = 0.25     # consultas espaciadas: la API es pública y no documenta límites
TIMEOUT = 60


class FplApi:
    """Cliente mínimo con reintentos y pausa entre consultas."""

    def __init__(self, session: requests.Session | None = None, pause: float = REQUEST_PAUSE_SECONDS):
        self.session, self.pause = session or _session(), pause

    def get(self, path: str) -> dict | list:
        response = self.session.get(f"{FPL_API}/{path}", timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        time.sleep(self.pause)
        return response.json()


def team_ids(bootstrap: dict) -> dict[int, str]:
    """id de equipo de la temporada -> nombre canónico (vía el código estable, como en el archivo)."""
    teams = pd.DataFrame(bootstrap["teams"])
    unknown = sorted(set(teams["code"]) - set(FPL_TEAM_CODES))
    if unknown:
        raise ArchiveQualityError(f"Códigos de equipo sin mapear: {unknown}")
    return {int(i): FPL_TEAM_CODES[int(c)] for i, c in zip(teams["id"], teams["code"])}


def finished_fixtures(fixtures: list[dict], ids: dict[int, str]) -> pd.DataFrame:
    fx = pd.DataFrame(fixtures)
    fx = fx[fx["finished"].astype(bool) & fx["event"].notna()].copy()
    fx["home_team"], fx["away_team"] = fx["team_h"].map(ids), fx["team_a"].map(ids)
    fx["kickoff"] = pd.to_datetime(fx["kickoff_time"], utc=True)
    return fx[["id", "event", "kickoff", "home_team", "away_team", "team_h_score", "team_a_score"]].rename(
        columns={"id": "fixture"})


def player_rows(api: FplApi, fixtures: pd.DataFrame) -> pd.DataFrame:
    """Filas por jugador y partido (solo los partidos de `fixtures`) con minutos y xG."""
    wanted = set(fixtures["fixture"])
    elements: set[int] = set()
    for gw in sorted(fixtures["event"].astype(int).unique()):
        for e in api.get(f"event/{gw}/live/")["elements"]:
            if any(x["fixture"] in wanted for x in e["explain"]):
                elements.add(int(e["id"]))
    rows = []
    for element in sorted(elements):
        for h in api.get(f"element-summary/{element}/")["history"]:
            if h["fixture"] in wanted:
                rows.append({"element": element, "fixture": h["fixture"], "was_home": bool(h["was_home"]),
                             "minutes": int(h["minutes"]), "starts": int(h["starts"]),
                             "expected_goals": float(h["expected_goals"])})
    return pd.DataFrame(rows, columns=["element", "fixture", "was_home", "minutes", "starts", "expected_goals"])


def team_xg(fixtures: pd.DataFrame, players: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Una fila por equipo y partido con xG a favor y en contra. Devuelve también los partidos descartados
    (sin los 11 titulares de cada lado: la captura estaría incompleta)."""
    p = players.merge(fixtures, on="fixture")
    p["team"] = np.where(p["was_home"], p["home_team"], p["away_team"])
    g = p.groupby(["fixture", "team"])
    per_team = pd.DataFrame({"xg_for": g["expected_goals"].sum(), "starts": g["starts"].sum(),
                             "players": g["minutes"].apply(lambda m: int((m > 0).sum()))}).reset_index()
    complete = per_team.groupby("fixture")["starts"].agg(lambda s: len(s) == 2 and (s == 11).all())
    dropped = [f"{r.home_team}-{r.away_team}" for r in fixtures.itertuples() if not complete.get(r.fixture, False)]
    per_team = per_team[per_team["fixture"].map(complete).fillna(False).astype(bool)]
    opp = per_team[["fixture", "team", "xg_for"]].rename(columns={"team": "opponent", "xg_for": "xg_against"})
    out = per_team.merge(opp, on="fixture")
    out = out[out["team"] != out["opponent"]].merge(fixtures, on="fixture")
    out["is_home"] = out["team"] == out["home_team"]
    return out.sort_values(["kickoff", "fixture", "is_home"], ascending=[True, True, False]).reset_index(drop=True), dropped
