import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { flushSync } from 'react-dom'
import { Link, useSearchParams } from 'react-router-dom'
import { MatchAnalysis, type MatchView } from '../components/MatchAnalysis'
import { FavRing, Odo, PageBand, Reveal, SplitBar, Title } from '../components/Motion'
import { pctInt, reducedMotion } from '../lib/motion'
import { TeamBadge } from '../components/TeamBadge'
import { formatDate, loadData, num, pct, twoSeasonsBefore } from '../lib/data'
import { kitOf, onColor, ring, sideColors } from '../lib/kits'
import { leagueFile, useLeague, useLeagueData } from '../lib/league'
import { useTeamIndex } from '../lib/teams'
import type { MetaFile, TeamFile, TeamIndexItem, UpcomingFile, UpcomingMatch } from '../lib/types'
import './upcoming.css'

const matchKey = (m: UpcomingMatch) => `${m.home_team}|${m.away_team}`

function kickoff(m: UpcomingMatch) {
  if (!m.kickoff_ar) return formatDate(m.date, { weekday: 'short', day: 'numeric', month: 'short' })
  const [d, t] = m.kickoff_ar.split(' ')
  return `${formatDate(d, { weekday: 'short', day: 'numeric', month: 'short' })} · ${t}`
}

/** Colores de los dos lados (camisetas de teams.json; el visitante cambia si se parecen). */
function matchColors(m: UpcomingMatch, teams: Map<string, TeamIndexItem>) {
  return sideColors(kitOf(m.home_name, teams.get(m.home_team)?.colors), kitOf(m.away_name, teams.get(m.away_team)?.colors, '#777777'))
}

const time = (m: UpcomingMatch) => (m.kickoff_ar ? m.kickoff_ar.slice(11) : '—')
const outcomeLabel = (m: UpcomingMatch) =>
  `Gana ${m.home_name} ${pct(m.probabilities.home)}, empate ${pct(m.probabilities.draw)}, gana ${m.away_name} ${pct(m.probabilities.away)}`

/** Análisis completo de un partido de la jornada (carga la evolución del Elo al abrirse). */
function UpcomingDetail({ m, today }: { m: UpcomingMatch; today: string }) {
  const { league } = useLeague()
  const [history, setHistory] = useState<MatchView['eloHistory']>(null)
  useEffect(() => {
    let alive = true
    const since = twoSeasonsBefore(today)
    Promise.all([loadData<TeamFile>(leagueFile(league, `teams/${m.home_slug}.json`)), loadData<TeamFile>(leagueFile(league, `teams/${m.away_slug}.json`))])
      .then(([h, a]) => alive && setHistory({ home: h.elo.filter((p) => p.date >= since), away: a.elo.filter((p) => p.date >= since) }))
      .catch(() => alive && setHistory({ home: [], away: [] }))
    return () => { alive = false }
  }, [m.home_slug, m.away_slug, today, league])
  const view: MatchView = {
    elo: m.elo, lam: m.expected_goals.home, mu: m.expected_goals.away, probabilities: m.probabilities,
    grid: m.score_grid, market: m.market,
    form: { home: m.context.form_home, away: m.context.form_away },
    rest: { home: m.context.rest_home, away: m.context.rest_away },
    h2h: m.context.head_to_head, eloHistory: history,
  }
  return (
    <div className="upcoming-detail">
      <MatchAnalysis view={view} home={m.home_team} away={m.away_team} homeName={m.home_name} awayName={m.away_name}
                     homeSlug={m.home_slug} awaySlug={m.away_slug} />
    </div>
  )
}

