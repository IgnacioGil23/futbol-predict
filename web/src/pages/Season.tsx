import type { CSSProperties, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Odo, PageBand, Reveal, Title } from '../components/Motion'
import { pctInt } from '../lib/motion'
import { TeamBadge } from '../components/TeamBadge'
import { TeamName } from '../components/TeamName'
import { formatDate, num, pct, pct1, REPO } from '../lib/data'
import { kitOf } from '../lib/kits'
import { useLeague, useLeagueData } from '../lib/league'
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
  // Tinta por probabilidad: más intensa cuanto más probable (el número siempre está escrito).
  return (
    <td className="num prob-cell" data-tone={tone} style={{ '--p': Math.min(1, p) } as CSSProperties}>
      <span className="prob-text tabular">{prob(p)}</span>
    </td>
  )
}

const NUMBER_WORD: Record<number, string> = { 1: 'Baja uno', 2: 'Bajan dos', 3: 'Bajan tres', 4: 'Bajan cuatro' }

/** Tramos de la tabla proyectada: la zona de top 6, el resto y, desde el primero con 10% de descender, el descenso. */
function groupsOf(teams: SeasonTeam[], relegation: number) {
  const n = teams.length
  const top = Math.min(6, n)
  let low = teams.findIndex((t, i) => i >= top && (t.p_relegation >= 0.1 || i >= n - relegation))
  if (low < 0) low = n
  const fight = teams.slice(0, top)
  const middle = teams.slice(top, low)
  const bottom = teams.slice(low)
  const contenders = teams.filter((t) => t.p_champion >= 0.01).length
  const maxRel = Math.max(0, ...middle.map((t) => t.p_relegation))
  const worst = [...bottom].sort((a, b) => b.p_relegation - a.p_relegation)[0]
  return [
    { title: 'La pelea', text: `${contenders} ${contenders === 1 ? 'equipo sale' : 'equipos salen'} campeón en al menos el 1% de las simulaciones.`, rows: fight, start: 0 },
    { title: 'La mitad', text: middle.length ? `Ninguno desciende en más del ${prob(maxRel)} de las simulaciones.` : '', rows: middle, start: top },
    { title: 'El descenso', text: worst ? `${NUMBER_WORD[relegation] ?? `Bajan ${relegation}`}. ${worst.name} desciende en el ${prob(worst.p_relegation)} de las simulaciones.` : '', rows: bottom, start: low },
  ].filter((g) => g.rows.length)
}

