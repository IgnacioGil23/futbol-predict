"""API de predicción de partidos: Premier League, LaLiga, Serie A, Bundesliga y Ligue 1.

Cada endpoint acepta `league` (ENG, ESP, ITA, GER o FRA; por defecto ENG, la Premier): cada liga tiene su modelo y su
estado (src/serving/league_state.py), y los equipos se buscan solo dentro de esa liga.

Uso local:
    uvicorn src.api.main:app --reload

Endpoints:
    GET /                                    redirige a /docs (documentación interactiva)
    GET /health                              estado, versión del modelo, último partido en los datos
    GET /teams?season=2026&league=ESP        equipos de la primera división en una temporada
    GET /predict?home=&away=&date=&league=   grilla de marcadores, 1X2 y contexto pre-partido
    GET /model?league=                       ficha del modelo (datos, métricas en test)
"""

import os
from contextlib import asynccontextmanager
from datetime import date as Date
from datetime import timedelta
from functools import lru_cache

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from src.api.schemas import Context, EloBlock, ExpectedGoals, Health, PredictionOut, Probabilities, ScoreProb, TeamsOut
from src.config import season_start_year
from src.league_registry import PRODUCT_LEAGUES
from src.serving.league_paths import model_path, serving_path
from src.serving.predictor import EloPoissonPredictor
from src.serving.store import MatchStore

# Antes de 2005-06 el Elo propio todavía está en su período de arranque (burn-in).
MIN_DATE = Date(2005, 8, 1)
MAX_DAYS_AHEAD = 60
GRID_SIZE = 7  # la grilla que se devuelve va de 0 a 6 goles (el resto de la masa se informa aparte)


LEAGUE_QUERY = Query("ENG", description="Liga: ENG (Premier), ESP (LaLiga), ITA (Serie A), GER (Bundesliga), FRA (Ligue 1)")


def check_league(league: str) -> str:
    if league not in PRODUCT_LEAGUES:
        raise HTTPException(404, f"Liga desconocida: {league} (válidas: {', '.join(PRODUCT_LEAGUES)})")
    return league


@lru_cache(maxsize=len(PRODUCT_LEAGUES))
def _store(league: str) -> MatchStore:
    return MatchStore.load() if league == "ENG" else MatchStore.load(serving_path(league))


@lru_cache(maxsize=len(PRODUCT_LEAGUES))
def _predictor(league: str) -> EloPoissonPredictor:
    return EloPoissonPredictor.load() if league == "ENG" else EloPoissonPredictor.load(model_path(league))


def _loaded(league: str) -> str:
    """Liga válida y con sus datos en la imagen (si faltan, 503: el resto de las ligas sigue respondiendo)."""
    check_league(league)
    if league not in available_leagues():
        raise HTTPException(503, f"La liga {league} no está disponible en este momento")
    return league


def get_store(league: str = LEAGUE_QUERY) -> MatchStore:
    return _store(_loaded(league))


def get_predictor(league: str = LEAGUE_QUERY) -> EloPoissonPredictor:
    return _predictor(_loaded(league))


def available_leagues() -> list[str]:
    return [c for c in PRODUCT_LEAGUES if c == "ENG" or (serving_path(c).exists() and model_path(c).exists())]


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Carga datos y modelos al arrancar: uvicorn no acepta conexiones hasta terminar,
    # así que Cloud Run nunca envía pedidos a una instancia a medio cargar.
    for league in available_leagues():
        _store(league)
        _predictor(league)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Fútbol europeo · predicción de marcadores",
    description="Dos regresiones de Poisson sobre la diferencia de Elo. Datos: Football-Data.co.uk.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def last_data_date(store: MatchStore) -> Date:
    played = store.matches[store.matches.home_goals.notna()]
    return played.date.max().date()


@app.get("/", include_in_schema=False)
def root():
    """La raíz no tiene contenido propio: lleva a la documentación interactiva."""
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=Health)
def health(store: MatchStore = Depends(get_store), predictor: EloPoissonPredictor = Depends(get_predictor)):
    return Health(status="ok", model_version=predictor.version, model_trained_at=predictor.meta["trained_at"],
                  last_match_in_data=last_data_date(store))


