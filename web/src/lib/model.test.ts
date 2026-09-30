import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { forecast, topScores } from './model'

// model.json lo genera `python -m src.export.site`; incluye vectores calculados con el predictor de Python.
const model = JSON.parse(readFileSync(new URL('../../public/data/model.json', import.meta.url), 'utf-8'))

describe('modelo TypeScript = modelo Python', () => {
  for (const v of model.test_vectors) {
    it(`elo_diff = ${v.elo_diff}`, () => {
      const f = forecast(model.params, 1800 + v.elo_diff / 2, 1800 - v.elo_diff / 2, model.max_goals)
      expect(f.lam).toBeCloseTo(v.lam, 10)
      expect(f.mu).toBeCloseTo(v.mu, 10)
      expect(f.probabilities.home).toBeCloseTo(v.probabilities[0], 10)
      expect(f.probabilities.draw).toBeCloseTo(v.probabilities[1], 10)
      expect(f.probabilities.away).toBeCloseTo(v.probabilities[2], 10)
      expect(f.grid[0][0]).toBeCloseTo(v.score_0_0, 10)
      expect(f.grid[2][1]).toBeCloseTo(v.score_2_1, 10)
    })
  }

  it('la grilla es una distribución y el top de marcadores está ordenado', () => {
    const f = forecast(model.params, 1900, 1700)
    const total = f.grid.flat().reduce((a, b) => a + b, 0)
    expect(total).toBeCloseTo(1, 12)
    const top = topScores(f.grid, 3)
    expect(top[0].p).toBeGreaterThanOrEqual(top[1].p)
    expect(f.probabilities.home).toBeGreaterThan(f.probabilities.away)
  })
})
