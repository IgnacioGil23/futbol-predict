import { scaleLinear } from 'd3-scale'
import { line } from 'd3-shape'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { formatDate, num, pct, useData } from '../lib/data'
import type { MonitoringIndicator, MonitoringReport, MonitoringStatus } from '../lib/types'
import { useWidth } from '../lib/useWidth'
import './monitoring.css'

const REPO = 'https://github.com/IgnacioGil23/futbol-predict'

const STATUS_TEXT: Record<MonitoringStatus, string> = {
  ok: 'Todos los indicadores están dentro de lo normal según 10 temporadas de historia.',
  atencion: 'Algún indicador está fuera de su rango habitual. Se sigue de cerca; todavía puede ser azar.',
  alerta: 'Algún indicador está en una zona que casi nunca ocurrió en la historia. Se abrió una alerta para revisar el modelo.',
  insuficiente: 'Todavía hay pocos partidos evaluados: con menos de media temporada, cualquier desvío es compatible con el azar.',
}

const fmt = (name: string, v: number | null) => {
  if (v === null) return '—'
  if (name === 'goals_ratio') return num(v, 2)
  if (name === 'draws_diff_pp') return `${v > 0 ? '+' : ''}${num(v, 1)} pp`
  return `${v > 0 ? '+' : ''}${num(v, 3)}`
}

/** Barra horizontal: franja de alerta, franja normal (backtest) y el valor actual. */
function RangeBar({ name, ind }: { name: string; ind: MonitoringIndicator }) {
  const [ref, width] = useWidth<HTMLDivElement>(260)
  const [a0, a1] = ind.alert_range
  const [n0, n1] = ind.normal_range
  const v = ind.value
  const pad = (a1 - a0) * 0.35
  const lo = Math.min(a0 - pad, v ?? a0)
  const hi = Math.max(a1 + pad, v ?? a1)
  const x = scaleLinear().domain([lo, hi]).range([6, width - 6]).clamp(true)
  return (
    <div ref={ref} className="range-bar">
      <svg width={width} height={34} role="img" aria-label={`Valor ${fmt(name, v)}; rango normal ${fmt(name, n0)} a ${fmt(name, n1)}`}>
        <rect x={6} y={12} width={width - 12} height={8} rx={4} fill="var(--surface-2)" />
        <rect x={x(a0)} y={12} width={x(a1) - x(a0)} height={8} fill="var(--line)" />
        <rect x={x(n0)} y={12} width={x(n1) - x(n0)} height={8} fill="color-mix(in srgb, var(--good) 35%, transparent)" />
        <line x1={x(ind.backtest_median)} x2={x(ind.backtest_median)} y1={9} y2={23} stroke="var(--muted)" strokeDasharray="2 2" />
        {v !== null && <circle cx={x(v)} cy={16} r={6} className={`dot-${ind.status}`} stroke="var(--surface)" strokeWidth={2} />}
      </svg>
      <div className="range-labels small muted tabular">
        <span>normal: {fmt(name, n0)} a {fmt(name, n1)}</span>
        <span>mediana histórica {fmt(name, ind.backtest_median)}</span>
      </div>
    </div>
  )
}

