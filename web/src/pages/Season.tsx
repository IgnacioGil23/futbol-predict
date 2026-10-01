import { TeamName } from '../components/TeamName'
import { formatDate, num, pct, pct1, REPO, useData } from '../lib/data'
import { useTeamIndex } from '../lib/teams'
import type { SeasonEvaluation, SeasonFile, SeasonTeam, TeamIndexItem } from '../lib/types'
import './season.css'


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

function PositionGrid({ teams, index }: { teams: SeasonTeam[]; index: Map<string, TeamIndexItem> }) {
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
            <div className="pos-team" role="rowheader"><TeamName team={index.get(t.team)} name={t.name} size={18} to={`/equipos/${t.slug}`} /></div>
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
        <strong>Cómo leerla:</strong> cada fila es un equipo y cada columna, una posición final. Cuanto más intenso el
        color, más probable es que termine ahí (el número, en %, se muestra desde 10%). Cada fila suma 100%: una fila con
        el color concentrado en pocas columnas es un equipo con destino bastante claro; una fila con el color repartido,
        uno que todavía puede terminar en muchos lugares. Columnas 1-4 en azul: puestos de top 4; 18-20 en naranja:
        descenso.
      </p>
    </div>
  )
}

/** "[0.05, 0.2)" -> "5% a 20%" (el último tramo llega hasta 100%). */
function binLabel(bin: string) {
  return bin.replace(/[[\]()]/g, '').split(', ').map((x) => pct(Math.min(1, Number(x)))).join(' a ')
}

const EVENT_LABEL = { campeon: 'Campeón', top4: 'Top 4', descenso: 'Descenso' } as const
const CUTOFF_LABEL = (c: number) => (c === 0 ? 'Antes de la fecha 1' : `Tras ${c} partidos`)

/** Explicación de una tabla de calibración, con un ejemplo tomado de sus propios datos. */
function CalibrationHelp({ rows, event }: { rows: SeasonEvaluation['calibration']['top4']; event: string }) {
  const example = rows.find((r) => r.bin.startsWith('[0.5')) ?? rows[Math.floor(rows.length / 2)]
  return (
    <p className="small muted" style={{ marginTop: 8 }}>
      <strong>Cómo leerla:</strong> juntamos todas las veces que la simulación dio una probabilidad de {event} dentro de
      cada tramo. "Casos" es cuántas veces pasó eso, "Media simulada" lo que dijo en promedio y "Pasó" en qué porcentaje de
      esos casos ocurrió de verdad. Si las dos últimas columnas se parecen, los porcentajes son confiables.
      {example && (
        <> Por ejemplo, en {example.n} casos dijo entre {binLabel(example.bin)} (en promedio {pct1(example.predicted)}) y
          ocurrió el {pct1(example.observed)} de las veces.</>
      )}{' '}
      En los tramos con pocos casos, diferencias de algunos puntos son esperables por azar.
    </p>
  )
}

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
          <strong>Cómo leerla:</strong> cada fila es un momento de la temporada desde el que se simuló. En cada celda, el
          primer número es el error de nuestra simulación y el segundo, el de la simulación que trata a todos los equipos
          como iguales; si el nuestro es más bajo, la fuerza de los equipos ayuda a predecir. La "mejora" resume esa
          diferencia en porcentaje. Si el intervalo entre corchetes no incluye el 0, la mejora es clara; si lo incluye, con
          solo {ev.seasons.length} temporadas no alcanza para asegurarla.
        </p>
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
            <CalibrationHelp rows={ev.calibration[e]} event={EVENT_LABEL[e].toLowerCase()} />
          </div>
        ))}
      </div>
    </section>
  )
}

export function Season() {
  const { data: s, error, loading } = useData<SeasonFile>('season.json')
  const { byTeam } = useTeamIndex()
  if (loading) return <div className="container section"><div className="skeleton" style={{ minHeight: 400 }} /></div>
  if (error || !s) {
    return <div className="container section"><p className="callout">Todavía no hay una simulación publicada.</p></div>
  }
  return (
    <div className="container section">
      <div className="section-head">
        <span className="eyebrow">Temporada {s.season} · actualizada el {formatDate(s.as_of)}</span>
        <h1>¿Cómo puede terminar la temporada?</h1>
        <p className="lede" style={{ maxWidth: 820 }}>
          Jugamos los {s.remaining_matches} partidos que faltan {num(s.n_sims, 0)} veces con el modelo. En cada
          simulación, el Elo de los equipos se actualiza con los resultados simulados, así una racha cambia las chances de
          lo que viene, como en la realidad. Desempates: puntos, diferencia de gol y goles a favor. La simulación usa el
          modelo con el Elo de resultados (el evaluado en su preregistro): el Elo de cuotas del resto del sitio no puede
          actualizarse con partidos simulados, porque no tienen cuotas.
        </p>
      </div>
      <div className="card">
        <div className="table-wrap">
          <table className="table season-table">
            <thead>
              <tr>
                <th>Equipo</th><th className="num">Pts (PJ)</th><th className="num" title="Elo de resultados">Elo (res.)</th><th className="num">Pts esperados</th>
                <th className="num">Campeón</th><th className="num">Top 4</th><th className="num">Top 6</th><th className="num">Descenso</th>
              </tr>
            </thead>
            <tbody>
              {s.teams.map((t) => (
                <tr key={t.slug}>
                  <td><TeamName team={byTeam.get(t.team)} name={t.name} to={`/equipos/${t.slug}`} /></td>
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
          <strong>Cómo leerla:</strong> "Pts (PJ)" son los puntos reales hasta hoy y los partidos jugados; "Pts esperados",
          el promedio de puntos al final de la temporada en todas las simulaciones. Las últimas cuatro columnas dicen en
          qué porcentaje de las {num(s.n_sims, 0)} simulaciones el equipo salió campeón, terminó entre los 4 o los 6
          primeros o descendió. Por ejemplo, {s.teams[0].name} salió campeón en el {prob(s.teams[0].p_champion)} de las
          simulaciones. "—" significa que no pasó en ninguna.
        </p>
        <p className="small muted" style={{ marginTop: 8 }}>
          "Top 4" y "Top 6" son posiciones en la tabla: los cupos europeos exactos dependen también de las copas. No se
          modelan descuentos de puntos ni desempates por cara a cara. Modelo {s.model_version}.
        </p>
      </div>

      <h2 style={{ margin: '32px 0 12px' }}>Todas las posiciones posibles</h2>
      <div className="card"><PositionGrid teams={s.teams} index={byTeam} /></div>

      {s.evaluation && <Evaluation ev={s.evaluation} />}
    </div>
  )
}
