"""Estado de los equipos a una fecha cualquiera, para servir predicciones.

Todo se responde con partidos jugados ESTRICTAMENTE antes de la fecha pedida
(misma regla anti-fuga que las features de entrenamiento).

Elo a la fecha D de un equipo:
* El rating solo cambia cuando el equipo juega o al inicio de una temporada
  (regresión a la media / rating de arranque de un recién llegado). El ajuste de
  inicio se calcula con el primer partido de la temporada, usando solo partidos
  anteriores a esa fecha.
* Por eso, si el próximo partido del equipo (fecha >= D) es de una temporada que
  ya empezó en D, su Elo previo a ese partido es exactamente el rating vigente en D.
* Si esa temporada todavía no empezó (receso, o un equipo que aún no debutó en los
  datos), se usa el rating posterior a su último partido, o ninguno si no jugó
  nunca: el ajuste de inicio dependería de resultados posteriores a D.
"""

from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PROCESSED_DIR

# CSV comprimido (no parquet): así la imagen de la API no necesita pyarrow.
SERVING_MATCHES_PATH = PROCESSED_DIR / "serving_matches.csv.gz"


def build_serving_matches(matches: pd.DataFrame, elo_per_match: pd.DataFrame, elo_history: pd.DataFrame) -> pd.DataFrame:
    """Une partidos (E0+E1) con Elo previo y posterior de ambos equipos."""
    cols = ["match_id", "division", "season", "season_start", "date", "home_team", "away_team",
            "home_goals", "away_goals", "result"]
    df = matches[cols].merge(elo_per_match[["match_id", "elo_home", "elo_away"]], on="match_id", how="left")
    post = elo_history[["match_id", "team", "elo_after"]]
    for side in ("home", "away"):
        df = df.merge(post.rename(columns={"team": f"{side}_team", "elo_after": f"elo_{side}_after"}),
                      on=["match_id", f"{side}_team"], how="left")
    df["home_goals"] = df["home_goals"].astype("float64")
    df["away_goals"] = df["away_goals"].astype("float64")
    df["result"] = df["result"].astype("string")
    for col in ("division", "season", "home_team", "away_team"):
        df[col] = df[col].astype(str)
    return df.sort_values(["date", "match_id"]).reset_index(drop=True)


def write_serving_matches(df: pd.DataFrame, path: Path = SERVING_MATCHES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False, float_format="%.6f", compression="gzip")


def read_serving_matches(path: Path = SERVING_MATCHES_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, compression="gzip", keep_default_na=False, na_values=[""],
                     dtype={"home_team": str, "away_team": str, "division": str, "season": str, "match_id": str})
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    df["result"] = df["result"].astype("string")
    return df


@dataclass
class TeamMatch:
    date: pd.Timestamp
    season_start: int
    division: str
    opponent: str
    is_home: bool
    gf: float
    ga: float
    elo_before: float
    elo_after: float
    match_id: str

    @property
    def played(self) -> bool:
        return not (np.isnan(self.gf) or np.isnan(self.ga))

    @property
    def outcome(self) -> str:
        return "G" if self.gf > self.ga else ("E" if self.gf == self.ga else "P")