/** Brecha acumulada modelo − mercado a medida que se evalúan partidos. */
function GapChart({ report }: { report: MonitoringReport }) {
  const [ref, width] = useWidth<HTMLDivElement>(700)
  const [hover, setHover] = useState<number | null>(null)
  const pts = report.cumulative.filter((p) => p.gap !== null) as { date: string; n: number; gap: number; source: string }[]
  const ind = report.indicators.gap_vs_market
  if (pts.length < 2 || !ind) return <p className="small muted">Todavía no hay suficientes partidos con cuotas para graficar.</p>
  const h = 240
  const m = { top: 12, right: 12, bottom: 28, left: 44 }
  const ys = pts.map((p) => p.gap)
  const lo = Math.min(-0.06, ...ys, ind.normal_range[0])
  const hi = Math.max(0.08, ...ys, ind.alert_range[1])
  const x = scaleLinear().domain([1, pts[pts.length - 1].n]).range([m.left, width - m.right])
  const y = scaleLinear().domain([lo, hi]).nice().range([h - m.bottom, m.top])
  const path = line<(typeof pts)[number]>().x((p) => x(p.n)).y((p) => y(p.gap))
  const hp = hover !== null ? pts[hover] : null
  return (
    <div ref={ref} className="chart-wrap">
      <svg width={width} height={h} role="img" aria-label="Brecha acumulada de log loss contra el mercado"
           onMouseMove={(e) => {
             const px = e.clientX - (e.currentTarget as SVGSVGElement).getBoundingClientRect().left
             const n = Math.round(x.invert(px))
             const i = pts.findIndex((p) => p.n >= n)
             setHover(i >= 0 ? i : null)
           }} onMouseLeave={() => setHover(null)}>
        <rect x={m.left} width={width - m.left - m.right} y={y(ind.normal_range[1])} height={y(ind.normal_range[0]) - y(ind.normal_range[1])}
              fill="color-mix(in srgb, var(--good) 14%, transparent)" />
        {y.ticks(5).map((t) => (
          <g key={t}>
            <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? 'var(--axis)' : 'var(--line)'} />
            <text x={m.left - 6} y={y(t) + 4} textAnchor="end">{t > 0 ? '+' : ''}{num(t, 2)}</text>
          </g>
        ))}
        {x.ticks(6).map((t) => <text key={t} x={x(t)} y={h - 8} textAnchor="middle">{t}</text>)}
        <path d={path(pts) ?? ''} fill="none" stroke="var(--home)" strokeWidth={2} />
        {hp && <circle cx={x(hp.n)} cy={y(hp.gap)} r={4.5} fill="var(--home)" stroke="var(--surface)" strokeWidth={2} />}
      </svg>
      {hp && (
        <div className="tooltip" style={{ left: x(hp.n), top: y(hp.gap) }}>
          {hp.n} partidos (hasta el {formatDate(hp.date)}): brecha {hp.gap > 0 ? '+' : ''}{num(hp.gap, 3)}
        </div>
      )}
      <p className="small muted">
        Eje X: partidos evaluados. Eje Y: log loss del modelo menos el del mercado (positivo = el mercado predijo mejor).
        Franja verde: rango normal en ventanas de {report.window} partidos según el backtest; con menos partidos la línea
        oscila mucho más, por puro azar.
      </p>
    </div>
  )
}

