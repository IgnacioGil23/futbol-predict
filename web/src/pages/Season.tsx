import { Link } from 'react-router-dom'
import { formatDate, num, pct, pct1, useData } from '../lib/data'
import type { SeasonEvaluation, SeasonFile, SeasonTeam } from '../lib/types'
import './season.css'

const REPO = 'https://github.com/IgnacioGil23/futbol-predict'

/** Probabilidad como porcentaje legible: "<0,1%" en lugar de 0% cuando pasó en alguna simulación. */
function prob(p: number) {
  if (p === 0) return '—'
  if (p < 0.001) return '<0,1%'
  if (p > 0.999) return '>99,9%'
  return p < 0.1 ? pct1(p) : pct(p)
}

function ProbCell({ p, tone }: { p: number; tone: 'up' | 'down' }) {
  return (
    <td className="num prob-cell">
      <span className="prob-bar" data-tone={tone} style={{ width: `${Math.round(p * 100)}%` }} />
      <span className="prob-text tabular">{prob(p)}</span>
    </td>
  )
}

function PositionGrid({ teams }: { teams: SeasonTeam[] }) {
  const n = teams.length
  return (
    <div className="table-wrap">
      <div className="pos-grid" style={{ gridTemplateColumns: `minmax(120px, 1.4fr) repeat(${n}, minmax(22px, 1fr))` }}
           role="table" aria-label="Probabilidad de cada posición final">
        <div className="pos-head" role="columnheader">Equipo</div>
        {Array.from({ length: n }, (_, i) => (
          <div key={i} className={`pos-head num ${i < 4 ? 'zone-top' : i >= n - 3 ? 'zone-rel' : ''}`} role="columnheader">{i + 1}</div>
        ))}
        {teams.map((t) => (
          <div key={t.slug} className="pos-row" role="row">
            <div className="pos-team" role="rowheader"><Link to={`/equipos/${t.slug}`}>{t.name}</Link></div>
            {t.positions.map((p, i) => (
              <div key={i} className="pos-cell" role="cell" title={`${t.name}: ${prob(p)} de terminar ${i + 1}º`}
                   style={{ '--p': Math.min(1, p / 0.5) } as React.CSSProperties}>
                {p >= 0.1 ? <span className="tabular">{Math.round(p * 100)}</span> : null}
              </div>
            ))}
          </div>
        ))}
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>
        Cada celda: probabilidad de terminar en esa posición (se muestra el número desde 10%). Columnas 1-4: zona de
        Champions por posición; 18-20: descenso.
      </p>
    </div>
  )
}

/** "[0.05, 0.2)" -> "5% a 20%" (el último tramo llega hasta 100%). */
function binLabel(bin: string) {
  return bin.replace(/[[\]()]/g, '').split(', ').map((x) => pct(Math.min(1, Number(x)))).join(' a ')
}

const EVENT_LABEL ={ campeon: 'Campeón', top4: 'Top 4', descenso: 'Descenso' } as const
const CUTOFF_LABEL = (c: number) => (c === 0 ? 'Antes de la fecha 1' : `Tras ${c} partidos`)