/** Resumen del partido abierto: marcador más probable, goles esperados y el salto al análisis completo. */
function PanelSummary({ m, hc, ac, analysisId }: { m: UpcomingMatch; hc: string; ac: string; analysisId: string }) {
  const top = m.top_scores[0]
  const max = Math.max(m.expected_goals.home, m.expected_goals.away, 3)
  const jump = () => {
    const el = document.getElementById(analysisId)
    el?.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' })
    el?.focus({ preventScroll: true })
  }
  return (
    <div className="fx-summary">
      <div className="fx-sum-top">
        <span className="note">Marcador más probable</span>
        <span className="num fx-sum-score">{top.home_goals}-{top.away_goals}</span>
        <span className="note">sale en el {pct(top.probability)} de los casos: lo más probable rara vez es probable.</span>
      </div>
      <div className="fx-sum-xg">
        <span className="note">Goles esperados</span>
        <span className="xg-bars">
          <span className="track"><span style={{ width: `${(m.expected_goals.home / max) * 100}%`, background: hc, boxShadow: ring(hc) }} /></span>
          <span className="num">{num(m.expected_goals.home)}</span>
          <span className="track"><span style={{ width: `${(m.expected_goals.away / max) * 100}%`, background: ac, boxShadow: ring(ac) }} /></span>
          <span className="num">{num(m.expected_goals.away)}</span>
        </span>
      </div>
      <div className="fx-sum-go">
        <span className="note">Grilla de marcadores, Elo, forma, cara a cara y descanso</span>
        <button type="button" className="btn btn-primary" onClick={jump}>Ver análisis →</button>
      </div>
    </div>
  )
}