class MatchStore:
    def __init__(self, serving_matches: pd.DataFrame):
        self.matches = serving_matches.sort_values(["date", "match_id"]).reset_index(drop=True)
        self.by_team: dict[str, list[TeamMatch]] = {}
        for r in self.matches.itertuples(index=False):
            for is_home in (True, False):
                team, opp = (r.home_team, r.away_team) if is_home else (r.away_team, r.home_team)
                self.by_team.setdefault(team, []).append(TeamMatch(
                    date=r.date, season_start=int(r.season_start), division=r.division, opponent=opp,
                    is_home=is_home,
                    gf=r.home_goals if is_home else r.away_goals, ga=r.away_goals if is_home else r.home_goals,
                    elo_before=r.elo_home if is_home else r.elo_away,
                    elo_after=(r.elo_home_after if is_home else r.elo_away_after),
                    match_id=r.match_id))
        self._dates = {t: [m.date for m in ms] for t, ms in self.by_team.items()}
        # Fecha en que se aplica el ajuste de inicio de cada temporada (primer partido, cualquier división).
        self._season_start_date = self.matches.groupby("season_start").date.min().to_dict()

    @classmethod
    def load(cls, path: Path = SERVING_MATCHES_PATH) -> "MatchStore":
        return cls(read_serving_matches(path))

    # ------------------------------------------------------------------ básicos
    def teams(self, division: str | None = None, season_start: int | None = None) -> list[str]:
        df = self.matches
        if division:
            df = df[df.division == division]
        if season_start is not None:
            df = df[df.season_start == season_start]
        return sorted(set(df.home_team) | set(df.away_team))

    def _before(self, team: str, day: pd.Timestamp) -> list[TeamMatch]:
        if team not in self.by_team:
            raise KeyError(team)
        i = bisect_left(self._dates[team], day)
        return [m for m in self.by_team[team][:i] if m.played]

    def elo_as_of(self, team: str, day: pd.Timestamp) -> float | None:
        day = pd.Timestamp(day)
        ms = self.by_team.get(team)
        if not ms:
            raise KeyError(team)
        i = bisect_left(self._dates[team], day)
        prev = next((m for m in reversed(ms[:i]) if m.played), None)
        nxt = ms[i] if i < len(ms) else None
        if nxt is not None and self._season_start_date[nxt.season_start] <= day:
            return float(nxt.elo_before)
        return float(prev.elo_after) if prev is not None else None

    # --------------------------------------------------------------- contexto
    def elo_series(self, team: str, day: pd.Timestamp, seasons_back: int = 2) -> list[dict]:
        """Rating después de cada partido, desde `seasons_back` temporadas antes de `day`."""
        past = self._before(team, pd.Timestamp(day))
        if not past:
            return []
        first_season = past[-1].season_start - seasons_back
        return [{"date": m.date.date().isoformat(), "elo": round(m.elo_after, 1), "opponent": m.opponent,
                 "home": m.is_home, "score": f"{int(m.gf)}-{int(m.ga)}", "division": m.division}
                for m in past if m.season_start >= first_season]

    def recent_form(self, team: str, day: pd.Timestamp, n: int = 5) -> list[dict]:
        past = self._before(team, pd.Timestamp(day))[-n:]
        return [{"date": m.date.date().isoformat(), "opponent": m.opponent, "home": m.is_home,
                 "goals_for": int(m.gf), "goals_against": int(m.ga), "outcome": m.outcome,
                 "division": m.division} for m in reversed(past)]

    def rest(self, team: str, day: pd.Timestamp) -> dict:
        day = pd.Timestamp(day)
        past = self._before(team, day)
        last = past[-1] if past else None
        return {
            "days_since_last_match": int((day - last.date).days) if last else None,
            "matches_last_21_days": sum(1 for m in past if (day - m.date).days <= 21),
            "last_match_date": last.date.date().isoformat() if last else None,
        }

    def head_to_head(self, home: str, away: str, day: pd.Timestamp, n: int = 10) -> dict:
        past = [m for m in self._before(home, pd.Timestamp(day)) if m.opponent == away]
        wins = sum(m.outcome == "G" for m in past)
        draws = sum(m.outcome == "E" for m in past)
        return {
            "matches": len(past), "home_team_wins": wins, "draws": draws, "away_team_wins": len(past) - wins - draws,
            "last": [{"date": m.date.date().isoformat(), "home_team": home if m.is_home else away,
                      "away_team": away if m.is_home else home,
                      "score": f"{int(m.gf)}-{int(m.ga)}" if m.is_home else f"{int(m.ga)}-{int(m.gf)}",
                      "division": m.division} for m in reversed(past[-n:])],
        }

    def standings(self, division: str, season_start: int, day: pd.Timestamp) -> pd.DataFrame:
        """Tabla de la temporada con los partidos jugados antes de `day` (criterios: pts, dif. de gol, goles)."""
        season = self.matches[(self.matches.division == division) & (self.matches.season_start == season_start)]
        teams = sorted(set(season.home_team) | set(season.away_team))
        played = season[(season.date < pd.Timestamp(day)) & season.home_goals.notna()]
        rows = {t: {"team": t, "played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "points": 0} for t in teams}
        for r in played.itertuples(index=False):
            for team, gf, ga in ((r.home_team, r.home_goals, r.away_goals), (r.away_team, r.away_goals, r.home_goals)):
                row = rows[team]
                row["played"] += 1
                row["gf"] += int(gf)
                row["ga"] += int(ga)
                if gf > ga:
                    row["won"] += 1
                    row["points"] += 3
                elif gf == ga:
                    row["drawn"] += 1
                    row["points"] += 1
                else:
                    row["lost"] += 1
        table = pd.DataFrame(rows.values())
        table["gd"] = table.gf - table.ga
        table = table.sort_values(["points", "gd", "gf", "team"], ascending=[False, False, False, True])
        table["position"] = np.arange(1, len(table) + 1)
        return table.reset_index(drop=True)

    def division_in_season(self, team: str, season_start: int) -> str | None:
        """División (E0/E1) del equipo en esa temporada, o None si no jugó ninguna de las dos."""
        if team not in self.by_team:
            raise KeyError(team)
        for m in self.by_team[team]:
            if m.season_start == season_start:
                return m.division
        return None
