"""Calendario completo de la temporada (openfootball/england, dominio público).

Fuente: https://github.com/openfootball/england ("dedicated to the public domain.
Use as you please with no restrictions whatsoever"). Un archivo de texto por
temporada con las 38 jornadas, día, horario y resultado cuando ya se jugó:

    ▪ Matchday 6
      Sat Oct 10
        12:30  Arsenal FC              v Leeds United FC
        15:00  Sunderland AFC          v Brighton & Hove Albion FC
               Chelsea FC              v AFC Bournemouth        <- mismo horario que la línea anterior

Los horarios se publican como hora local de cada liga (Inglaterra: los típicos 12:30, 15:00, 17:30) y se
convierten a hora de Argentina con las zonas horarias oficiales, que contemplan los cambios de horario.

Otras ligas (src/data/leagues.py): mismo formato en openfootball/espana, italy, deutschland y europe/france. Sus
nombres se traducen a los de Football-Data con una tabla (configs/leagues/team_names.json) que se deduce de los
partidos ya jugados (`infer_names`: misma fecha y mismo resultado).
"""

import logging
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from src.config import season_label
from src.data.teams import DISPLAY_NAMES, canonical_team

logger = logging.getLogger(__name__)

SCHEDULE_URL = "https://raw.githubusercontent.com/openfootball/england/master/{season}/1-premierleague.txt"
UK = ZoneInfo("Europe/London")
ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")

# Nombre en openfootball -> nombre canónico (Football-Data). Los que no figuran se
# resuelven quitando "FC"/"AFC" y buscando el nombre para mostrar (ver `to_canonical`).
OPENFOOTBALL_NAMES = {
    "AFC Bournemouth": "Bournemouth",
    "Brighton & Hove Albion FC": "Brighton",
    "Manchester City FC": "Man City",
    "Manchester United FC": "Man United",
    "Nottingham Forest FC": "Nott'm Forest",
    "Tottenham Hotspur FC": "Tottenham",
    "Wolverhampton Wanderers FC": "Wolves",
    "West Bromwich Albion FC": "West Brom",
    "Queens Park Rangers FC": "QPR",
    "Sheffield Wednesday FC": "Sheffield Weds",
}
_FROM_DISPLAY = {v: k for k, v in DISPLAY_NAMES.items()}

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
RE_MATCHDAY = re.compile(r"Matchday\s+(\d+)")
RE_DATE = re.compile(r"^\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$")
RE_MATCH = re.compile(
    r"^\s+(?:(\d{1,2}:\d{2})\s+)?(?P<home>\S.*?)\s+v\s+(?P<away>\S.*?)"
    r"(?:\s+(?P<hg>\d+)-(?P<ag>\d+)(?:\s+\(\d+-\d+\))?)?\s*$"
)


def to_canonical(name: str) -> str:
    name = name.strip()
    if name in OPENFOOTBALL_NAMES:
        return OPENFOOTBALL_NAMES[name]
    short = re.sub(r"^AFC\s+|\s+A?FC$", "", name)
    return canonical_team(_FROM_DISPLAY.get(short, _FROM_DISPLAY.get(name, short)))


def parse_schedule(text: str, season_start: int, names: dict | None = None, tz: ZoneInfo = UK) -> pd.DataFrame:
    """Texto de openfootball -> un partido por fila (jornada, fecha, horarios, equipos, resultado si lo hay).

    `names`: tabla nombre de openfootball -> Football-Data de otra liga (los que no figuran quedan como vienen);
    sin tabla, las reglas de la Premier (`to_canonical`). `tz`: zona horaria de los horarios publicados.
    """
    canonical = to_canonical if names is None else (lambda raw: names.get(raw.strip(), raw.strip()))
    rows, matchday, day, kickoff = [], None, None, None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "=")):
            continue
        if m := RE_MATCHDAY.search(line):
            matchday, day, kickoff = int(m.group(1)), None, None
            continue
        if m := RE_DATE.match(line):
            month, dom = MONTHS[m.group(1)], int(m.group(2))
            year = int(m.group(3)) if m.group(3) else (season_start if month >= 7 else season_start + 1)
            day, kickoff = date(year, month, dom), None
            continue
        if (m := RE_MATCH.match(line)) and day is not None and matchday is not None:
            kickoff = m.group(1) or kickoff
            rows.append({
                "matchday": matchday, "date": pd.Timestamp(day),
                "time_uk": kickoff,
                "home_team": canonical(m.group("home")), "away_team": canonical(m.group("away")),
                "home_raw": m.group("home").strip(), "away_raw": m.group("away").strip(),
                "home_goals": float(m.group("hg")) if m.group("hg") else float("nan"),
                "away_goals": float(m.group("ag")) if m.group("ag") else float("nan"),
            })
            continue
        logger.warning("Línea del calendario no reconocida: %r", line)
    df = pd.DataFrame(rows, columns=["matchday", "date", "time_uk", "home_team", "away_team", "home_raw", "away_raw",
                                     "home_goals", "away_goals"])
    # Columnas de texto como object: así un horario faltante queda None (con el tipo str de pandas sería NaN, que no
    # es JSON válido).
    df["time_uk"] = pd.Series([r["time_uk"] for r in rows], dtype=object, index=df.index)
    df["kickoff_ar"] = pd.Series([to_argentina(d, t, tz) for d, t in zip(df["date"], df["time_uk"])], dtype=object,
                                 index=df.index)
    df["played"] = df["home_goals"].notna()
    return df


