"""Esquemas de respuesta de la API (documentados automáticamente en /docs)."""

from datetime import date

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str
    model_version: str
    model_trained_at: str
    last_match_in_data: date


class TeamsOut(BaseModel):
    season: int
    teams: list[str]
    all_teams: list[str] = Field(description="Todos los equipos con partidos de Premier desde 2000-01")


class EloBlock(BaseModel):
    home: float
    away: float
    diff: float


class ExpectedGoals(BaseModel):
    home: float
    away: float


class Probabilities(BaseModel):
    home: float
    draw: float
    away: float


class ScoreProb(BaseModel):
    home_goals: int
    away_goals: int
    probability: float


class Context(BaseModel):
    form_home: list[dict]
    form_away: list[dict]
    rest_home: dict
    rest_away: dict
    head_to_head: dict
    elo_history_home: list[dict]
    elo_history_away: list[dict]


class PredictionOut(BaseModel):
    model_version: str
    home_team: str
    away_team: str
    date: date
    elo: EloBlock
    expected_goals: ExpectedGoals
    probabilities: Probabilities
    score_grid: list[list[float]] = Field(description="[i][j] = P(local i goles, visitante j goles), 0 a 6")
    score_grid_mass: float = Field(description="Probabilidad total cubierta por la grilla 0-6")
    top_scores: list[ScoreProb]
    context: Context
    warnings: list[str]
