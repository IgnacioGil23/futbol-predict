"""Próximos partidos publicados por Football-Data.co.uk (fixtures.csv).

El archivo trae los partidos de los próximos días de todas las ligas, con cuotas
pre-cierre. Football-Data lo publica pocos días antes de cada fecha.
"""

import io

import pandas as pd
import requests

from src.config import PREMIER_LEAGUE
from src.data.football_data import _parse_dates
from src.data.teams import canonical_team

FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"


def parse_fixtures(text: str, division: str = PREMIER_LEAGUE) -> pd.DataFrame:
    """CSV de fixtures -> partidos de `division` con nombres canónicos y fecha parseada."""
    df = pd.read_csv(io.StringIO(text), dtype=str)
    df.columns = [c.strip().lstrip("﻿") for c in df.columns]
    df = df[df["Div"].str.strip() == division].copy()
    if df.empty:
        return df.assign(date=pd.Series(dtype="datetime64[ns]"))
    df["date"] = _parse_dates(df["Date"].str.strip().astype("string")).astype("datetime64[ns]")
    for col in ("HomeTeam", "AwayTeam"):
        df[col] = df[col].map(canonical_team)
    for col in ("B365H", "B365D", "B365A"):
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    return df.reset_index(drop=True)


def fetch_fixtures(division: str = PREMIER_LEAGUE, timeout: int = 60) -> pd.DataFrame:
    response = requests.get(FIXTURES_URL, timeout=timeout)
    response.raise_for_status()
    return parse_fixtures(response.content.decode("utf-8-sig", errors="replace"), division)