export function Upcoming() {
  const [params, setParams] = useSearchParams()
  const data = useLeagueData<UpcomingFile>('upcoming.json')
  const meta = useLeagueData<MetaFile>('meta.json')
  const { byTeam } = useTeamIndex()
  const badge = (t: TeamIndexItem | undefined, size: number, className = '') =>
    t ? <TeamBadge badge={t.badge} short={t.short} name={t.name} size={size} colors={t.colors ?? null} decorative className={className} /> : null
  const matchdays = data.data?.matchdays ?? []
  const selected = Number(params.get('jornada')) || matchdays[0]?.matchday
  const md = matchdays.find((x) => x.matchday === selected) ?? matchdays[0]
  const open = params.get('partido')

  const highlights = useMemo(() => {
    if (!md?.matches.length) return null
    const ms = md.matches
    const even = [...ms].sort((a, b) => Math.abs(a.probabilities.home - a.probabilities.away) - Math.abs(b.probabilities.home - b.probabilities.away))[0]
    const fav = [...ms].sort((a, b) => Math.max(b.probabilities.home, b.probabilities.away) - Math.max(a.probabilities.home, a.probabilities.away))[0]
    const goals = [...ms].sort((a, b) => (b.expected_goals.home + b.expected_goals.away) - (a.expected_goals.home + a.expected_goals.away))[0]
    return { even, fav, goals }
  }, [md])

  const setParam = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    Object.entries(patch).forEach(([k, v]) => (v === null ? next.delete(k) : next.set(k, v)))
    setParams(next, { replace: true })
  }
  // Abrir o cerrar un partido: con View Transitions, la fila se expande con continuidad.
  const withTransition = (update: () => void) => {
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown }
    if (doc.startViewTransition && !reducedMotion()) doc.startViewTransition(() => flushSync(update))
    else update()
  }
  const toggle = (m: UpcomingMatch) => withTransition(() => setParam({ partido: open === matchKey(m) ? null : matchKey(m) }))
  const openMatch = (m: UpcomingMatch) => withTransition(() => setParam({ partido: matchKey(m) }))

  // Al abrir un partido (también desde un enlace directo), llevarlo a la vista.
  useEffect(() => {
    if (open) document.getElementById(`m-${open}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [open, md])

  const withMarket = md?.matches.filter((m) => m.market).length ?? 0
  const q = data.data?.quality
  const problems = [...(q?.not_found_in_football_data ?? []), ...(q?.score_mismatches ?? [])]

  // Partidos agrupados por día (el orden de la jornada se mantiene).
  const days = useMemo(() => {
    const out: { date: string; matches: UpcomingMatch[] }[] = []
    for (const m of md?.matches ?? []) {
      const d = m.kickoff_ar?.slice(0, 10) ?? m.date
      const g = out.find((x) => x.date === d)
      if (g) g.matches.push(m)
      else out.push({ date: d, matches: [m] })
    }
    return out
  }, [md])
  const rowIndex = useMemo(() => new Map((md?.matches ?? []).map((m, i) => [matchKey(m), i])), [md])

  const lead = highlights?.fav
  const leadView = lead && (() => {
    const { hc, ac } = matchColors(lead, byTeam)
    const homeFav = lead.probabilities.home >= lead.probabilities.away
    return { hc, ac, homeFav, p: Math.max(lead.probabilities.home, lead.probabilities.away), top: lead.top_scores[0] }
  })()

  return (
    <>
      <PageBand layout="5">
        <div className="hero-main">
          <Title lines={md ? ['Jornada', <Odo key="md" value={md.matchday} base={160} now />] : ['Próximos', 'partidos']} />
          {md && (
            <p className="rise lede" style={{ '--d': '260ms' } as CSSProperties}>
              Del {formatDate(md.from, { weekday: 'long', day: 'numeric', month: 'long' })} al{' '}
              {formatDate(md.to, { weekday: 'long', day: 'numeric', month: 'long' })}. <span className="muted">Horarios de Argentina.</span>
            </p>
          )}
          {md && (
            <p className="rise hero-text" style={{ '--d': '320ms' } as CSSProperties}>
              Abrí cualquier partido para ver el análisis completo: grilla de marcadores, Elo, forma, cara a cara y descanso.
            </p>
          )}
          <div className="rise hero-controls" style={{ '--d': '380ms' } as CSSProperties}>
            {matchdays.length > 1 && (
              <div className="seg tabs" role="tablist" aria-label="Jornadas">
                {matchdays.map((x) => (
                  <button key={x.matchday} role="tab" aria-selected={x.matchday === md?.matchday}
                          onClick={() => setParam({ jornada: String(x.matchday), partido: null })}>
                    Jornada {x.matchday}
                    <span className="tab-date">{formatDate(x.from, { day: 'numeric', month: 'short' })}</span>
                  </button>
                ))}
              </div>
            )}
            <Link className="btn ghost-stack" to="/partidos/previa">
              <strong>Armar una previa →</strong>
              <span>Elegí dos equipos y una fecha, y mirá ese cruce</span>
            </Link>
          </div>
          <span className="rise data-label" style={{ '--d': '420ms' } as CSSProperties}>Próximos partidos · {data.data?.season ?? ''}</span>
        </div>

        <div className="hero-aside">
          {lead && leadView ? (
            <>
              <h2 className="rise lead-title" style={{ '--d': '160ms' } as CSSProperties}>El mayor favorito de la fecha</h2>
              <article className="card lead" aria-label={`${lead.home_name} contra ${lead.away_name}`}>
                <div className="lead-sides">
                  <div className="lead-side from-l" style={{ background: leadView.hc, color: onColor(leadView.hc), '--d': '240ms' } as CSSProperties}>
                    {badge(byTeam.get(lead.home_team), 78, 'lead-med')}
                    <div>
                      <p className="lead-name">{lead.home_name}</p>
                      <p className="lead-meta">Local · {kickoff(lead)}</p>
                    </div>
                  </div>
                  <div className="lead-side lead-away from-r" style={{ background: leadView.ac, color: onColor(leadView.ac), '--d': '240ms' } as CSSProperties}>
                    {badge(byTeam.get(lead.away_team), 78, 'lead-med')}
                    <div>
                      <p className="lead-name">{lead.away_name}</p>
                      <p className="lead-meta">Visitante</p>
                    </div>
                  </div>
                  <FavRing p={leadView.p}>
                    <span className="num fav-p"><Odo value={pctInt(leadView.p)} base={520} now />%</span>
                    <span className="fav-who">gana {leadView.homeFav ? lead.home_name : lead.away_name}</span>
                  </FavRing>
                </div>
                <div className="lead-body">
                  <SplitBar probs={[lead.probabilities.home, lead.probabilities.draw, lead.probabilities.away]} colors={[leadView.hc, leadView.ac]}
                            height={44} font={16} base={560} label={outcomeLabel(lead)} />
                  <div className="bar-legend"><span>Gana {lead.home_name}</span><span>Empate</span><span>Gana {lead.away_name}</span></div>
                  <div className="lead-foot">
                    <span>Más probable <b className="num">{leadView.top.home_goals}-{leadView.top.away_goals}</b> <span className="muted">({pct(leadView.top.probability)})</span></span>
                    <span>Goles esperados <b className="num">{num(lead.expected_goals.home)} – {num(lead.expected_goals.away)}</b></span>
                    <button type="button" className="btn btn-primary lead-cta" onClick={() => openMatch(lead)}>Ver análisis →</button>
                  </div>
                </div>
              </article>
            </>
          ) : data.loading ? <div className="skeleton" style={{ minHeight: 360 }} /> : null}
        </div>
      </PageBand>

      <div className="container page">
        {data.loading && (
          <section aria-busy="true" aria-label="Cargando partidos" className="fx-skeleton">
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="fx-skel-row">
                <span className="skel" /><span className="skel" /><span className="skel skel-bar" /><span className="skel" /><span className="skel" /><span className="skel" />
              </div>
            ))}
          </section>
        )}
        {data.data && !matchdays.length && (
          <p className="callout empty-state">
            No hay partidos pendientes publicados en el calendario (fin de temporada o calendario todavía no disponible).
            Mientras tanto podés armar cualquier cruce en la <Link to="/partidos/previa">Previa</Link>.
          </p>
        )}

        {highlights && (
          <Reveal className="sec" aria-labelledby="datos">
            <h2 id="datos" className="sub-title">Dos datos más de la fecha</h2>
            <div className="grid grid-2">
              {(() => {
                const m = highlights.even
                const { hc, ac } = matchColors(m, byTeam)
                const ps = [m.probabilities.home, m.probabilities.draw, m.probabilities.away]
                return (
                  <button type="button" className="card card-link datum" onClick={() => openMatch(m)}>
                    <h3>El más parejo</h3>
                    <span className="datum-match">{badge(byTeam.get(m.home_team), 30)}<strong>{m.home_name} – {m.away_name}</strong>{badge(byTeam.get(m.away_team), 30)}</span>
                    <span className="num datum-big">
                      <Odo value={pctInt(ps[0])} base={100} /> · <Odo value={pctInt(ps[1])} base={200} /> · <Odo value={pctInt(ps[2])} base={300} />
                    </span>
                    <SplitBar probs={[ps[0], ps[1], ps[2]]} colors={[hc, ac]} height={12} font={11} base={200} label={outcomeLabel(m)} odometer={false} />
                    <span className="note">{pct(ps[0])} · {pct(ps[1])} · {pct(ps[2])}: local, empate y visitante.</span>
                  </button>
                )
              })()}
              {(() => {
                const m = highlights.goals
                const { hc, ac } = matchColors(m, byTeam)
                const max = Math.max(m.expected_goals.home, m.expected_goals.away, 2.5)
                return (
                  <button type="button" className="card card-link datum" onClick={() => openMatch(m)}>
                    <h3>Más goles esperados</h3>
                    <span className="datum-match">{badge(byTeam.get(m.home_team), 30)}<strong>{m.home_name} – {m.away_name}</strong>{badge(byTeam.get(m.away_team), 30)}</span>
                    <span className="datum-total"><span className="num datum-big"><Odo value={num(m.expected_goals.home + m.expected_goals.away, 1)} base={150} /></span> goles en total</span>
                    <span className="xg-bars">
                      <span className="track"><span className="grow-x" style={{ width: `${(m.expected_goals.home / max) * 100}%`, background: hc, boxShadow: ring(hc), '--d': '120ms' } as CSSProperties} /></span>
                      <span className="num">{num(m.expected_goals.home)}</span>
                      <span className="track"><span className="grow-x" style={{ width: `${(m.expected_goals.away / max) * 100}%`, background: ac, boxShadow: ring(ac), '--d': '200ms' } as CSSProperties} /></span>
                      <span className="num">{num(m.expected_goals.away)}</span>
                    </span>
                  </button>
                )
              })()}
            </div>
          </Reveal>
        )}

        {md && (
          <Reveal className="sec" aria-labelledby="todos">
            <div className="section-title fixture-head">
              <h2 id="todos">Todos los partidos</h2>
              <p className="data-label">
                Cuotas del mercado: {withMarket ? `disponibles en ${withMarket} de ${md.matches.length} partidos` : 'todavía no publicadas'}.
                Football-Data las publica pocos días antes de cada fecha; ahí aparece la comparación con el mercado.
              </p>
            </div>
            <div className="fx-cols" aria-hidden="true">
              <span>Hora</span><span className="r">Local</span><span className="c">Gana local · empate · gana visitante</span><span>Visitante</span><span className="r">Más probable</span><span className="r">Goles esp.</span><span />
            </div>
            {days.map((day) => (
              <div key={day.date} className="fx-day">
                <h3 className="day-head"><span className="day-label">{formatDate(day.date, { weekday: 'long', day: 'numeric', month: 'long' })}</span>
                  <span className="num">{day.matches.length} {day.matches.length === 1 ? 'partido' : 'partidos'}</span></h3>
                <ul className="upcoming-list">
                  {day.matches.map((m) => {
                    const isOpen = open === matchKey(m)
                    const top = m.top_scores[0]
                    const i = rowIndex.get(matchKey(m)) ?? 0
                    const { hc, ac } = matchColors(m, byTeam)
                    const p = m.probabilities
                    const favSide = Math.max(p.home, p.away) >= 0.55 ? (p.home > p.away ? 'home' : 'away') : null
                    const note = favSide ? 'favorito' : Math.abs(p.home - p.away) <= 0.04 ? 'parejo' : ''
                    const noteX = favSide === 'home' ? (p.home * 100) / 2 : favSide === 'away' ? 100 - (p.away * 100) / 2 : 50
                    const delay = Math.min(i * 40, 600)
                    const panelId = `panel-${i}`
                    return (
                      <li key={matchKey(m)} id={`m-${matchKey(m)}`}
                          className={`row rise ${isOpen ? 'open' : ''}`}
                          style={{ '--hc': hc, '--ac': ac, '--d': `${delay}ms`, viewTransitionName: `fx-${i}` } as CSSProperties}>
                        <button type="button" className="rowbtn fx-row" onClick={() => toggle(m)} aria-expanded={isOpen} aria-controls={panelId}>
                          <span className="num fx-time">{time(m)}</span>
                          <span className={`fx-team fx-home ${favSide === 'home' ? 'fav' : ''}`}><span className="fx-name">{m.home_name}</span>{badge(byTeam.get(m.home_team), 36, 'med-h')}</span>
                          <span className="fx-bar">
                            {note && <span className="fx-note" style={{ left: `${noteX}%` }}>{note}</span>}
                            <SplitBar probs={[p.home, p.draw, p.away]} colors={[hc, ac]} height={30} base={delay} label={outcomeLabel(m)} />
                            {m.market && <span className="fx-market num" title="Mercado (Bet365, sin margen)">mercado {pct(m.market.home)} · {pct(m.market.draw)} · {pct(m.market.away)}</span>}
                          </span>
                          <span className={`fx-team fx-away ${favSide === 'away' ? 'fav' : ''}`}>{badge(byTeam.get(m.away_team), 36, 'med-a')}<span className="fx-name">{m.away_name}</span></span>
                          <span className="fx-score">
                            <span className="big num" title="Marcador más probable"><b>{top.home_goals}-{top.away_goals}</b> <span className="muted">{pct(top.probability)}</span></span>
                            <span className="more">el más probable</span>
                          </span>
                          <span className="num fx-xg" title="Goles esperados">{num(m.expected_goals.home)} – {num(m.expected_goals.away)}</span>
                          <span className="chev" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 5l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg></span>
                          <span className="sr-only">{kickoff(m)}. {isOpen ? 'Ocultar' : 'Mostrar'} el análisis.</span>
                        </button>
                        {isOpen && (
                          <div id={panelId} className="panel fx-panel">
                            <PanelSummary m={m} hc={hc} ac={ac} analysisId={`analisis-${i}`} />
                            <div id={`analisis-${i}`} tabIndex={-1} className="fx-analysis">
                              <UpcomingDetail m={m} today={meta.data?.as_of ?? m.date} />
                            </div>
                          </div>
                        )}
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}

            <div className="note fx-notes">
              <span>
                Predicción con el estado de los equipos a hoy: si antes del partido se juegan otros (por ejemplo, entre semana),
                el Elo se actualiza y la predicción puede cambiar. Calendario: <a href={data.data?.sources.schedule ?? 'https://github.com/openfootball'} target="_blank" rel="noreferrer">openfootball (dominio público)</a>.
              </span>
            </div>
            {problems.length > 0 && (
              <p className="callout" style={{ marginTop: 12 }}>
                Aviso de calidad de datos: el calendario y los resultados de Football-Data no coinciden en {problems.length} partido(s).
              </p>
            )}
          </Reveal>
        )}
      </div>
    </>
  )
}