def to_argentina(day: pd.Timestamp, time_uk: str | None, tz: ZoneInfo = UK) -> str | None:
    """Fecha y hora local de la liga (`tz`) -> 'AAAA-MM-DD HH:MM' en hora de Argentina (None si no hay horario)."""
    if not isinstance(time_uk, str) or not time_uk:      # sin horario (None, o NaN en columnas de texto)
        return None
    hh, mm = map(int, time_uk.split(":"))
    local = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
    return local.astimezone(ARGENTINA).strftime("%Y-%m-%d %H:%M")


def schedule_url(season_start: int, league: str = "ENG") -> str:
    from src.data.leagues import PRODUCT_LEAGUES
    return PRODUCT_LEAGUES[league]["schedule_url"].format(season=season_label(season_start))


def fetch_schedule(season_start: int, timeout: int = 60, league: str = "ENG", names: dict | None = None) -> pd.DataFrame:
    """Calendario de `league` (por defecto la Premier). En otras ligas, `names` traduce los nombres (ver
    `src.data.team_names.load_names`)."""
    from src.data.leagues import PRODUCT_LEAGUES
    response = requests.get(schedule_url(season_start, league), timeout=timeout)
    response.raise_for_status()
    tz = ZoneInfo(PRODUCT_LEAGUES[league]["timezone"])
    if league != "ENG" and names is None:
        names = {}
    return parse_schedule(response.content.decode("utf-8"), season_start, names=names, tz=tz)


def infer_names(schedule: pd.DataFrame, results: pd.DataFrame, max_days: int = 1) -> dict[str, str]:
    """Nombre de openfootball -> Football-Data, deducido de los partidos jugados: misma fecha (±`max_days`) y mismo
    resultado. Solo cuentan los partidos con un único candidato; cada nombre se queda con el más votado, y si dos
    nombres eligen el mismo equipo, ninguno se traduce (ambigüedad)."""
    votes: dict[str, dict[str, int]] = {}
    played = schedule[schedule["home_goals"].notna()]
    res = results[results["home_goals"].notna()]
    for r in played.itertuples(index=False):
        near = res[((res["date"] - r.date).abs() <= pd.Timedelta(days=max_days))
                   & (res["home_goals"] == r.home_goals) & (res["away_goals"] == r.away_goals)]
        if len(near) != 1:
            continue
        fd = near.iloc[0]
        for raw, name in ((r.home_raw, fd["home_team"]), (r.away_raw, fd["away_team"])):
            votes.setdefault(raw, {}).setdefault(name, 0)
            votes[raw][name] += 1
    best = {}
    for raw, v in votes.items():
        ranked = sorted(v.items(), key=lambda kv: -kv[1])
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            best[raw] = ranked[0][0]
    taken = pd.Series(best).value_counts()
    return {raw: name for raw, name in best.items() if taken[name] == 1}


def check_against_results(schedule: pd.DataFrame, results: pd.DataFrame) -> dict:
    """Cruza los partidos jugados del calendario con los resultados de Football-Data (control de calidad)."""
    played = schedule[schedule.played]
    merged = played.merge(results[["home_team", "away_team", "home_goals", "away_goals"]],
                          on=["home_team", "away_team"], how="left", suffixes=("", "_fd"), indicator=True)
    missing = merged[merged._merge == "left_only"]
    diff = merged[(merged._merge == "both") & ((merged.home_goals != merged.home_goals_fd)
                                                | (merged.away_goals != merged.away_goals_fd))]
    return {
        "played_in_schedule": int(len(played)),
        "not_found_in_football_data": [f"{r.home_team} v {r.away_team}" for r in missing.itertuples()],
        "score_mismatches": [f"{r.home_team} v {r.away_team}: {int(r.home_goals)}-{int(r.away_goals)} vs "
                             f"{int(r.home_goals_fd)}-{int(r.away_goals_fd)}" for r in diff.itertuples()],
    }
