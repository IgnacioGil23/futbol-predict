"""Todo lo que la exportación de la web necesita saber de una liga.

La Premier (ENG) usa los artefactos de siempre (models/production, models/elo, data/processed/matches.parquet) y se
publica en la raíz de web/public/data; las otras ligas usan los suyos (src/serving/league_models.py) y se publican en
web/public/data/leagues/<liga>/.
"""

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT
from src.data.fixtures import fetch_fixtures
from src.data.leagues import PRODUCT_LEAGUES, matches_path
from src.data.load import MATCHES_PATH
from src.data.schedule import fetch_schedule, schedule_url
from src.data.team_names import league_display_name, league_short_name, load_names
from src.data.teams import display_name
from src.export.badges import badge
from src.export.stadiums import stadium
from src.features.build import FEATURES_PATH, load_elo_params
from src.features.elo import EloParams
from src.models.experiments import prepare
from src.serving.league_state import load_league_params, model_path, serving_path
from src.serving.predictor import EloPoissonPredictor
from src.serving.production import ELO_MODEL_PATH, FIRST_TRAIN_SEASON
from src.serving.store import MatchStore

SEASON_EVAL_DIR = PROJECT_ROOT / "reports" / "season"


@dataclass
class LeagueContext:
    code: str
    store: MatchStore
    predictor: EloPoissonPredictor          # modelo publicado (Elo de cuotas)
    sim_predictor: EloPoissonPredictor      # simulación de la temporada (Elo de resultados)
    first_train: int
    meta: dict = field(default_factory=dict)

    @property
    def league(self) -> dict:
        return PRODUCT_LEAGUES[self.code]

    @property
    def top(self) -> str:
        return self.league["top"]

    @property
    def is_premier(self) -> bool:
        return self.code == "ENG"

    def out_dir(self, root: Path) -> Path:
        return root if self.is_premier else root / "leagues" / self.code

    def name_of(self, team: str) -> str:
        return display_name(team) if self.is_premier else league_display_name(team, self.code)

    def badge_of(self, team: str) -> dict:
        if self.is_premier:
            return badge(team)
        b = badge(team)                       # sin escudo: iniciales
        return {"badge": None, "short": league_short_name(team, self.code) or b["short"]}

    def stadium_of(self, team: str) -> dict:
        return stadium(team) if self.is_premier else {"stadium": None}

    def schedule(self, season: int) -> pd.DataFrame:
        if self.is_premier:
            return fetch_schedule(season)
        return fetch_schedule(season, league=self.code, names=load_names(self.code))

    def schedule_url(self, season: int) -> str:
        return schedule_url(season, self.code)

    def fixtures(self) -> pd.DataFrame:
        return fetch_fixtures(division=self.top)

    @property
    def sim_elo_params(self) -> EloParams:
        return load_elo_params() if self.is_premier else load_league_params(self.code)[1]

    @cached_property
    def matches(self) -> pd.DataFrame:
        """Partidos de las dos divisiones con todas las columnas de Football-Data (estadísticas)."""
        return pd.read_parquet(MATCHES_PATH if self.is_premier else matches_path(self.code))

    @cached_property
    def features(self) -> pd.DataFrame:
        from src.serving.league_models import features_path, league_features
        if self.is_premier:
            return prepare(pd.read_parquet(FEATURES_PATH))
        path = features_path(self.code)
        return prepare(pd.read_parquet(path)) if path.exists() else league_features(self.code, self.matches)

    def season_reports(self) -> list[Path]:
        pattern = "evaluacion_*.json" if self.is_premier else f"{self.code}_evaluacion_*.json"
        return sorted(SEASON_EVAL_DIR.glob(pattern))


def premier_context() -> LeagueContext:
    return LeagueContext("ENG", MatchStore.load(), EloPoissonPredictor.load(), EloPoissonPredictor.load(ELO_MODEL_PATH),
                         FIRST_TRAIN_SEASON)


def league_context(code: str) -> LeagueContext:
    from src.models.odds_elo_eval import FIRST_TRAIN
    return LeagueContext(code, MatchStore.load(serving_path(code)), EloPoissonPredictor.load(model_path(code)),
                         EloPoissonPredictor.load(model_path(code, "elo")), FIRST_TRAIN[code])


def leagues_index(contexts: list[LeagueContext]) -> list[dict]:
    """leagues.json: las ligas publicadas y dónde están sus datos."""
    return [{"code": c.code, "slug": c.league["slug"], "competition": c.league["competition"],
             "country": c.league["name"], "second": c.league["second_name"],
             "top_division": c.top, "second_division": c.league["second"],
             "path": "" if c.is_premier else f"leagues/{c.code}/",
             "relegation": c.league["relegation"], "playoff": c.league["playoff"],
             "head_to_head": c.league["head_to_head"], "model_version": c.predictor.version}
            for c in contexts]

