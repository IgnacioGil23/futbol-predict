"""Captura diaria del xG por equipo y partido de la temporada en curso (docs/preregistro_xg.md).

Guarda en ledger/xg_team_matches.csv (rama monitoring) una fila por equipo y partido terminado, con la fecha de
captura. Mismas reglas que los registros de predicciones: solo se agregan filas y el primer valor capturado es
el definitivo (si Fantasy corrige el xG después, el registro conserva lo que se sabía antes). Es un agregado por
equipo: no republica datos de jugadores.

Un partido solo se captura si están los 11 titulares de cada lado; si no, se reintenta en la próxima corrida.

Uso (lo corre el workflow diario):
    python -m src.monitoring.xg_capture --ledger monitoring/ledger/xg_team_matches.csv
"""

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.config import season_label, season_start_year
from src.data.fpl_live import FplApi, finished_fixtures, player_rows, team_ids, team_xg
from src.monitoring.ledger import append_entries, read_ledger

logger = logging.getLogger(__name__)

DEFAULT_XG_LEDGER = Path("monitoring/ledger/xg_team_matches.csv")
XG_KEY = ["season_start", "home_team", "away_team", "team"]
XG_COLUMNS = ["season", "season_start", "match_date", "home_team", "away_team", "team", "is_home", "xg_f", "xg_a",
              "players", "fpl_fixture", "captured_at_utc"]
UK = ZoneInfo("Europe/London")        # las fechas de Football-Data son las del Reino Unido


def pending_fixtures(fixtures: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    """Partidos terminados cuyo xG todavía no está en el registro (con sus dos equipos)."""
    fixtures = fixtures.assign(season_start=[season_start_year(k.astimezone(UK).date()) for k in fixtures["kickoff"]])
    if existing.empty:
        return fixtures
    done = existing.groupby(["season_start", "home_team", "away_team"]).size()
    done = set(done[done == 2].index)
    keys = zip(fixtures["season_start"], fixtures["home_team"], fixtures["away_team"])
    return fixtures[[k not in done for k in keys]]


def ledger_rows(team: pd.DataFrame, now: datetime) -> pd.DataFrame:
    if team.empty:
        return pd.DataFrame(columns=XG_COLUMNS)
    dates = [k.astimezone(UK).date() for k in team["kickoff"]]
    starts = [season_start_year(d) for d in dates]
    return pd.DataFrame({
        "season": [season_label(s) for s in starts], "season_start": starts,
        "match_date": [d.isoformat() for d in dates], "home_team": team["home_team"], "away_team": team["away_team"],
        "team": team["team"], "is_home": team["is_home"], "xg_f": team["xg_for"].round(6),
        "xg_a": team["xg_against"].round(6), "players": team["players"], "fpl_fixture": team["fixture"],
        "captured_at_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
    })[XG_COLUMNS]


def capture(api: FplApi, existing: pd.DataFrame, now: datetime) -> tuple[pd.DataFrame, list[str]]:
    bootstrap = api.get("bootstrap-static/")
    fixtures = finished_fixtures(api.get("fixtures/"), team_ids(bootstrap))
    pending = pending_fixtures(fixtures, existing)
    if pending.empty:
        return pd.DataFrame(columns=XG_COLUMNS), []
    team, dropped = team_xg(pending, player_rows(api, pending))
    return ledger_rows(team, now), dropped


def history_rows(ledger: pd.DataFrame) -> pd.DataFrame:
    """Registro de xG -> filas de historia para src.serving.shadow_xg.xg_features_for."""
    return pd.DataFrame({
        "match_id": ledger["season"] + "|" + ledger["home_team"] + "|" + ledger["away_team"],
        "season_start": ledger["season_start"].astype(int), "date": ledger["match_date"], "team": ledger["team"],
        "is_home": ledger["is_home"].astype(str).str.lower() == "true", "xg_f": ledger["xg_f"].astype(float),
        "xg_a": ledger["xg_a"].astype(float),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="Captura el xG por equipo de los partidos terminados")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_XG_LEDGER)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    now = datetime.now(timezone.utc)
    existing = read_ledger(args.ledger, XG_COLUMNS)
    rows, dropped = capture(FplApi(), existing, now)
    added = append_entries(args.ledger, rows, columns=XG_COLUMNS, key=XG_KEY, order=["match_date", "home_team", "team"])
    if dropped:
        logger.warning("Partidos sin los 11 titulares de cada lado (se reintentan mañana): %s", dropped)
    logger.info("xG capturado: %d filas nuevas · total %d", added, len(existing) + added)


if __name__ == "__main__":
    main()
