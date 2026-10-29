import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { flushSync } from 'react-dom'
import { Link, useSearchParams } from 'react-router-dom'
import { Odo, PageBand, Reveal, Title } from '../components/Motion'
import { reducedMotion } from '../lib/motion'
import { OutcomeBar } from '../components/OutcomeBar'
import { ScoreHeatmap } from '../components/ScoreHeatmap'
import { formatDate, num, pct } from '../lib/data'
import { useLeague, useLeagueData } from '../lib/league'
import { forecast } from '../lib/model'
import type { ReviewMatch, ReviewSeasonFile, ReviewSeasonSummary } from '../lib/types'
import './review.css'

const RESULT_LABEL = { H: 'ganó el local', D: 'empate', A: 'ganó el visitante' } as const

// Grilla Poisson a partir de los goles esperados guardados (misma cuenta que el modelo).
function gridFrom(lam: number, mu: number) {
  const params = { home_goals: { intercept: Math.log(lam), coef: 0, feature_mean: 0, feature_scale: 1 },
                   away_goals: { intercept: Math.log(mu), coef: 0, feature_mean: 0, feature_scale: 1 } }
  return forecast(params, 0, 0).grid
}

type Sort = 'fecha' | 'sorpresas' | 'aciertos'

/** Reordenar con View Transitions: las filas se desplazan a su nuevo lugar (solo las primeras, las que se ven). */
function withTransition(update: () => void) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown }
  if (doc.startViewTransition && !reducedMotion()) doc.startViewTransition(() => flushSync(update))
  else update()
}
const vtName = (id: string) => `rv-${id.replace(/[^a-zA-Z0-9_-]/g, '-')}`

/** El filtro por equipo y el orden son del estado de la liga: se reinician al cambiar de liga. */
export function Review() {
  const { league } = useLeague()
  return <ReviewLiga key={league.slug} />
}

