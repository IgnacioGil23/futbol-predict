import { Link } from 'react-router-dom'
import { num } from '../lib/data'
import { topScores } from '../lib/model'
import type { EloPoint, FormMatch, H2H, Probabilities, Rest } from '../lib/types'
import { EloChart } from './EloChart'
import { FormStrip, H2HBlock, RestBlock } from './MatchContext'
import { OutcomeBar } from './OutcomeBar'
import { ScoreHeatmap } from './ScoreHeatmap'

/** Todo lo que se muestra de un partido (Previa y Próximos partidos usan el mismo formato). */
export interface MatchView {
  elo: { home: number; away: number }
  lam: number
  mu: number
  probabilities: Probabilities
  grid: number[][]
  market: Probabilities | null
  form: { home: FormMatch[]; away: FormMatch[] }
  rest: { home: Rest; away: Rest }
  h2h: H2H
  eloHistory: { home: EloPoint[]; away: EloPoint[] } | null   // null = todavía cargando
}

interface Props {
  view: MatchView
  home: string
  away: string
  homeName: string
  awayName: string
  homeSlug?: string
  awaySlug?: string
}

export function MatchAnalysis({ view, home, homeName, awayName, homeSlug, awaySlug }: Props) {
  const top = topScores(view.grid, 3)
  const diff = view.elo.home - view.elo.away
  return (
    <>
      <div className="grid grid-main" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>Probabilidad de cada marcador</h3>
          <p className="card-sub">Goles esperados: {homeName} {num(view.lam)} · {awayName} {num(view.mu)}</p>
          <ScoreHeatmap grid={view.grid} homeName={homeName} awayName={awayName} />
        </div>
        <div className="grid" style={{ alignContent: 'start' }}>
          <div className="card">
            <h3>Resultado</h3>
            <OutcomeBar probs={view.probabilities} homeName={homeName} awayName={awayName} market={view.market} />
          </div>
          <div className="card">
            <h3>Marcadores más probables</h3>
            <ol style={{ margin: 0, paddingLeft: 20 }} className="tabular">
              {top.map((s) => (
                <li key={`${s.home}-${s.away}`} style={{ padding: '2px 0' }}>
                  <strong>{s.home}-{s.away}</strong> <span className="muted">· {num(s.p * 100, 1)}%</span>
                </li>
              ))}
            </ol>
            <p className="small muted" style={{ marginTop: 8 }}>
              En las 8.030 predicciones históricas del modelo (2005-2026), el marcador más probable nunca superó el
              15%: en fútbol hay demasiados resultados posibles como para "acertar el resultado exacto".
            </p>
          </div>
          <div className="card">
            <h3>Elo</h3>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }} className="tabular">
              <div><div className="small muted">{homeName}</div><strong className="big-num">{num(view.elo.home, 0)}</strong></div>
              <div style={{ textAlign: 'center' }}><div className="small muted">Diferencia</div><strong className="big-num">{diff > 0 ? '+' : ''}{num(diff, 0)}</strong></div>
              <div style={{ textAlign: 'right' }}><div className="small muted">{awayName}</div><strong className="big-num">{num(view.elo.away, 0)}</strong></div>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Evolución del Elo (dos temporadas)</h3>
        <p className="card-sub">La fuerza de cada equipo según sus resultados: sube al ganar, más cuanto más fuerte el rival y más amplia la victoria.</p>
        {view.eloHistory ? (
          <EloChart series={[
            { name: homeName, color: 'var(--home)', points: view.eloHistory.home },
            { name: awayName, color: 'var(--away)', points: view.eloHistory.away },
          ]} />
        ) : <div className="skeleton" style={{ minHeight: 260 }} />}
        <div style={{ display: 'flex', gap: 12, marginTop: 10, flexWrap: 'wrap' }} className="small">
          {homeSlug && <Link to={`/equipos/${homeSlug}`}>Ficha de {homeName} →</Link>}
          {awaySlug && <Link to={`/equipos/${awaySlug}`}>Ficha de {awayName} →</Link>}
        </div>
      </div>

      <div className="grid grid-3" style={{ marginTop: 16 }}>
        <div className="card"><h3>Forma · {homeName}</h3><FormStrip form={view.form.home} name={homeName} /></div>
        <div className="card"><h3>Forma · {awayName}</h3><FormStrip form={view.form.away} name={awayName} /></div>
        <div className="card">
          <h3>Cara a cara</h3>
          <H2HBlock h2h={view.h2h} homeTeam={home} homeName={homeName} awayName={awayName} />
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>Descanso y congestión</h3>
          <div className="grid grid-2">
            <RestBlock rest={view.rest.home} name={homeName} />
            <RestBlock rest={view.rest.away} name={awayName} />
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>
            Solo cuenta partidos de liga: los datos no incluyen copas ni competiciones europeas, así que un equipo que
            jugó Champions a mitad de semana aparece "descansado". Por eso (y porque no mejoró la validación) el
            modelo no usa este dato.
          </p>
        </div>
        <div className="card">
          <h3>Lo que el modelo no sabe</h3>
          <ul className="small" style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
            <li>Lesiones, suspensiones y alineaciones confirmadas.</li>
            <li>Rotaciones por copas o competiciones europeas.</li>
            <li>Fichajes y cambios de entrenador (salvo cuando ya se reflejan en resultados).</li>
            <li>Noticias de la semana: el mercado de apuestas sí las incorpora, y por eso predice mejor.</li>
          </ul>
          <p className="small" style={{ marginTop: 10 }}><Link to="/metodologia">¿Qué tan bien predice? →</Link></p>
        </div>
      </div>
    </>
  )
}
