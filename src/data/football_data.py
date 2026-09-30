"""Lectura robusta de los CSV de Football-Data.co.uk.

Por qué no alcanza con `pd.read_csv`:

* Algunas temporadas tienen filas con MÁS campos que el encabezado (en E0 2003/04
  y 2004/05 los últimos 45 partidos de cada una: se agregaron casas de apuestas a
  mitad de temporada sin actualizar el encabezado). `read_csv` falla o, según la
  herramienta, descarta esas filas en silencio; así fue como el dataset derivado
  que usábamos antes perdió 90 partidos. Acá los campos extra (que siempre van al
  final) se descartan y la fila se conserva.
* El formato de fecha cambia entre temporadas (dd/mm/yy y dd/mm/yyyy).
* Los nombres de columnas de cuotas cambian con los años (`BbAvH` -> `AvgH`).

Referencia de columnas: https://www.football-data.co.uk/notes.txt
Las cuotas "sin C" (p. ej. B365H) son pre-cierre: se toman el viernes a la tarde
para partidos de fin de semana y el martes para los de mitad de semana. Las
cuotas "con C" (p. ej. PSCH) son de cierre.
"""

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import season_label
from src.data.teams import canonical_team

# Columna del esquema propio -> columnas candidatas en Football-Data (en orden de
# preferencia). Solo se listan las que el proyecto usa.
COLUMN_SOURCES: dict[str, tuple[str, ...]] = {
    "time": ("Time",),
    "home_team": ("HomeTeam", "HT"),
    "away_team": ("AwayTeam", "AT"),
    "home_goals": ("FTHG", "HG"),
    "away_goals": ("FTAG", "AG"),
    "result": ("FTR", "Res"),
    "ht_home_goals": ("HTHG",),
    "ht_away_goals": ("HTAG",),
    "ht_result": ("HTR",),
    "referee": ("Referee",),
    "home_shots": ("HS",),
    "away_shots": ("AS",),
    "home_shots_on_target": ("HST",),
    "away_shots_on_target": ("AST",),
    "home_fouls": ("HF",),
    "away_fouls": ("AF",),
    "home_corners": ("HC",),
    "away_corners": ("AC",),
    "home_yellow": ("HY",),
    "away_yellow": ("AY",),
    "home_red": ("HR",),
    "away_red": ("AR",),
    # Cuotas 1X2
    "b365_home": ("B365H",),
    "b365_draw": ("B365D",),
    "b365_away": ("B365A",),
    "b365c_home": ("B365CH",),
    "b365c_draw": ("B365CD",),
    "b365c_away": ("B365CA",),
    "ps_home": ("PSH",),
    "ps_draw": ("PSD",),
    "ps_away": ("PSA",),
    "psc_home": ("PSCH",),
    "psc_draw": ("PSCD",),
    "psc_away": ("PSCA",),
    "avg_home": ("AvgH", "BbAvH"),
    "avg_draw": ("AvgD", "BbAvD"),
    "avg_away": ("AvgA", "BbAvA"),
    "max_home": ("MaxH", "BbMxH"),
    "max_draw": ("MaxD", "BbMxD"),
    "max_away": ("MaxA", "BbMxA"),
    # Total de goles 2.5 (Bet365, pre-cierre)
    "b365_over25": ("B365>2.5",),
    "b365_under25": ("B365<2.5",),
}

STRING_COLUMNS = {"time", "home_team", "away_team", "result", "ht_result", "referee"}
INT_COLUMNS = {
    "home_goals", "away_goals", "ht_home_goals", "ht_away_goals",
    "home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target",
    "home_fouls", "away_fouls", "home_corners", "away_corners",
    "home_yellow", "away_yellow", "home_red", "away_red",
}  # fmt: skip

OUTPUT_COLUMNS = ["division", "season", "season_start", "date", *COLUMN_SOURCES]


def _read_rows(path: Path) -> tuple[list[str], list[list[str]], int]:
    """Devuelve (encabezado, filas recortadas al ancho del encabezado, n filas largas)."""
    # Los archivos viejos vienen en latin-1 y los nuevos en UTF-8 con BOM.
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.reader(text.splitlines())
    header = [h.strip() for h in next(reader)]
    width = len(header)
    rows, n_long = [], 0
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue  # filas vacías de relleno al final de algunos archivos
        if len(row) > width:
            # Solo se aceptan si los campos sobrantes son cuotas agregadas al
            # final: todo lo que está dentro del ancho del encabezado mantiene su
            # posición. validate_rows() lo verifica con reglas de consistencia.
            n_long += 1
            row = row[:width]
        rows.append(row + [""] * (width - len(row)))
    return header, rows, n_long


def _parse_dates(values: pd.Series) -> pd.Series:
    """Fechas dd/mm/yy o dd/mm/yyyy, sin inferencia ambigua de formato."""
    long = pd.to_datetime(values, format="%d/%m/%Y", errors="coerce")
    short = pd.to_datetime(values, format="%d/%m/%y", errors="coerce")
    dates = long.where(values.str.len() == 10, short)
    if dates.isna().any():
        bad = values[dates.isna()].unique()[:5]
        raise ValueError(f"Fechas no parseables: {list(bad)}")
    return dates


