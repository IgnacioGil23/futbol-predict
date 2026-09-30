"""Rutas y constantes compartidas por todo el proyecto."""

from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
FOOTBALL_DATA_DIR = RAW_DIR / "football_data"
PROCESSED_DIR = DATA_DIR / "processed"

# Football-Data.co.uk publica un CSV por división y temporada:
#   https://www.football-data.co.uk/mmz4281/<código de temporada>/<división>.csv
# donde el código de temporada es "0001" para 2000/01, "2627" para 2026/27, etc.
FOOTBALL_DATA_URL = "https://www.football-data.co.uk/mmz4281/{season_code}/{division}.csv"

# E0 = Premier League (el objeto de estudio).
# E1 = Championship: se descarga solo para darle historial de Elo a los equipos
# ascendidos (sin esto, un recién ascendido arrancaría "de cero" en la Premier).
PREMIER_LEAGUE = "E0"
CHAMPIONSHIP = "E1"
DIVISIONS = (PREMIER_LEAGUE, CHAMPIONSHIP)

FIRST_SEASON_START_YEAR = 2000

# Tabla de ratings de ClubElo redistribuida por el dataset "Club Football Match Data"
# (Adam Gábor). Se usa solo como Elo de comparación: la API pública de ClubElo
# dejó de estar disponible y, desde el 15/06/2025, los snapshots de esa tabla son
# una continuación "provisional" calculada por el autor del dataset.
CLUBELO_SNAPSHOTS_URL = (
    "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data/main/data/EloRatings.csv"
)
CLUBELO_SNAPSHOTS_PATH = RAW_DIR / "EloRatings.csv"
CLUBELO_PROVISIONAL_FROM = date(2025, 6, 15)


def season_start_year(day: date) -> int:
    """Año de inicio de la temporada en curso en la fecha `day`.

    Las temporadas de la Premier arrancan en agosto; julio se considera todavía
    receso. Solo se usa para saber hasta qué temporada descargar: la temporada
    de cada partido sale del archivo del que se leyó, nunca de su fecha (la
    temporada 2019/20 terminó el 26/07/2020, así que una regla por mes fallaría).
    """
    return day.year if day.month >= 8 else day.year - 1


def season_code(start_year: int) -> str:
    """2003 -> "0304" (formato de URL de Football-Data)."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_label(start_year: int) -> str:
    """2003 -> "2003-04"."""
    return f"{start_year}-{(start_year + 1) % 100:02d}"
