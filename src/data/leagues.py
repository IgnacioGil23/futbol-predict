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
    python -m src.data.leagues              # datos de las cuatro ligas (incluida la temporada en curso)
    python -m src.data.leagues --report     # además, reescribe el reporte de calidad versionado
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import FIRST_SEASON_START_YEAR, PROCESSED_DIR, PROJECT_ROOT, season_label, season_start_year
from src.data.download import download_football_data, football_data_path
from src.data.football_data import clean_odds, read_season, validate_rows
from src.league_registry import LEAGUES, OPENFOOTBALL, PRODUCT_LEAGUES  # noqa: F401 - se re-exportan

logger = logging.getLogger(__name__)

LAST_SEASON = 2025                         # 2025-26: última temporada completa (la investigación llega hasta acá)
LEAGUES_DIR = PROCESSED_DIR / "leagues"
QUALITY_REPORT_PATH = PROJECT_ROOT / "reports" / "replication" / "calidad_ligas.json"
SHOT_COLUMNS = ["home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target"]


class LeagueQualityError(RuntimeError):
    """Un problema en los datos que invalidaría las variables."""


def matches_path(code: str) -> Path:
    return LEAGUES_DIR / f"{code}_matches.parquet"


def download_league(code: str, force: bool = False, today: date | None = None) -> None:
    """Primera y segunda división hasta la temporada en curso (que se vuelve a descargar siempre)."""
    league = LEAGUES[code]
    download_football_data(force=force, today=today, divisions=(league["top"], league["second"]))


def assign_match_ids(matches: pd.DataFrame, code: str) -> pd.Series:
    """Id por contenido (división, temporada, fecha y equipos): no depende del orden de las filas, así que ni una
    temporada nueva ni un partido postergado que Football-Data inserta en el medio cambian los ids de los demás."""
    clean = lambda name: "".join(c for c in str(name) if c.isalnum())  # noqa: E731
    return pd.Series([f"{code}-{d}-{s}-{day:%Y%m%d}-{clean(h)}-{clean(a)}" for d, s, day, h, a in
                      zip(matches["division"], matches["season_start"], pd.to_datetime(matches["date"]),
                          matches["home_team"], matches["away_team"])], index=matches.index)


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


def load_league(code: str, today: date | None = None) -> tuple[pd.DataFrame, dict]:
    """Partidos de las dos divisiones desde 2000-01 hasta la temporada en curso (si ya está publicada)."""
    league, frames, report = LEAGUES[code], [], {"seasons": {}, "long_rows": {}, "invalid_odds_rows": 0}
    current = season_start_year(today or date.today())
    for division in (league["top"], league["second"]):
        for start in range(FIRST_SEASON_START_YEAR, current + 1):
            path = football_data_path(division, start)
            if start > LAST_SEASON and not path.exists():
                continue                              # temporada en curso todavía no publicada
            s = read_season(path, division, start)
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
    matches["match_id"] = assign_match_ids(matches, code)
    if matches["match_id"].duplicated().any():
        raise LeagueQualityError(f"{code}: partidos repetidos {list(matches.match_id[matches.match_id.duplicated()])[:3]}")
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
    parser.add_argument("--report", action="store_true",
                        help="reescribir el reporte de calidad de la replicación (QUALITY_REPORT_PATH), que está versionado")
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
    if args.report:                 # la actualización diaria de datos no toca el reporte versionado de la investigación
        QUALITY_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        QUALITY_REPORT_PATH.write_text(json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Reporte -> %s", QUALITY_REPORT_PATH)


if __name__ == "__main__":
    main()
