"""Descarga de datos crudos.

- Football-Data.co.uk: un CSV por división y temporada (resultados, estadísticas
  y cuotas). Es la fuente base del proyecto.
- Snapshots de Elo (ClubElo vía el dataset de Adam Gábor): solo para comparar
  contra el Elo propio.

Las temporadas terminadas no cambian, así que se descargan una sola vez; la
temporada en curso se vuelve a bajar siempre para incorporar partidos nuevos.

Uso:
    python -m src.data.download            # descarga lo que falte
    python -m src.data.download --force    # vuelve a bajar todo
"""

import argparse
import logging
from datetime import date
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import (
    CLUBELO_SNAPSHOTS_PATH,
    CLUBELO_SNAPSHOTS_URL,
    DIVISIONS,
    FIRST_SEASON_START_YEAR,
    FOOTBALL_DATA_DIR,
    FOOTBALL_DATA_URL,
    season_code,
    season_start_year,
)

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60


def _session() -> requests.Session:
    retry = Retry(total=4, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _fetch(session: requests.Session, url: str, destination: Path) -> int:
    response = session.get(url, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    if not response.content.strip():
        raise ValueError(f"Respuesta vacía desde {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Escritura atómica: si se corta a mitad de camino no queda un CSV truncado
    # que después pase por "ya descargado".
    tmp = destination.with_suffix(destination.suffix + ".part")
    tmp.write_bytes(response.content)
    tmp.replace(destination)
    return len(response.content)


def football_data_path(division: str, start_year: int) -> Path:
    return FOOTBALL_DATA_DIR / f"{division}_{season_code(start_year)}.csv"


def download_football_data(force: bool = False, today: date | None = None) -> list[Path]:
    current = season_start_year(today or date.today())
    session = _session()
    paths = []
    for division in DIVISIONS:
        for start_year in range(FIRST_SEASON_START_YEAR, current + 1):
            path = football_data_path(division, start_year)
            is_current = start_year == current
            if path.exists() and not force and not is_current:
                paths.append(path)
                continue
            url = FOOTBALL_DATA_URL.format(season_code=season_code(start_year), division=division)
            try:
                size = _fetch(session, url, path)
            except requests.HTTPError as err:
                # Al principio de agosto la temporada nueva puede no estar publicada aún.
                if is_current and err.response is not None and err.response.status_code == 404:
                    logger.warning("Temporada en curso todavía no publicada: %s", url)
                    continue
                raise
            logger.info("%s -> %s (%d bytes)", url, path.name, size)
            paths.append(path)
    return paths


def download_clubelo_snapshots(force: bool = False) -> Path:
    if CLUBELO_SNAPSHOTS_PATH.exists() and not force:
        return CLUBELO_SNAPSHOTS_PATH
    size = _fetch(_session(), CLUBELO_SNAPSHOTS_URL, CLUBELO_SNAPSHOTS_PATH)
    logger.info("%s -> %s (%d bytes)", CLUBELO_SNAPSHOTS_URL, CLUBELO_SNAPSHOTS_PATH.name, size)
    return CLUBELO_SNAPSHOTS_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="volver a descargar todo")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    files = download_football_data(force=args.force)
    download_clubelo_snapshots(force=args.force)
    logger.info("Listo: %d archivos de Football-Data + snapshots de Elo", len(files))


if __name__ == "__main__":
    main()
