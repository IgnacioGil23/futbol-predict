"""Validaciones estructurales de una temporada de liga (formato todos contra todos, ida y vuelta)."""

from dataclasses import dataclass

import pandas as pd

# Equipos por división. La Premier tiene 20 desde 1995/96 y la Championship 24
# desde su creación como First Division en 1995/96 (ambos formatos estables en
# todo el rango 2000-2026 del proyecto).
TEAMS_PER_DIVISION = {"E0": 20, "E1": 24}


@dataclass(frozen=True)
class SeasonCheck:
    division: str
    season: str
    matches: int
    expected_matches: int
    teams: int
    complete: bool
    problems: tuple[str, ...]


def check_season(season_df: pd.DataFrame, is_current: bool) -> SeasonCheck:
    """Chequea una temporada; en la temporada en curso solo aplica reglas parciales."""
    division = season_df["division"].iloc[0]
    season = season_df["season"].iloc[0]
    n_teams_expected = TEAMS_PER_DIVISION[division]
    expected = n_teams_expected * (n_teams_expected - 1)
    teams = pd.unique(season_df[["home_team", "away_team"]].to_numpy().ravel())
    problems = []

    # Cada par ordenado (local, visitante) se juega a lo sumo una vez.
    pairs = season_df.groupby(["home_team", "away_team"]).size()
    if (pairs > 1).any():
        problems.append(f"{int((pairs > 1).sum())} cruces local-visitante repetidos")
    if len(teams) > n_teams_expected:
        problems.append(f"{len(teams)} equipos (> {n_teams_expected})")

    if not is_current:
        if len(season_df) != expected:
            problems.append(f"{len(season_df)} partidos (se esperaban {expected})")
        if len(teams) != n_teams_expected:
            problems.append(f"{len(teams)} equipos (se esperaban {n_teams_expected})")
        home = season_df["home_team"].value_counts()
        away = season_df["away_team"].value_counts()
        per_side = n_teams_expected - 1
        if (home != per_side).any() or (away != per_side).any():
            problems.append(f"no todos los equipos jugaron {per_side} de local y {per_side} de visitante")

    return SeasonCheck(
        division=division,
        season=season,
        matches=len(season_df),
        expected_matches=expected,
        teams=len(teams),
        complete=len(season_df) == expected,
        problems=tuple(problems),
    )