export function Monitoring() {
  const { data: r, error, loading } = useData<MonitoringReport>('monitoring.json')
  if (loading) return <div className="container section"><div className="skeleton" style={{ minHeight: 400 }} /></div>
  if (error || !r) {
    return (
      <div className="container section">
        <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3.2rem)' }}>Monitoreo del modelo</h1>
        <p className="callout" style={{ marginTop: 16 }}>Todavía no hay un reporte de monitoreo publicado.</p>
      </div>
    )
  }
  const s = r.season
  const missing = Math.max(0, r.window - r.counts.evaluated)
  return (
    <div className="container section">
      <div className="section-head">
        <span className="eyebrow">Transparencia · actualizado el {formatDate(r.generated_at)}</span>
        <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3.2rem)' }}>Monitoreo del modelo</h1>
        <p className="lede">
          Antes de cada partido se guarda la predicción en un <a href={`${REPO}/blob/monitoring/ledger/predictions.csv`} target="_blank" rel="noreferrer">registro público e inmutable</a>{' '}
          (<a href={`${REPO}/commits/monitoring`} target="_blank" rel="noreferrer">historial de cambios</a>). Después del partido se compara
          con el resultado y con el mercado de apuestas. Así se ve si el modelo se degrada con el tiempo.
        </p>
      </div>

      <div className={`card status-card status-${r.status}`}>
        <span className={`status-pill pill-${r.status}`}>{r.status_label}</span>
        <p style={{ margin: '10px 0 0' }}>{STATUS_TEXT[r.status]}</p>
        {missing > 0 && (
          <p className="small muted" style={{ marginTop: 6 }}>
            Faltan {missing} partidos evaluados para completar la primera ventana de {r.window} (media temporada).
          </p>
        )}
      </div>

      <div className="grid grid-3" style={{ marginTop: 16 }}>
        <div className="card stat">
          <span className="small muted">Predicciones registradas</span>
          <strong className="big-num tabular">{r.counts.logged}</strong>
          <span className="small muted">{r.counts.logged_live} en vivo (antes del partido) · {r.counts.logged_reconstructed} reconstruidas</span>
        </div>
        <div className="card stat">
          <span className="small muted">Evaluadas contra el resultado</span>
          <strong className="big-num tabular">{r.counts.evaluated}</strong>
          <span className="small muted">{r.counts.pending} pendientes de jugarse</span>
        </div>
        <div className="card stat">
          <span className="small muted">Versión del modelo</span>
          <strong className="big-num tabular" style={{ fontSize: '1.3rem' }}>{r.model_versions.join(', ')}</strong>
          <span className="small muted">Hash de sus parámetros: cambia si cambia algún número</span>
        </div>
      </div>

      <h2 style={{ margin: '32px 0 12px' }}>Indicadores</h2>
      <p className="small muted" style={{ marginBottom: 12 }}>
        Sobre los últimos {r.window} partidos evaluados. Los rangos no son arbitrarios: salen de un backtest del mismo modelo en{' '}
        {r.thresholds.backtest.seasons} (normal = lo que pasó en el 95% de las ventanas; fuera de la franja gris = alerta).
      </p>
      <div className="grid grid-2">
        {Object.entries(r.indicators).map(([name, ind]) => (
          <div key={name} className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
              <h3 style={{ margin: 0, fontSize: '1.05rem' }}>{ind.description}</h3>
              <span className={`status-pill pill-${ind.status}`}>{ind.status_label}</span>
            </div>
            <div className="big-num tabular" style={{ margin: '6px 0 2px' }}>{fmt(name, ind.value)}</div>
            <div className="small muted">{ind.n} partidos</div>
            <RangeBar name={name} ind={ind} />
          </div>
        ))}
      </div>

      {s && (
        <>
          <h2 style={{ margin: '32px 0 12px' }}>Temporada {s.season}</h2>
          <div className="grid grid-3">
            <div className="card stat">
              <span className="small muted">Log loss: modelo vs mercado</span>
              <strong className="big-num tabular">{num(s.model.log_loss, 3)} <span className="muted" style={{ fontSize: '1.1rem' }}>vs {s.market ? num(s.market.log_loss, 3) : '—'}</span></strong>
              <span className="small muted">
                {s.gap_ci ? `Brecha ${s.gap_vs_market! > 0 ? '+' : ''}${num(s.gap_vs_market!, 3)} (IC 95% ${num(s.gap_ci[0], 3)} a ${num(s.gap_ci[1], 3)})` : 'Sin cuotas suficientes'}
              </span>
            </div>
            <div className="card stat">
              <span className="small muted">Goles: reales vs esperados</span>
              <strong className="big-num tabular">{num(s.goals.actual, 0)} <span className="muted" style={{ fontSize: '1.1rem' }}>vs {num(s.goals.expected, 0)}</span></strong>
              <span className="small muted">{s.matches} partidos</span>
            </div>
            <div className="card stat">
              <span className="small muted">Empates: reales vs esperados</span>
              <strong className="big-num tabular">{num(s.draws.actual, 0)} <span className="muted" style={{ fontSize: '1.1rem' }}>vs {num(s.draws.expected, 1)}</span></strong>
              <span className="small muted">Aciertos del resultado: modelo {pct(s.model.accuracy)}{s.market ? ` · mercado ${pct(s.market.accuracy)}` : ''}</span>
            </div>
          </div>
        </>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Brecha acumulada contra el mercado</h3>
        <GapChart report={r} />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Últimas predicciones evaluadas</h3>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Fecha</th><th>Partido</th><th className="num">Resultado</th><th className="num">Modelo (L · E · V)</th><th className="num">Mercado</th><th className="num">Prob. del resultado</th><th>Origen</th></tr></thead>
            <tbody>
              {r.recent.map((m) => (
                <tr key={`${m.home_team}-${m.away_team}-${m.date}`}>
                  <td className="muted" style={{ whiteSpace: 'nowrap' }}>{formatDate(m.date, { day: 'numeric', month: 'short' })}</td>
                  <td>{m.home_team} – {m.away_team}</td>
                  <td className="num"><strong>{m.score[0]}-{m.score[1]}</strong></td>
                  <td className="num">{m.p.map((p) => pct(p)).join(' · ')}</td>
                  <td className="num muted">{m.market ? m.market.map((p) => pct(p)).join(' · ') : '—'}</td>
                  <td className="num">{pct(m.p_actual)}</td>
                  <td><span className={`source source-${m.source}`}>{m.source === 'vivo' ? 'en vivo' : 'reconstruida'}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 8 }}>
          "Reconstruida": predicción fuera de muestra calculada después del partido, solo para arrancar el historial de
          2026-27. "En vivo": guardada antes del partido. Ambas usan solo información previa a cada partido.
        </p>
      </div>

      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>Qué puede detectar</h3>
          <ul className="small" style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
            <li>Que el modelo empeore frente al mercado de forma sostenida.</li>
            <li>Cambios en el nivel de goles de la liga o en la frecuencia de empates que el modelo no capture.</li>
            <li>Que la ventaja de local cambie (como pasó con los estadios vacíos en 2020-21).</li>
          </ul>
        </div>
        <div className="card">
          <h3>Qué no puede detectar</h3>
          <ul className="small" style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
            <li>Cambios chicos: con {r.window} partidos, la brecha contra el mercado tiene un error de ~0,011, así que solo se
              detectan deterioros de más de ~0,02.</li>
            <li>Problemas de un equipo puntual: son pocos partidos para separarlos del azar.</li>
            <li>Nada durante las primeras semanas de cada temporada (datos insuficientes).</li>
          </ul>
          <p className="small" style={{ marginTop: 10 }}><Link to="/metodologia">Cómo se evaluó el modelo →</Link></p>
        </div>
      </div>
    </div>
  )
}