function Evaluation({ ev }: { ev: SeasonEvaluation }) {
  const events = ['campeon', 'top4', 'descenso'] as const
  const cutoffs = [...new Set(ev.table.map((r) => r.cutoff))].sort((a, b) => a - b)
  return (
    <section style={{ marginTop: 32 }}>
      <h2 style={{ marginBottom: 8 }}>¿Son creíbles estas probabilidades?</h2>
      <p className="lede" style={{ maxWidth: 820 }}>
        Simulamos las temporadas {ev.seasons[0]} a {ev.seasons[ev.seasons.length - 1]} desde cuatro momentos, cada una
        con el modelo entrenado solo con temporadas anteriores, y comparamos con lo que pasó. La regla se fijó antes de
        mirar los resultados, en el{' '}
        <a href={`${REPO}/blob/main/docs/preregistro_temporada.md`} target="_blank" rel="noreferrer">preregistro</a>.
      </p>
      <div className="card">
        <h3>Error de la simulación y mejora contra una que no conoce la fuerza de los equipos</h3>
        <p className="card-sub">
          <strong>Error</strong> (Brier): la diferencia al cuadrado entre la probabilidad y lo que pasó; más bajo es mejor.
          Se compara con el mismo simulador con todos los equipos iguales, que solo conoce la tabla.{' '}
          <strong>Mejora</strong>: cuánto baja el error frente a ese simulador (0% = no aporta; entre corchetes, el
          intervalo de 95% entre temporadas).
        </p>
        <div className="table-wrap">
          <table className="table eval-table">
            <thead>
              <tr><th>Momento</th>{events.map((e) => <th key={e} className="num">{EVENT_LABEL[e]}</th>)}</tr>
            </thead>
            <tbody>
              {cutoffs.map((c) => (
                <tr key={c}>
                  <td>{CUTOFF_LABEL(c)}</td>
                  {events.map((e) => {
                    const r = ev.table.find((x) => x.event === e && x.cutoff === c)!
                    return (
                      <td key={e} className="num">
                        <div className="tabular">
                          Error <strong>{num(r.producto.brier, 3)}</strong>
                          <span className="muted"> vs {num(r.base_iguales.brier, 3)}</span>
                        </div>
                        <div className="small tabular">
                          Mejora <strong>{pct(r.producto.skill)}</strong>
                          <span className="muted"> [{pct(r.producto.skill_ci[0])}; {pct(r.producto.skill_ci[1])}]</span>
                        </div>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 8 }}>
          <strong>Por qué la mejora se achica aunque el modelo acierte cada vez más:</strong> el error de la simulación
          baja mucho a lo largo de la temporada (en el top 4, de{' '}
          {num(ev.table.find((x) => x.event === 'top4' && x.cutoff === cutoffs[0])!.producto.brier, 3)} a{' '}
          {num(ev.table.find((x) => x.event === 'top4' && x.cutoff === cutoffs[cutoffs.length - 1])!.producto.brier, 3)}),
          pero el del simulador que solo conoce la tabla también: cerca del final, la tabla ya define casi todo y la
          fuerza de los equipos solo importa en los pocos casos que siguen abiertos. En la última fecha, los dos serían
          prácticamente iguales.
        </p>
      </div>
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        {(['top4', 'descenso'] as const).map((e) => (
          <div key={e} className="card">
            <h3>Calibración · {EVENT_LABEL[e]}</h3>
            <p className="card-sub">Cuando la simulación dijo X%, ¿cuántas veces pasó? Todas las temporadas y momentos juntos.</p>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Probabilidad simulada</th><th className="num">Casos</th><th className="num">Media simulada</th><th className="num">Pasó</th></tr></thead>
                <tbody>
                  {ev.calibration[e].map((b) => (
                    <tr key={b.bin}>
                      <td className="tabular">{binLabel(b.bin)}</td>
                      <td className="num">{b.n}</td>
                      <td className="num">{pct1(b.predicted)}</td>
                      <td className="num">{pct1(b.observed)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export function Season() {
  const { data: s, error, loading } = useData<SeasonFile>('season.json')
  if (loading) return <div className="container section"><div className="skeleton" style={{ minHeight: 400 }} /></div>
  if (error || !s) {
    return <div className="container section"><p className="callout">Todavía no hay una simulación publicada.</p></div>
  }
  return (
    <div className="container section">
      <div className="section-head">
        <span className="eyebrow">Temporada {s.season} · actualizada el {formatDate(s.as_of)}</span>
        <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3.2rem)' }}>¿Cómo puede terminar la temporada?</h1>
        <p className="lede" style={{ maxWidth: 820 }}>
          Jugamos los {s.remaining_matches} partidos que faltan {num(s.n_sims, 0)} veces con el modelo. En cada
          simulación, el Elo de los equipos se actualiza con los resultados simulados, así una racha cambia las chances de
          lo que viene, como en la realidad. Desempates: puntos, diferencia de gol y goles a favor.
        </p>
      </div>
      <div className="card">
        <div className="table-wrap">
          <table className="table season-table">
            <thead>
              <tr>
                <th>Equipo</th><th className="num">Pts (PJ)</th><th className="num">Elo</th><th className="num">Pts esperados</th>
                <th className="num">Campeón</th><th className="num">Top 4</th><th className="num">Top 6</th><th className="num">Descenso</th>
              </tr>
            </thead>
            <tbody>
              {s.teams.map((t) => (
                <tr key={t.slug}>
                  <td><Link to={`/equipos/${t.slug}`}>{t.name}</Link></td>
                  <td className="num tabular">{t.points} <span className="muted">({t.played})</span></td>
                  <td className="num tabular">{num(t.elo, 0)}</td>
                  <td className="num tabular">{num(t.expected_points, 1)}</td>
                  <ProbCell p={t.p_champion} tone="up" />
                  <ProbCell p={t.p_top4} tone="up" />
                  <ProbCell p={t.p_top6} tone="up" />
                  <ProbCell p={t.p_relegation} tone="down" />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 8 }}>
          "Top 4" y "Top 6" son posiciones en la tabla: los cupos europeos exactos dependen también de las copas. No se
          modelan descuentos de puntos ni desempates por cara a cara. Modelo {s.model_version}.
        </p>
      </div>

      <h2 style={{ margin: '32px 0 12px' }}>Todas las posiciones posibles</h2>
      <div className="card"><PositionGrid teams={s.teams} /></div>

      {s.evaluation && <Evaluation ev={s.evaluation} />}
    </div>
  )
}