def read_season(path: Path, division: str, start_year: int) -> pd.DataFrame:
    """Lee un CSV de Football-Data y lo devuelve en el esquema del proyecto."""
    header, rows, n_long = _read_rows(path)
    # Encabezados duplicados o vacíos: se conserva la primera aparición.
    first_index: dict[str, int] = {}
    for i, name in enumerate(header):
        if name and name not in first_index:
            first_index[name] = i

    def column(candidates: tuple[str, ...]) -> list[str] | None:
        for name in candidates:
            if name in first_index:
                i = first_index[name]
                return [r[i].strip() for r in rows]
        return None

    data: dict[str, object] = {}
    for target, candidates in COLUMN_SOURCES.items():
        values = column(candidates)
        if values is None:
            data[target] = np.nan
        elif target in STRING_COLUMNS:
            data[target] = pd.Series(values, dtype="string").replace("", pd.NA)
        else:
            data[target] = pd.to_numeric(pd.Series(values), errors="coerce")

    df = pd.DataFrame(data, index=range(len(rows)))
    df["date"] = _parse_dates(pd.Series(column(("Date",)), dtype="string")).astype("datetime64[ns]")
    df["division"] = pd.Series(division, index=df.index, dtype="string")
    df["season_start"] = start_year
    df["season"] = pd.Series(season_label(start_year), index=df.index, dtype="string")
    df["home_team"] = df["home_team"].map(canonical_team).astype("string")
    df["away_team"] = df["away_team"].map(canonical_team).astype("string")

    # Partidos de la temporada en curso publicados sin resultado todavía: afuera.
    df = df[df["home_goals"].notna() & df["away_goals"].notna()].copy()
    for name in INT_COLUMNS:
        df[name] = df[name].astype("Int64")
    for name in COLUMN_SOURCES:
        if name not in STRING_COLUMNS and name not in INT_COLUMNS:
            df[name] = df[name].astype("float64")
    df.attrs["n_long_rows"] = n_long
    return df[OUTPUT_COLUMNS].reset_index(drop=True)


ODDS_BOOKS = ("b365", "b365c", "ps", "psc", "avg")
OUTCOMES = ("home", "draw", "away")


def clean_odds(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Invalida (NaN) los tríos de cuotas 1X2 imposibles.

    Un trío es imposible si alguna cuota es <= 1 (Football-Data usa 0 como
    "sin dato" en algunas filas) o si la suma de probabilidades implícitas de
    una misma casa es < 1: ninguna casa publica un mercado con margen negativo,
    así que es un error de carga. Las cuotas máximas (max_*) no se chequean
    porque combinan casas distintas y ahí una suma < 1 sí es posible.

    Devuelve (df limpio, reporte de filas afectadas).
    """
    df = df.copy()
    affected = []
    for book in ODDS_BOOKS:
        cols = [f"{book}_{o}" for o in OUTCOMES]
        odds = df[cols]
        complete = odds.notna().all(axis=1)
        booksum = (1 / odds).sum(axis=1, min_count=3)
        invalid = complete & ((odds <= 1.0).any(axis=1) | (booksum < 1.0))
        if invalid.any():
            report = df.loc[invalid, ["division", "season", "date", "home_team", "away_team"]].copy()
            report["book"] = book
            report["booksum"] = booksum[invalid].round(3)
            affected.append(report)
            df.loc[invalid, cols] = np.nan
    report = pd.concat(affected, ignore_index=True) if affected else pd.DataFrame()
    return df, report


def validate_rows(df: pd.DataFrame) -> None:
    """Reglas de consistencia que detectan filas corridas o corruptas.

    Si una fila tuviera los campos desplazados (p. ej. por una coma de más), lo
    más probable es que rompa alguna de estas reglas.
    """
    problems = []
    goals_result = np.select(
        [df.home_goals > df.away_goals, df.home_goals < df.away_goals], ["H", "A"], "D"
    )
    if (goals_result != df.result).any():
        problems.append(f"{(goals_result != df.result).sum()} resultados no coinciden con los goles")
    ht = df.dropna(subset=["ht_home_goals", "ht_away_goals"])
    if ((ht.ht_home_goals > ht.home_goals) | (ht.ht_away_goals > ht.away_goals)).any():
        problems.append("goles al entretiempo mayores que los finales")
    for book in ODDS_BOOKS:
        odds = df[[f"{book}_{o}" for o in OUTCOMES]].dropna()
        if odds.empty:
            continue
        booksum = (1 / odds).sum(axis=1)
        # Se asume que clean_odds() ya corrió: acá solo se detectan márgenes
        # absurdamente altos, típicos de columnas corridas.
        if ((odds <= 1.0).any(axis=1) | (booksum < 1.0) | (booksum > 1.25)).any():
            problems.append(f"cuotas {book} imposibles (¿falta correr clean_odds o hay columnas corridas?)")
    if df.duplicated(["date", "home_team", "away_team"]).any():
        problems.append("partidos duplicados")
    if (df.home_team == df.away_team).any():
        problems.append("local == visitante")
    if problems:
        raise ValueError("; ".join(problems))