function PositionGrid({ teams, index, relegation }: { teams: SeasonTeam[]; index: Map<string, TeamIndexItem>; relegation: number }) {
  const n = teams.length
  return (
    <div className="table-wrap">
      <div className="pos-grid" style={{ gridTemplateColumns: `minmax(180px, 2fr) repeat(${n}, minmax(22px, 1fr))` }}
           role="table" aria-label="Probabilidad de cada posición final">
        <div className="pos-head" role="columnheader">Equipo</div>
        {Array.from({ length: n }, (_, i) => (
          <div key={i} className={`pos-head num ${i < 4 ? 'zone-top' : i >= n - relegation ? 'zone-rel' : ''}`} role="columnheader">{i + 1}</div>
        ))}
        {teams.map((t) => (
          <div key={t.slug} className="pos-row" role="row">
            <div className="pos-team" role="rowheader"><TeamName team={index.get(t.team)} name={t.name} size={18} to={`/equipos/${t.slug}`} /></div>
            {t.positions.map((p, i) => (
              <div key={i} className="pos-cell" role="cell" title={`${t.name}: ${prob(p)} de terminar ${i + 1}º`}
                   style={{ '--p': Math.min(1, p / 0.5) } as React.CSSProperties} data-strong={p / 0.5 > 0.55 || undefined}>
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
        uno que todavía puede terminar en muchos lugares. Columnas 1-4 en azul: puestos de top 4; {n - relegation + 1}-{n} en naranja:
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
// Fuera de la Premier los cortes equivalen a la misma proporción de la temporada (100, 200 y 300 de 380 partidos).
const SHARE: Record<number, string> = { 100: '26%', 200: '53%', 300: '79%' }
const CUTOFF_LABEL = (c: number, proportional = false) => (c === 0 ? 'Antes de la fecha 1'
  : proportional ? `Tras el ${SHARE[c] ?? `${c} partidos`} de los partidos` : `Tras ${c} partidos`)

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

export function Evaluation({ ev, id, title, intro }: { ev: SeasonEvaluation; id?: string; title: string; intro?: ReactNode }) {
  const events = ['campeon', 'top4', 'descenso'] as const
  const cutoffs = [...new Set(ev.table.map((r) => r.cutoff))].sort((a, b) => a - b)
  return (
    <section id={id} style={{ marginTop: 32 }}>
      <h2 style={{ marginBottom: 8 }}>{title}</h2>
      {intro}
      <p className="lede" style={{ maxWidth: 820 }}>
        Simulamos las temporadas {ev.seasons[0]} a {ev.seasons[ev.seasons.length - 1]} desde cuatro momentos, cada una
        con el modelo entrenado solo con temporadas anteriores, y comparamos con lo que pasó. La regla se fijó antes de
        mirar los resultados, en el{' '}
        <a href={`${REPO}/blob/main/docs/${ev.cutoffs_label ? 'preregistro_ligas' : 'preregistro_temporada'}.md`}
           target="_blank" rel="noreferrer">preregistro</a>.
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
                  <td>{CUTOFF_LABEL(c, Boolean(ev.cutoffs_label))}</td>
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
  const { data: s, error, loading } = useLeagueData<SeasonFile>('season.json')
  const { byTeam } = useTeamIndex()
  const { league } = useLeague()
  const title = <Title lines={['¿Cómo puede', 'terminar la', 'temporada?']} />
  if (loading) {
    return (
      <>
        <PageBand layout="7"><div className="hero-main">{title}</div><div className="hero-aside"><div className="skeleton" style={{ minHeight: 280 }} /></div></PageBand>
        <div className="container page sec"><div className="skeleton" style={{ minHeight: 400 }} /></div>
      </>
    )
  }
  if (error || !s) {
    return (
      <>
        <PageBand layout="7"><div className="hero-main">{title}</div></PageBand>
        <div className="container page sec"><p className="callout">Todavía no hay una simulación publicada.</p></div>
      </>
    )
  }
  const relegation = s.zones?.relegation ?? 3
  const race = [...s.teams].sort((a, b) => b.p_champion - a.p_champion).slice(0, 4)
  const danger = [...s.teams].sort((a, b) => b.p_relegation - a.p_relegation).slice(0, 4)
  const groups = groupsOf(s.teams, relegation)
  const colorOf = (t: SeasonTeam) => kitOf(t.name, byTeam.get(t.team)?.colors, 'var(--acc)').primary
  const badge = (team: string, name: string, size: number) => {
    const t = byTeam.get(team)
    return t ? <TeamBadge badge={t.badge} short={t.short} name={name} size={size} colors={t.colors ?? null} decorative /> : null
  }
  return (
    <>
      <PageBand layout="7">
        <div className="hero-main">
          {title}
          <p className="rise lede" style={{ '--d': '260ms', maxWidth: 820 } as CSSProperties}>
            Jugamos los <span className="num"><Odo value={s.remaining_matches} now /></span> partidos que faltan {num(s.n_sims, 0)} veces con el modelo. En cada
            simulación, el Elo de los equipos se actualiza con los resultados simulados, así una racha cambia las chances de
            lo que viene, como en la realidad. Desempates: puntos, diferencia de gol y goles a favor.
          </p>
          <span className="rise data-label" style={{ '--d': '320ms' } as CSSProperties}>Temporada {s.season} · actualizada el {formatDate(s.as_of)}</span>
        </div>
        <div className="hero-aside">
          <div className="card season-race rise" style={{ '--d': '240ms' } as CSSProperties}>
            <p className="race-line">
              {race[0].name} salió campeón en el {prob(race[0].p_champion)} de las simulaciones
              {race[1] && race[1].p_champion > 0 ? <>; {race[1].name}, en el {prob(race[1].p_champion)}.</> : '.'}
            </p>
            <ol className="race-rows">
              {race.map((t, i) => (
                <li key={t.slug}>
                  {badge(t.team, t.name, 28)}
                  <span className="race-name">{t.name}</span>
                  <span className="track"><span className="grow-x" style={{ width: `${Math.max(1, t.p_champion * 100)}%`, background: colorOf(t), '--d': `${300 + i * 70}ms` } as CSSProperties} /></span>
                  <span className="num race-v">{prob(t.p_champion)}</span>
                </li>
              ))}
            </ol>
            <p className="race-line">{NUMBER_WORD[relegation] ?? `Bajan ${relegation}`}. {danger[0].name} es el más comprometido.</p>
            <ol className="race-rows">
              {danger.map((t) => (
                <li key={t.slug}>
                  {badge(t.team, t.name, 28)}
                  <span className="race-name">{t.name}</span>
                  <span className="num race-v race-big"><Odo value={pctInt(t.p_relegation)} now />%</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </PageBand>

      <div className="container page">
        <Reveal className="sec" aria-labelledby="proyectada">
          <div className="section-title">
            <h2 id="proyectada">La tabla proyectada</h2>
            <span className="data-label">Ordenada por puntos esperados · % de las {num(s.n_sims, 0)} simulaciones</span>
          </div>
          <div className="table-wrap">
            <table className="table season-table">
              <thead>
                <tr>
                  <th className="num">#</th><th>Equipo</th><th className="num">Pts (PJ)</th><th className="num">Pts esperados</th>
                  <th className="num">Campeón</th><th className="num">Top 4</th><th className="num">Top 6</th><th className="num">Descenso</th>
                </tr>
              </thead>
              {groups.map((g) => (
                <tbody key={g.title}>
                  <tr className="group-row">
                    <th colSpan={8} scope="rowgroup"><span className="group-title">{g.title}</span>{g.text && <span className="group-text">{g.text}</span>}</th>
                  </tr>
                  {g.rows.map((t, i) => (
                    <tr key={t.slug} className="rise" style={{ '--row-c': colorOf(t), '--d': `${Math.min((g.start + i) * 35, 600)}ms` } as CSSProperties}>
                      <td className="num muted">{g.start + i + 1}</td>
                      <td><TeamName team={byTeam.get(t.team)} name={t.name} to={`/equipos/${t.slug}`} size={28} /></td>
                      <td className="num tabular">{t.points} <span className="muted">({t.played})</span></td>
                      <td className="num tabular">{num(t.expected_points, 1)}</td>
                      <ProbCell p={t.p_champion} tone="up" />
                      <ProbCell p={t.p_top4} tone="up" />
                      <ProbCell p={t.p_top6} tone="up" />
                      <ProbCell p={t.p_relegation} tone="down" />
                    </tr>
                  ))}
                </tbody>
              ))}
            </table>
          </div>
          <p className="note" style={{ marginTop: 12 }}>
            <strong>Cómo leerla:</strong> "Pts (PJ)" son los puntos reales hasta hoy y los partidos jugados; "Pts esperados",
            el promedio de puntos al final de la temporada en todas las simulaciones. Las últimas cuatro columnas dicen en
            qué porcentaje de las {num(s.n_sims, 0)} simulaciones el equipo salió campeón, terminó entre los 4 o los 6
            primeros o descendió. Por ejemplo, {s.teams[0].name} salió campeón en el {prob(s.teams[0].p_champion)} de las
            simulaciones. "—" significa que no pasó en ninguna.
          </p>
          <p className="note" style={{ marginTop: 8 }}>
            "Top 4" y "Top 6" son posiciones en la tabla: los cupos europeos exactos dependen también de las copas. No se
            modelan descuentos de puntos.
          </p>
          {s.zones?.playoff ? (
            <p className="note" style={{ marginTop: 8 }}>
              El {s.zones.playoff}.º juega la promoción contra un equipo de {league.second}: no se cuenta como descenso.
            </p>
          ) : null}
          {s.zones?.head_to_head ? (
            <p className="note" style={{ marginTop: 8 }}>
              En {league.competition} el primer desempate es el enfrentamiento directo; la simulación desempata por
              diferencia de gol y goles a favor.
            </p>
          ) : null}
        </Reveal>

        <Reveal className="sec" aria-labelledby="posiciones">
          <div className="section-title"><h2 id="posiciones">Todas las posiciones posibles</h2></div>
          <PositionGrid teams={s.teams} index={byTeam} relegation={relegation} />
        </Reveal>

        {s.evaluation && (
          <p className="note" style={{ marginTop: 24 }}>
            ¿Qué tan confiables son estas probabilidades? <Link to="/metodologia#simulacion">Ver la validación →</Link>
          </p>
        )}
      </div>
    </>
  )
}
