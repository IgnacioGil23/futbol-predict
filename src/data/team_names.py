"""Nombres de los equipos de las otras ligas (configs/leagues/team_names.json).

Por liga:
* "openfootball": nombre del calendario de openfootball -> nombre de Football-Data (canónico). Se deduce de los
  partidos ya jugados (src.data.schedule.infer_names) y se acumula: una traducción ya guardada no se pierde.
* "display": nombre para mostrar en la web (curado a mano; sin entrada, el de Football-Data).
* "short": abreviatura de tres letras para el escudo genérico.

Uso (actualiza la tabla con la temporada en curso):
    python -m src.data.team_names
"""

import argparse
import json
import logging
from datetime import date
from functools import lru_cache

import pandas as pd
import requests

from src.config import PROJECT_ROOT, season_start_year
from src.data.leagues import LEAGUES, matches_path
from src.data.schedule import fetch_schedule, infer_names

logger = logging.getLogger(__name__)

TEAM_NAMES_PATH = PROJECT_ROOT / "configs" / "leagues" / "team_names.json"


@lru_cache(maxsize=1)
def _table() -> dict:
    if not TEAM_NAMES_PATH.exists():
        return {}
    return json.loads(TEAM_NAMES_PATH.read_text(encoding="utf-8"))


def load_names(code: str) -> dict[str, str]:
    """openfootball -> Football-Data de la liga `code`."""
    return dict(_table().get(code, {}).get("openfootball", {}))


def league_display_name(team: str, code: str) -> str:
    return _table().get(code, {}).get("display", {}).get(team, team)


def league_short_name(team: str, code: str) -> str | None:
    return _table().get(code, {}).get("short", {}).get(team)


def merge_names(old: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    """Agrega las traducciones nuevas sin perder las guardadas; si una cambia, gana la nueva (y se avisa)."""
    for raw, name in new.items():
        if raw in old and old[raw] != name:
            logger.warning("Cambia la traducción de %r: %s -> %s", raw, old[raw], name)
    return dict(sorted({**old, **new}.items()))


def update(today: date | None = None) -> dict:
    table = json.loads(TEAM_NAMES_PATH.read_text(encoding="utf-8")) if TEAM_NAMES_PATH.exists() else {}
    current = season_start_year(today or date.today())
    for code, league in LEAGUES.items():
        entry = table.setdefault(code, {"openfootball": {}, "display": {}, "short": {}})
        matches = pd.read_parquet(matches_path(code))
        for season in (current,):          # openfootball cambió de formato: las temporadas viejas no se leen
            try:
                schedule = fetch_schedule(season, league=code, names={})
            except requests.RequestException as err:
                logger.warning("%s %d: sin calendario (%s)", code, season, err)
                continue
            results = matches[(matches.division == league["top"]) & (matches.season_start == season)]
            entry["openfootball"] = merge_names(entry["openfootball"], infer_names(schedule, results))
            raw = set(schedule.home_raw) | set(schedule.away_raw)
            missing = sorted(raw - set(entry["openfootball"]))
            if missing:
                logger.warning("%s %d: sin traducir %s", code, season, missing)
                # Anotación visible en GitHub Actions: sus partidos no se publican hasta que se traduzcan (un ascendido
                # se traduce solo después de su primer partido; si no, agregarlo a mano en TEAM_NAMES_PATH).
                print(f"::warning::{code}: equipos del calendario sin traducir {missing}")
    TEAM_NAMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEAM_NAMES_PATH.write_text(json.dumps(table, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    _table.cache_clear()
    return table


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    table = update()
    for code, entry in table.items():
        logger.info("%s: %d nombres de openfootball traducidos", code, len(entry["openfootball"]))


if __name__ == "__main__":
    main()