@app.get("/teams", response_model=TeamsOut)
def teams(season: int | None = Query(None, description="Año de inicio de temporada, p. ej. 2026 para 2026-27"),
          league: str = LEAGUE_QUERY, store: MatchStore = Depends(get_store)):
    season = season if season is not None else season_start_year(Date.today())
    info = PRODUCT_LEAGUES[check_league(league)]
    names = store.teams(info["top"], season)
    if not names:
        raise HTTPException(404, f"No hay partidos de {info['competition']} para la temporada {season}")
    return TeamsOut(season=season, teams=names, all_teams=store.teams(info["top"]))


@app.get("/model")
def model_card(predictor: EloPoissonPredictor = Depends(get_predictor)):
    return predictor.meta


@lru_cache(maxsize=4096)
def _predict_cached(home: str, away: str, day: Date, league: str = "ENG") -> PredictionOut:
    store, predictor = get_store(league), get_predictor(league)
    info = PRODUCT_LEAGUES[league]
    ts = pd.Timestamp(day)
    warnings = []
    elos = {}
    season = season_start_year(day)
    for team in (home, away):
        try:
            division = store.division_in_season(team, season)
        except KeyError:
            raise HTTPException(404, f"Equipo desconocido: {team}") from None
        if division is None:
            raise HTTPException(422, f"{team} no jugaba en {info['competition']} ni {info['second_name']} en "
                                     f"{season}-{(season + 1) % 100:02d}: no hay un Elo actualizado para esa fecha")
        elo = store.rating_as_of(team, ts, predictor.rating)
        if elo is None:
            raise HTTPException(422, f"{team} no tiene partidos antes de {day.isoformat()}")
        elos[team] = elo
        if division != info["top"]:
            warnings.append(f"{team} jugaba en {info['second_name']} en esa temporada: su Elo viene de esa división.")
    if day > last_data_date(store):
        warnings.append("Fecha posterior al último partido en los datos: se usa el Elo más reciente disponible.")

    pred = predictor.predict(elos[home], elos[away])
    grid = pred.matrix[:GRID_SIZE, :GRID_SIZE]
    return PredictionOut(
        model_version=predictor.version,
        home_team=home, away_team=away, date=day,
        elo=EloBlock(home=round(elos[home], 1), away=round(elos[away], 1), diff=round(elos[home] - elos[away], 1)),
        expected_goals=ExpectedGoals(home=round(pred.lam, 3), away=round(pred.mu, 3)),
        probabilities=Probabilities(home=float(pred.probs[0]), draw=float(pred.probs[1]), away=float(pred.probs[2])),
        score_grid=[[round(float(p), 5) for p in row] for row in grid],
        score_grid_mass=round(float(grid.sum()), 5),
        top_scores=[ScoreProb(**s) for s in pred.top_scores(6)],
        context=Context(
            form_home=store.recent_form(home, ts), form_away=store.recent_form(away, ts),
            rest_home=store.rest(home, ts), rest_away=store.rest(away, ts),
            head_to_head=store.head_to_head(home, away, ts),
            elo_history_home=store.elo_series(home, ts, kind=predictor.rating),
            elo_history_away=store.elo_series(away, ts, kind=predictor.rating),
        ),
        warnings=warnings,
    )


@app.get("/predict", response_model=PredictionOut)
def predict(home: str = Query(..., description="Equipo local (nombre de Football-Data, p. ej. 'Man City')"),
            away: str = Query(..., description="Equipo visitante"),
            date: Date | None = Query(None, description="Fecha del partido (AAAA-MM-DD). Por defecto, hoy."),
            league: str = LEAGUE_QUERY):
    league = check_league(league)
    day = date or Date.today()
    if home == away:
        raise HTTPException(422, "El local y el visitante deben ser distintos")
    if day < MIN_DATE:
        raise HTTPException(422, f"La fecha debe ser posterior a {MIN_DATE.isoformat()} (antes, el Elo está en arranque)")
    if day > Date.today() + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(422, f"No se predicen partidos a más de {MAX_DAYS_AHEAD} días")
    return _predict_cached(home, away, day, league)
