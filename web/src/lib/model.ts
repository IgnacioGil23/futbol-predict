// Réplica en TypeScript del modelo de producción (src/serving/predictor.py):
//   log E[goles] = intercept + coef * (elo_diff - media) / desvío
// y la grilla de marcadores con goles Poisson independientes, recortada en
// MAX_GOALS y renormalizada. Un test (model.test.ts) verifica contra los
// vectores calculados en Python y exportados en model.json.

export interface GlmParams {
  intercept: number
  coef: number
  feature_mean: number
  feature_scale: number
}

export interface ModelParams {
  home_goals: GlmParams
  away_goals: GlmParams
}

export interface Forecast {
  lam: number
  mu: number
  probabilities: { home: number; draw: number; away: number }
  grid: number[][] // [golesLocal][golesVisitante], 0..maxGoals
}

function rate(p: GlmParams, eloDiff: number): number {
  return Math.exp(p.intercept + (p.coef * (eloDiff - p.feature_mean)) / p.feature_scale)
}

function poissonPmf(k: number, lambda: number): number {
  let logFact = 0
  for (let i = 2; i <= k; i++) logFact += Math.log(i)
  return Math.exp(k * Math.log(lambda) - lambda - logFact)
}

export function forecast(params: ModelParams, eloHome: number, eloAway: number, maxGoals = 10): Forecast {
  const diff = eloHome - eloAway
  const lam = rate(params.home_goals, diff)
  const mu = rate(params.away_goals, diff)
  const ph = Array.from({ length: maxGoals + 1 }, (_, k) => poissonPmf(k, lam))
  const pa = Array.from({ length: maxGoals + 1 }, (_, k) => poissonPmf(k, mu))
  let total = 0
  const grid = ph.map((h) => pa.map((a) => { const v = h * a; total += v; return v }))
  let home = 0, draw = 0, away = 0
  for (let x = 0; x <= maxGoals; x++) {
    for (let y = 0; y <= maxGoals; y++) {
      grid[x][y] /= total
      if (x > y) home += grid[x][y]
      else if (x === y) draw += grid[x][y]
      else away += grid[x][y]
    }
  }
  return { lam, mu, probabilities: { home, draw, away }, grid }
}

export function topScores(grid: number[][], k = 5) {
  const cells: { home: number; away: number; p: number }[] = []
  grid.forEach((row, x) => row.forEach((p, y) => cells.push({ home: x, away: y, p })))
  return cells.sort((a, b) => b.p - a.p).slice(0, k)
}
