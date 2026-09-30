// Tipos de los JSON que exporta `python -m src.export.site`.
import type { ModelParams } from './model'

export type Outcome = 'H' | 'D' | 'A'
export type FormOutcome = 'G' | 'E' | 'P'

export interface Metrics { log_loss: number; rps: number; brier?: number; accuracy: number; ece?: number; n?: number }

export interface ModelMeta {
  model: string
  features: string[]
  trained_on: { seasons: string; matches: number }
  trained_at: string
  elo_params: Record<string, number>
  test_metrics: { seasons: string; model: Metrics; bet365_pre_closing: Metrics; pinnacle_closing: Metrics }
}

export interface ModelFile { params: ModelParams; max_goals: number; meta: ModelMeta }

export interface FormMatch {
  date: string; opponent: string; home: boolean; goals_for: number; goals_against: number
  outcome: FormOutcome; division: string
}
export interface Rest { days_since_last_match: number | null; matches_last_21_days: number; last_match_date: string | null }
export interface TableRow {
  team: string; played: number; won: number; drawn: number; lost: number
  gf: number; ga: number; gd: number; points: number; position: number
}
export interface TeamState {
  team: string; name: string; slug: string; elo: number
  form: FormMatch[]; rest: Rest; table: TableRow | null
}
export interface StateFile { as_of: string; season: string; teams: TeamState[]; standings: TableRow[] }

export interface H2H {
  matches: number; home_team_wins: number; draws: number; away_team_wins: number
  last: { date: string; home_team: string; away_team: string; score: string; division: string }[]
}

export interface TeamIndexItem { team: string; name: string; slug: string; premier_seasons: number; last_premier_season: string }
export interface TeamSeason {
  season: string; played: number; points: number; position: number
  goals_for_per_game: number; goals_against_per_game: number; league_goals_per_team_game: number
  attack_vs_league_pct: number; defence_vs_league_pct: number
}
export interface EloPoint { date: string; elo: number; division: string; opponent: string; home: boolean; score: string }
export interface TeamFile { team: string; name: string; slug: string; seasons: TeamSeason[]; elo: EloPoint[] }

export interface Probabilities { home: number; draw: number; away: number }

export interface UpcomingMatch {
  date: string; kickoff_ar: string | null
  home_team: string; away_team: string; home_name: string; away_name: string; home_slug: string; away_slug: string
  elo: { home: number; away: number }
  expected_goals: { home: number; away: number }
  probabilities: Probabilities
  score_grid: number[][]
  top_scores: { home_goals: number; away_goals: number; probability: number }[]
  market: Probabilities | null
  context: { form_home: FormMatch[]; form_away: FormMatch[]; rest_home: Rest; rest_away: Rest; head_to_head: H2H }
}
export interface UpcomingMatchday { matchday: number; from: string; to: string; matches: UpcomingMatch[] }
export interface UpcomingFile {
  generated_for: string; season: string; model_version: string; timezone: string
  sources: { schedule: string; odds: string }
  quality: { played_in_schedule?: number; not_found_in_football_data?: string[]; score_mismatches?: string[]; schedule_error?: string }
  matchdays: UpcomingMatchday[]
}

export interface ReviewSeasonSummary {
  season: string; matches: number; compared_matches: number
  model: Metrics; market: Metrics
}
export interface ReviewMatch {
  id: string; date: string; home_team: string; away_team: string; home_name: string; away_name: string
  score: [number, number]; result: Outcome; elo: [number, number]; expected_goals: [number, number]
  p: [number, number, number]; market: [number, number, number] | null; p_actual: number
}
export interface ReviewSeasonFile { season: string; matches: ReviewMatch[] }

export interface CalibrationBin { outcome: Outcome; bin: number; n: number; mean_predicted: number; observed: number; ci_low: number; ci_high: number }
export interface CalibrationFile { seasons: string; matches: number; model: CalibrationBin[]; market: CalibrationBin[] }

export interface HABlock {
  matches: number; home_win: number; draw: number; away_win: number; goal_diff: number; goal_diff_ci: [number, number]
}
export interface HomeAdvantageFile {
  eras: (HABlock & { era: string; from: string; to: string })[]
  seasons: (HABlock & { season: string })[]
  overall_home_win: number
}

export interface MetaFile {
  generated_at: string; as_of: string; last_match_in_data: string; upcoming_matches: number; model_version: string
  model: ModelMeta
  sources: { name: string; url: string; use: string }[]
}

/** Respuesta de la API /predict (para fechas históricas). */
export interface ApiPrediction {
  home_team: string; away_team: string; date: string
  elo: { home: number; away: number; diff: number }
  expected_goals: { home: number; away: number }
  probabilities: Probabilities
  score_grid: number[][]
  context: {
    form_home: FormMatch[]; form_away: FormMatch[]; rest_home: Rest; rest_away: Rest; head_to_head: H2H
    elo_history_home: EloPoint[]; elo_history_away: EloPoint[]
  }
  warnings: string[]
}
