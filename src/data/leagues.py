"""Otras ligas (España, Italia, Alemania, Francia) para la replicación de los tiros y el análisis entre ligas.

Misma fuente y mismo lector que la Premier (Football-Data.co.uk, src.data.football_data.read_season); cada
liga con su segunda división, que le da historia de Elo a los equipos que ascienden. Como la Premier, los datos
se descargan y NO se versionan; solo se versiona el reporte de calidad agregado.

Controles (sin cantidades fijas de equipos, que cambian entre ligas y temporadas):
* formato todos contra todos, ida y vuelta: con n equipos, n(n-1) partidos; cada cruce local-visitante una sola
  vez; cada equipo n-1 partidos de local y n-1 de visitante. Las temporadas que no lo cumplen (por ejemplo, una
  suspendida) se informan y sus partidos se conservan: son partidos reales;
* resultado coherente con los goles, sin fechas faltantes, cuotas imposibles invalidadas (clean_odds);
* cobertura de tiros y tiros al arco por división y temporada.

Uso:
    python -m src.data.leagues
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import FIRST_SEASON_START_YEAR, FOOTBALL_DATA_URL, PROCESSED_DIR, PROJECT_ROOT, season_code, season_label
from src.data.download import _fetch, _session, football_data_path
from src.data.football_data import clean_odds, read_season, validate_rows

logger = logging.getLogger(__name__)

LEAGUES: dict[str, dict] = {
    "ESP": {"name": "España", "top": "SP1", "second": "SP2"},
    "ITA": {"name": "Italia", "top": "I1", "second": "I2"},
    "GER": {"name": "Alemania", "top": "D1", "second": "D2"},
    "FRA": {"name": "Francia", "top": "F1", "second": "F2"},
}
LAST_SEASON = 2025                         # 2025-26: última temporada completa
LEAGUES_DIR = PROCESSED_DIR / "leagues"
QUALITY_REPORT_PATH = PROJECT_ROOT / "reports" / "replication" / "calidad_ligas.json"
SHOT_COLUMNS = ["home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target"]


class LeagueQualityError(RuntimeError):
    """Un problema en los datos que invalidaría las variables."""


def matches_path(code: str) -> Path:
    return LEAGUES_DIR / f"{code}_matches.parquet"


def download_league(code: str, force: bool = False) -> None:
    session, league = _session(), LEAGUES[code]
    for division in (league["top"], league["second"]):
        for start in range(FIRST_SEASON_START_YEAR, LAST_SEASON + 1):
            path = football_data_path(division, start)
            if force or not path.exists():
                url = FOOTBALL_DATA_URL.format(season_code=season_code(start), division=division)
                logger.info("Descargado %s (%d bytes)", url, _fetch(session, url, path))


def round_robin_check(season: pd.DataFrame) -> dict:
    """Formato ida y vuelta deducido de los datos (sin cantidad fija de equipos)."""
    teams = pd.unique(season[["home_team", "away_team"]].to_numpy().ravel())
    n = len(teams)
    pairs = season.groupby(["home_team", "away_team"]).size()
    home, away = season["home_team"].value_counts(), season["away_team"].value_counts()
    return {"teams": int(n), "matches": int(len(season)), "expected": int(n * (n - 1)),
            "repeated_pairs": int((pairs > 1).sum()),
            "complete": bool(len(season) == n * (n - 1) and (home == n - 1).all() and (away == n - 1).all())}


def shot_coverage(season: pd.DataFrame) -> float:
    return float(season[SHOT_COLUMNS].notna().all(axis=1).mean())


def load_league(code: str) -> tuple[pd.DataFrame, dict]:
    league, frames, report = LEAGUES[code], [], {"seasons": {}, "long_rows": {}, "invalid_odds_rows": 0}
    for division in (league["top"], league["second"]):
        for start in range(FIRST_SEASON_START_YEAR, LAST_SEASON + 1):
            s = read_season(football_data_path(division, start), division, start)
            if s.attrs["n_long_rows"]:
                report["long_rows"][f"{division} {season_label(start)}"] = s.attrs["n_long_rows"]
            if s["date"].isna().any():
                raise LeagueQualityError(f"{division} {season_label(start)}: partidos sin fecha")
            s, odds_report = clean_odds(s)            # primero se invalidan las cuotas imposibles
            report["invalid_odds_rows"] += int(len(odds_report))
            validate_rows(s)
            check = round_robin_check(s)
            if check["repeated_pairs"]:
                raise LeagueQualityError(f"{division} {season_label(start)}: cruces repetidos")
            report["seasons"][f"{division} {season_label(start)}"] = {**check, "shots": shot_coverage(s)}
            frames.append(s)
    matches = pd.concat(frames, ignore_index=True)
    matches["match_id"] = [f"{code}-{d}-{s}-{i:04d}" for i, (d, s) in
                           enumerate(zip(matches["division"], matches["season_start"]))]
    # columnas que build_features espera y que en otras ligas no existen (Elo de ClubElo)
    matches["clubelo_home"] = matches["clubelo_away"] = float("nan")
    matches["clubelo_provisional"] = False
    report["incomplete_seasons"] = [k for k, v in report["seasons"].items() if not v["complete"]]
    report["first_full_shots_season"] = first_full_shots_season(report, league["top"])
    return matches, report


def first_full_shots_season(report: dict, division: str, threshold: float = 0.99) -> str | None:
    """Primera temporada de `division` desde la cual TODAS las siguientes tienen tiros en ≥ 99% de los partidos."""
    seasons = [season_label(s) for s in range(FIRST_SEASON_START_YEAR, LAST_SEASON + 1)]
    ok = [report["seasons"][f"{division} {s}"]["shots"] >= threshold for s in seasons]
    for i in range(len(seasons)):
        if all(ok[i:]):
            return seasons[i]
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    LEAGUES_DIR.mkdir(parents=True, exist_ok=True)
    quality = {"generated": date.today().isoformat(), "source": "https://www.football-data.co.uk", "leagues": {}}
    for code, league in LEAGUES.items():
        download_league(code, force=args.force)
        matches, report = load_league(code)
        matches.to_parquet(matches_path(code), index=False)
        quality["leagues"][code] = {"name": league["name"], **report}
        logger.info("%s: %d partidos · temporadas incompletas %s · tiros completos desde %s", league["name"],
                    len(matches), report["incomplete_seasons"] or "ninguna", report["first_full_shots_season"])
    QUALITY_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUALITY_REPORT_PATH.write_text(json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte -> %s", QUALITY_REPORT_PATH)


if __name__ == "__main__":
    main()