function ReviewLiga() {
  const [params, setParams] = useSearchParams()
  const index = useLeagueData<ReviewSeasonSummary[]>('review/index.json')
  const seasons = index.data ?? []
  const fromUrl = params.get('season')
  const season = (fromUrl && seasons.some((x) => x.season === fromUrl) ? fromUrl : '') || seasons[seasons.length - 2]?.season || ''
  const file = useLeagueData<ReviewSeasonFile>(season ? `review/${season}.json` : null)
  const [sort, setSort] = useState<Sort>('fecha')
  const [team, setTeam] = useState('')
  const selectedId = params.get('match')
  const detailRef = useRef<HTMLDivElement>(null)
  // En pantallas angostas el detalle queda debajo de la tabla: llevarlo a la vista al elegir un partido.
  useEffect(() => {
    if (selectedId && window.innerWidth < 900) detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [selectedId])

  const matches = useMemo(() => {
    let ms = file.data?.matches ?? []
    if (team) ms = ms.filter((m) => m.home_team === team || m.away_team === team)
    const copy = [...ms]
    if (sort === 'sorpresas') copy.sort((a, b) => a.p_actual - b.p_actual)
    else if (sort === 'aciertos') copy.sort((a, b) => b.p_actual - a.p_actual)
    else copy.sort((a, b) => (a.date < b.date ? 1 : -1))
    return copy
  }, [file.data, sort, team])
  const teams = useMemo(() => [...new Set((file.data?.matches ?? []).flatMap((m) => [m.home_team, m.away_team]))].sort(), [file.data])
  const selected = file.data?.matches.find((m) => m.id === selectedId) ?? null
  const summary = seasons.find((s) => s.season === season)

  const select = (m: ReviewMatch) => { const n = new URLSearchParams(params); n.set('season', season); n.set('match', m.id); setParams(n, { replace: true }) }

  return (
    <>
      <PageBand layout="7">
        <div className="hero-main">
          <Title lines={['¿Qué había', 'predicho', 'el modelo?']} />
          <p className="rise lede" style={{ '--d': '260ms' } as CSSProperties}>
            Cada predicción se hizo como si fuera antes del partido: el modelo se reentrena al comienzo de cada temporada
            solo con las anteriores, y el Elo usa solo partidos previos. Sin maquillaje: acá están también los errores.
          </p>
          <span className="rise data-label" style={{ '--d': '320ms' } as CSSProperties}>Revisión histórica</span>
        </div>
        <div className="hero-aside">
          {summary && (
            <div className="card review-summary rise" style={{ '--d': '240ms' } as CSSProperties}>
              <p className="data-label">{season} · log loss, menor es mejor · {summary.compared_matches} partidos con cuotas</p>
              <div className="rs-rows">
                <span>Modelo</span><span className="num rs-v"><Odo value={num(summary.model.log_loss, 3)} now /></span>
                <span>Mercado</span><span className="num rs-v"><Odo value={num(summary.market.log_loss, 3)} now /></span>
              </div>
              <p className="rs-hit">Resultado más probable acertado en <span className="num"><Odo value={pct(summary.model.accuracy)} now /></span> de los partidos.</p>
            </div>
          )}
        </div>
      </PageBand>
    <div className="container page">
      <div className="grid grid-main review-grid" style={{ alignItems: 'start' }}>
        <Reveal as="div" className="review-list">
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', marginBottom: 12 }}>
            <div className="field">
              <label htmlFor="season">Temporada</label>
              <select id="season" value={season} onChange={(e) => { setTeam(''); setParams({ season: e.target.value }, { replace: true }) }}>
                {[...seasons].reverse().map((s) => <option key={s.season} value={s.season}>{s.season}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="team">Equipo</label>
              <select id="team" value={team} onChange={(e) => setTeam(e.target.value)}>
                <option value="">Todos</option>
                {teams.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="sort">Orden</label>
              <select id="sort" value={sort} onChange={(e) => { const v = e.target.value as Sort; withTransition(() => setSort(v)) }}>
                <option value="fecha">Más recientes</option>
                <option value="sorpresas">Mayores sorpresas</option>
                <option value="aciertos">Resultados más anticipados</option>
              </select>
            </div>
          </div>
          {summary && (
            <p className="note" style={{ marginBottom: 10 }}>
              {season}: log loss del modelo <strong>{num(summary.model.log_loss, 3)}</strong> vs mercado <strong>{num(summary.market.log_loss, 3)}</strong>{' '}
              (menor es mejor; {summary.compared_matches} partidos con cuotas) · resultado más probable acertado en {pct(summary.model.accuracy)} de los partidos.
            </p>
          )}
          <div className="table-wrap" style={{ maxHeight: 560, overflowY: 'auto' }}>
            <table className="table">
              <thead><tr><th>Fecha</th><th>Partido</th><th className="num">Resultado</th><th className="num" title="Probabilidad que el modelo le daba al resultado que ocurrió">Prob. del resultado</th></tr></thead>
              <tbody>
                {matches.map((m, i) => (
                  <tr key={m.id} onClick={() => select(m)} className={m.id === selectedId ? 'selected' : undefined}
                      style={{ cursor: 'pointer', viewTransitionName: i < 40 ? vtName(m.id) : undefined } as CSSProperties}>
                    <td className="muted" style={{ whiteSpace: 'nowrap' }}>{formatDate(m.date, { day: 'numeric', month: 'short' })}</td>
                    <td><button onClick={() => select(m)} style={{ all: 'unset', cursor: 'pointer' }}>{m.home_team} – {m.away_team}</button></td>
                    <td className="num"><strong>{m.score[0]}-{m.score[1]}</strong></td>
                    <td className="num">
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span className="track pa-track">
                          <span style={{ width: `${m.p_actual * 100}%`, background: m.p_actual < 0.25 ? 'var(--away)' : 'var(--ink)' }} />
                        </span>
                        {pct(m.p_actual)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>

        <div ref={detailRef} className="card review-detail">
          {!selected ? (
            <>
              <h3>Elegí un partido</h3>
              <p className="small muted">Vas a ver la grilla de marcadores que calculó el modelo antes del partido, con el resultado real marcado.</p>
              <p className="small" style={{ marginTop: 12, color: 'var(--ink-2)' }}>
                Tip: ordená por <strong>mayores sorpresas</strong> para ver los resultados que el modelo consideraba más improbables.
              </p>
            </>
          ) : (
            <>
              <span className="data-label">{formatDate(selected.date)}</span>
              <h3 className="review-match">{selected.home_name} {selected.score[0]}-{selected.score[1]} {selected.away_name}</h3>
              <p className="card-sub">
                Resultado: {RESULT_LABEL[selected.result]}. El modelo le daba un {pct(selected.p_actual)}.
                Goles esperados {num(selected.expected_goals[0])} – {num(selected.expected_goals[1])} · Elo {num(selected.elo[0], 0)} vs {num(selected.elo[1], 0)}.
              </p>
              <OutcomeBar probs={{ home: selected.p[0], draw: selected.p[1], away: selected.p[2] }}
                          homeName={selected.home_name} awayName={selected.away_name}
                          market={selected.market ? { home: selected.market[0], draw: selected.market[1], away: selected.market[2] } : null} />
              <div style={{ marginTop: 14 }}>
                <ScoreHeatmap grid={gridFrom(selected.expected_goals[0], selected.expected_goals[1])}
                              homeName={selected.home_name} awayName={selected.away_name} actual={selected.score} size={6} />
              </div>
              <Link className="btn" style={{ marginTop: 12 }} to={`/partidos/previa?home=${encodeURIComponent(selected.home_team)}&away=${encodeURIComponent(selected.away_team)}`}>
                Este cruce hoy →
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
    </>
  )
}
