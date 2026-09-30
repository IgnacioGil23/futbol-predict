"""Construye el dataset procesado a partir de los CSV crudos.

Salidas (en data/processed/):
    matches.parquet       Premier League (E0) + Championship (E1), un partido por fila,
                          en el esquema de src.data.football_data, más el Elo de ClubElo.
    data_quality.json     Resumen de chequeos y limpiezas aplicadas.

Uso:
    python -m src.data.load
"""

import json
import logging
from datetime import date

import numpy as np
import pandas as pd

from src.config import (
    CLUBELO_PROVISIONAL_FROM,
    CLUBELO_SNAPSHOTS_PATH,
    DIVISIONS,
    FIRST_SEASON_START_YEAR,
    PROCESSED_DIR,
    season_start_year,
)
from src.data.checks import check_season
from src.data.download import football_data_path
from src.data.football_data import clean_odds, read_season, validate_rows
from src.data.teams import canonical_team

logger = logging.getLogger(__name__)

MATCHES_PATH = PROCESSED_DIR / "matches.parquet"
QUALITY_PATH = PROCESSED_DIR / "data_quality.json"


def load_raw_matches(today: date | None = None) -> tuple[pd.DataFrame, dict]:
    current = season_start_year(today or date.today())
    frames, long_rows = [], {}
    for division in DIVISIONS:
        for start_year in range(FIRST_SEASON_START_YEAR, current + 1):
            path = football_data_path(division, start_year)
            if not path.exists():
                if start_year == current:
                    continue
                raise FileNotFoundError(f"Falta {path}: correr `python -m src.data.download`")
            season = read_season(path, division, start_year)
            if season.attrs["n_long_rows"]:
                long_rows[f"{division} {season['season'].iloc[0]}"] = season.attrs["n_long_rows"]
            frames.append(season)
    matches = pd.concat(frames, ignore_index=True)
    matches.attrs["current_season_start"] = current
    return matches, long_rows


def attach_clubelo(matches: pd.DataFrame) -> pd.DataFrame:
    """Agrega el Elo de ClubElo vigente al momento de cada partido.

    Regla: el último snapshot con fecha <= fecha del partido. Se verificó
    empíricamente (notebook 01_eda) que un snapshot NO incorpora partidos jugados
    ese mismo día, así que la regla no filtra información del resultado.
    Los snapshots se toman los días 1 y 15, así que el valor puede tener hasta
    ~15 días de antigüedad; desde CLUBELO_PROVISIONAL_FROM son una continuación
    provisional calculada por el autor del dataset, no ClubElo.
    """
    snapshots = pd.read_csv(CLUBELO_SNAPSHOTS_PATH, parse_dates=["date"])
    snapshots = snapshots[snapshots["country"] == "ENG"].copy()
    snapshots["club"] = snapshots["club"].map(canonical_team).astype("string")
    snapshots = snapshots.rename(columns={"date": "elo_date"}).sort_values("elo_date")

    out = matches.copy()
    out["_row"] = np.arange(len(out))
    for side in ("home", "away"):
        left = out[["_row", "date", f"{side}_team"]].rename(columns={f"{side}_team": "club"})
        left["date"] = left["date"].astype("datetime64[ns]")
        snapshots["elo_date"] = snapshots["elo_date"].astype("datetime64[ns]")
        merged = pd.merge_asof(
            left.sort_values("date"),
            snapshots[["elo_date", "club", "elo"]],
            left_on="date",
            right_on="elo_date",
            by="club",
            direction="backward",
            allow_exact_matches=True,
        ).set_index("_row").loc[out["_row"]]
        out[f"clubelo_{side}"] = merged["elo"].to_numpy()
        out[f"clubelo_{side}_date"] = merged["elo_date"].to_numpy()
    provisional = pd.Timestamp(CLUBELO_PROVISIONAL_FROM)
    out["clubelo_provisional"] = (out["clubelo_home_date"] >= provisional) | (
        out["clubelo_away_date"] >= provisional
    )
    return out.drop(columns="_row")


def build_dataset(today: date | None = None) -> pd.DataFrame:
    matches, long_rows = load_raw_matches(today)
    current = matches.attrs["current_season_start"]

    matches, odds_report = clean_odds(matches)
    validate_rows(matches)

    season_checks = [
        check_season(group, is_current=start == current)
        for (_, start), group in matches.groupby(["division", "season_start"], sort=True)
    ]
    failures = [c for c in season_checks if c.problems]
    if failures:
        raise ValueError("Temporadas con problemas: " + "; ".join(
            f"{c.division} {c.season}: {', '.join(c.problems)}" for c in failures
        ))

    matches = attach_clubelo(matches)
    matches = matches.sort_values(["date", "division", "time", "home_team"], na_position="first")
    matches = matches.reset_index(drop=True)
    matches.insert(0, "match_id", [
        f"{d:%Y%m%d}_{div}_{h}_{a}".replace(" ", "").replace("'", "")
        for d, div, h, a in zip(matches["date"], matches["division"], matches["home_team"], matches["away_team"])
    ])
    if matches["match_id"].duplicated().any():
        raise ValueError("match_id duplicado")

    quality = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "matches_by_division": matches["division"].value_counts().to_dict(),
        "date_range": [str(matches["date"].min().date()), str(matches["date"].max().date())],
        "rows_with_extra_fields_recovered": long_rows,
        "invalid_odds_set_to_nan": odds_report.astype(str).to_dict("records"),
        "seasons": [
            {"division": c.division, "season": c.season, "matches": c.matches,
             "expected": c.expected_matches, "complete": c.complete}
            for c in season_checks
        ],
        "clubelo_missing": int(matches[["clubelo_home", "clubelo_away"]].isna().any(axis=1).sum()),
    }
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    matches.to_parquet(MATCHES_PATH, index=False)
    QUALITY_PATH.write_text(json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8")
    return matches


def load_matches(division: str | None = None) -> pd.DataFrame:
    """Lee el dataset procesado (opcionalmente filtrado por división)."""
    matches = pd.read_parquet(MATCHES_PATH)
    if division is not None:
        matches = matches[matches["division"] == division].reset_index(drop=True)
    return matches


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    matches = build_dataset()
    pl = matches[matches["division"] == "E0"]
    logger.info("Guardado %s (%d partidos; %d de Premier League)", MATCHES_PATH, len(matches), len(pl))
    logger.info("Premier League: %s a %s", pl["date"].min().date(), pl["date"].max().date())
    logger.info("Resultados PL: %s", pl["result"].value_counts().to_dict())


if __name__ == "__main__":
    main()
