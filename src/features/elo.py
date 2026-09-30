"""Elo propio, calculado partido a partido sobre Premier League + Championship.

Base del método (verificado):
* Expectativa y actualización de Elo estándar, como en Hvattum y Arntzen (2010,
  International Journal of Forecasting 26(3):460-470):
      gamma_H = 1 / (1 + 10 ** ((R_A - R_H - h) / 400))
      R_H' = R_H + k * (alpha_H - gamma_H)   (alpha = 1 / 0.5 / 0 por victoria / empate / derrota)
* Factor k según diferencia de gol (su variante "ELOg"): k = k0 * (1 + |dif. de gol|) ** lam.
  Los valores del paper son k0 = 10 y lam = 1.
* Ventaja de local h sumada al rating del local dentro de la expectativa, como en
  las World Football Elo Ratings (que usan h = 100).

Extensiones propias (sus parámetros se ajustan con temporadas de entrenamiento,
ver src/features/tune_elo.py):
* Rating inicial: en 2000-01 los equipos de Premier arrancan `initial_gap` puntos
  por encima de los de Championship.
* Equipos nuevos: un club que no jugó la temporada anterior en E0/E1 (viene de
  League One, fuera de los datos) arranca con la media de los equipos de su
  división que sí vienen de la temporada anterior, más `newcomer_offset`.
* Regresión a la media al inicio de cada temporada: el rating se acerca una
  fracción `season_regression` a la media de su división (mercado de pases,
  cambios de plantel).

Anti-fuga: el rating previo a un partido del día D solo depende de partidos
jugados antes de D. Los partidos sin resultado (futuros) reciben rating previo
pero no actualizan nada. La composición de cada división por temporada se toma
del calendario (conocido antes de que empiece la temporada).
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

BASE_RATING = 1500.0


@dataclass(frozen=True)
class EloParams:
    k0: float = 10.0
    lam: float = 1.0
    home_advantage: float = 100.0
    season_regression: float = 0.0
    initial_gap: float = 100.0
    newcomer_offset: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def expected_home(rating_home, rating_away, home_advantage: float):
    """Puntaje esperado del local (victoria = 1, empate = 0,5)."""
    return 1.0 / (1.0 + 10.0 ** ((np.asarray(rating_away) - np.asarray(rating_home) - home_advantage) / 400.0))


def compute_elo(matches: pd.DataFrame, params: EloParams = EloParams(),
                top_division: str = "E0") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula el Elo previo a cada partido.

    `matches` necesita: match_id, date, season_start, division, home_team,
    away_team, home_goals, away_goals (NaN = partido todavía no jugado).
    `top_division`: la división que arranca `initial_gap` puntos arriba (E0 en Inglaterra; en la
    replicación en otras ligas, su primera división).

    Devuelve:
      per_match: match_id, elo_home, elo_away, elo_expected_home (con ventaja de local).
      history:   una fila por equipo y partido jugado con el rating posterior
                 (para graficar la evolución).
    """
    df = matches.sort_values(["date", "match_id"]).reset_index(drop=True)
    played = df["home_goals"].notna().to_numpy() & df["away_goals"].notna().to_numpy()

    # Composición de cada división por temporada (del calendario).
    members: dict[tuple[int, str], set[str]] = {}
    for (season, division), g in df.groupby(["season_start", "division"]):
        members[(int(season), division)] = set(g["home_team"]) | set(g["away_team"])
    team_division = {
        (season, team): division for (season, division), teams in members.items() for team in teams
    }

    ratings: dict[str, float] = {}
    last_season_played: dict[str, int] = {}
    current_season: int | None = None

    def start_season(season: int) -> None:
        divisions = [d for (s, d) in members if s == season]
        teams_by_div = {d: members[(season, d)] for d in divisions}
        if not ratings:  # primera temporada de los datos
            for division, teams in teams_by_div.items():
                start = BASE_RATING + (params.initial_gap if division == top_division else 0.0)
                for team in teams:
                    ratings[team] = start
            return
        for division, teams in teams_by_div.items():
            carried = [t for t in teams if last_season_played.get(t) == season - 1]
            new = [t for t in teams if t not in carried]
            if carried:
                reference = float(np.mean([ratings[t] for t in carried]))
            else:
                reference = BASE_RATING
            for team in new:
                ratings[team] = reference + params.newcomer_offset
            division_mean = float(np.mean([ratings[t] for t in teams]))
            for team in teams:
                ratings[team] += params.season_regression * (division_mean - ratings[team])

    n = len(df)
    elo_home = np.empty(n)
    elo_away = np.empty(n)
    history = []
    seasons = df["season_start"].to_numpy()
    homes = df["home_team"].to_numpy()
    aways = df["away_team"].to_numpy()
    hg = df["home_goals"].to_numpy(dtype=float, na_value=np.nan)
    ag = df["away_goals"].to_numpy(dtype=float, na_value=np.nan)
    dates = df["date"].to_numpy()
    ids = df["match_id"].to_numpy()

    for i in range(n):
        season = int(seasons[i])
        if season != current_season:
            if current_season is not None and season < current_season:
                raise ValueError("Los partidos deben estar ordenados por temporada")
            start_season(season)
            current_season = season
        home, away = homes[i], aways[i]
        r_h, r_a = ratings[home], ratings[away]
        elo_home[i], elo_away[i] = r_h, r_a
        if not played[i]:
            continue
        gamma = 1.0 / (1.0 + 10.0 ** ((r_a - r_h - params.home_advantage) / 400.0))
        alpha = 1.0 if hg[i] > ag[i] else (0.5 if hg[i] == ag[i] else 0.0)
        k = params.k0 * (1.0 + abs(hg[i] - ag[i])) ** params.lam
        delta = k * (alpha - gamma)
        ratings[home] = r_h + delta
        ratings[away] = r_a - delta
        last_season_played[home] = last_season_played[away] = season
        history.append((ids[i], dates[i], season, team_division[(season, home)], home, ratings[home]))
        history.append((ids[i], dates[i], season, team_division[(season, away)], away, ratings[away]))

    per_match = pd.DataFrame({
        "match_id": ids,
        "elo_home": elo_home,
        "elo_away": elo_away,
    })
    per_match["elo_expected_home"] = expected_home(elo_home, elo_away, params.home_advantage)
    history = pd.DataFrame(history, columns=["match_id", "date", "season_start", "division", "team", "elo_after"])
    return per_match, history
