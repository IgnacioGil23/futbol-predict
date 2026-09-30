import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { MatchAnalysis, type MatchView } from '../components/MatchAnalysis'
import { formatDate, loadData, num, pct, twoSeasonsBefore, useData } from '../lib/data'
import type { MetaFile, TeamFile, UpcomingFile, UpcomingMatch } from '../lib/types'
import './upcoming.css'

const matchKey = (m: UpcomingMatch) => `${m.home_team}|${m.away_team}`

function kickoff(m: UpcomingMatch) {
  if (!m.kickoff_ar) return formatDate(m.date, { weekday: 'short', day: 'numeric', month: 'short' })
  const [d, t] = m.kickoff_ar.split(' ')
  return `${formatDate(d, { weekday: 'short', day: 'numeric', month: 'short' })} · ${t}`
}

function MiniBar({ m }: { m: UpcomingMatch }) {
  const p = m.probabilities
  return (
    <div className="mini-bar" role="img" aria-label={`Local ${pct(p.home)}, empate ${pct(p.draw)}, visitante ${pct(p.away)}`}>
      <div className="mini-bar-track" style={{ gridTemplateColumns: `${p.home}fr ${p.draw}fr ${p.away}fr` }}>
        <span style={{ background: 'var(--home)' }} /><span style={{ background: 'var(--draw)' }} /><span style={{ background: 'var(--away)' }} />
      </div>
      <div className="mini-bar-labels tabular">
        <span style={{ color: 'var(--home)' }}>{pct(p.home)}</span>
        <span className="muted">{pct(p.draw)}</span>
        <span style={{ color: 'var(--away)' }}>{pct(p.away)}</span>
      </div>
    </div>
  )
}

/** Análisis completo de un partido de la jornada (carga la evolución del Elo al abrirse). */
function UpcomingDetail({ m, today }: { m: UpcomingMatch; today: string }) {
  const [history, setHistory] = useState<MatchView['eloHistory']>(null)
  useEffect(() => {
    let alive = true
    const since = twoSeasonsBefore(today)
    Promise.all([loadData<TeamFile>(`teams/${m.home_slug}.json`), loadData<TeamFile>(`teams/${m.away_slug}.json`)])
      .then(([h, a]) => alive && setHistory({ home: h.elo.filter((p) => p.date >= since), away: a.elo.filter((p) => p.date >= since) }))
      .catch(() => alive && setHistory({ home: [], away: [] }))
    return () => { alive = false }
  }, [m.home_slug, m.away_slug, today])
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

export function Upcoming() {
  const [params, setParams] = useSearchParams()
  const data = useData<UpcomingFile>('upcoming.json')
  const meta = useData<MetaFile>('meta.json')
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
  const toggle = (m: UpcomingMatch) => setParam({ partido: open === matchKey(m) ? null : matchKey(m) })

  // Al abrir un partido (también desde un enlace directo), llevarlo a la vista.
  useEffect(() => {
    if (open) document.getElementById(`m-${open}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [open, md])

  const withMarket = md?.matches.filter((m) => m.market).length ?? 0
  const q = data.data?.quality
  const problems = [...(q?.not_found_in_football_data ?? []), ...(q?.score_mismatches ?? [])]

  return (
    <div className="container section">
      <div className="section-head">
        <span className="eyebrow">Próximos partidos · {data.data?.season ?? ''}</span>
        <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3.2rem)' }}>{md ? `Jornada ${md.matchday}` : 'Próximos partidos'}</h1>
        {md && (
          <p className="lede">
            Del {formatDate(md.from, { weekday: 'long', day: 'numeric', month: 'long' })} al{' '}
            {formatDate(md.to, { weekday: 'long', day: 'numeric', month: 'long' })}. Horarios de Argentina. Abrí cualquier
            partido para ver el análisis completo: grilla de marcadores, Elo, forma, cara a cara y descanso.
          </p>
        )}
      </div>

      {data.loading && <div className="skeleton" style={{ minHeight: 420 }} />}
      {data.data && !matchdays.length && (
        <p className="callout">
          No hay partidos pendientes publicados en el calendario (fin de temporada o calendario todavía no disponible).
          Mientras tanto podés armar cualquier cruce en la <Link to="/previa">Previa</Link>.
        </p>
      )}

      {matchdays.length > 1 && (
        <div className="tabs" role="tablist" aria-label="Jornadas">
          {matchdays.map((x) => (
            <button key={x.matchday} role="tab" aria-selected={x.matchday === md?.matchday}
                    className={`btn ${x.matchday === md?.matchday ? 'btn-primary' : ''}`}
                    onClick={() => setParam({ jornada: String(x.matchday), partido: null })}>
              Jornada {x.matchday}
              <span className="small" style={{ opacity: 0.75 }}>{formatDate(x.from, { day: 'numeric', month: 'short' })}</span>
            </button>
          ))}
        </div>
      )}

      {highlights && (
        <div className="grid grid-3" style={{ margin: '16px 0' }}>
          {[
            { label: 'El más parejo', m: highlights.even, text: (m: UpcomingMatch) => `${pct(m.probabilities.home)} · ${pct(m.probabilities.draw)} · ${pct(m.probabilities.away)}` },
            { label: 'El mayor favorito', m: highlights.fav, text: (m: UpcomingMatch) => {
                const home = m.probabilities.home >= m.probabilities.away
                return `${home ? m.home_name : m.away_name}: ${pct(Math.max(m.probabilities.home, m.probabilities.away))}`
              } },
            { label: 'Más goles esperados', m: highlights.goals, text: (m: UpcomingMatch) => `${num(m.expected_goals.home + m.expected_goals.away, 1)} goles en total` },
          ].map((h) => (
            <button key={h.label} className="card highlight" onClick={() => setParam({ partido: matchKey(h.m) })}>
              <span className="eyebrow">{h.label}</span>
              <strong>{h.m.home_name} vs {h.m.away_name}</strong>
              <span className="small muted tabular">{h.text(h.m)}</span>
            </button>
          ))}
        </div>
      )}

      {md && (
        <div className="card" style={{ padding: 0 }}>
          <ul className="upcoming-list">
            {md.matches.map((m) => {
              const isOpen = open === matchKey(m)
              const top = m.top_scores[0]
              return (
                <li key={matchKey(m)} id={`m-${matchKey(m)}`} className={isOpen ? 'open' : undefined}>
                  <button className="upcoming-row" onClick={() => toggle(m)} aria-expanded={isOpen}>
                    <span className="u-when small muted tabular">{kickoff(m)}</span>
                    <span className="u-teams">
                      <strong>{m.home_name}</strong> <span className="muted">vs</span> <strong>{m.away_name}</strong>
                    </span>
                    <MiniBar m={m} />
                    <span className="u-meta small tabular">
                      <span title="Goles esperados">{num(m.expected_goals.home)} – {num(m.expected_goals.away)}</span>
                      <span className="muted" title="Marcador más probable">{top.home_goals}-{top.away_goals} ({pct(top.probability)})</span>
                      {m.market && <span className="u-market" title="Mercado (Bet365, sin margen)">mercado {pct(m.market.home)} · {pct(m.market.draw)} · {pct(m.market.away)}</span>}
                    </span>
                    <span className="u-chevron" aria-hidden="true">{isOpen ? '−' : '+'}</span>
                  </button>
                  {isOpen && <UpcomingDetail m={m} today={meta.data?.as_of ?? m.date} />}
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {md && (
        <div className="small muted" style={{ marginTop: 12, display: 'grid', gap: 4 }}>
          <span>
            Cuotas del mercado: {withMarket ? `disponibles en ${withMarket} de ${md.matches.length} partidos` : 'todavía no publicadas'}.
            Football-Data las publica pocos días antes de cada fecha; ahí aparece la comparación con el mercado.
          </span>
          <span>
            Predicción con el estado de los equipos a hoy: si antes del partido se juegan otros (por ejemplo, entre semana),
            el Elo se actualiza y la predicción puede cambiar. Calendario: <a href="https://github.com/openfootball/england" target="_blank" rel="noreferrer">openfootball</a> (dominio público).
          </span>
        </div>
      )}
      {problems.length > 0 && (
        <p className="callout" style={{ marginTop: 12 }}>
          Aviso de calidad de datos: el calendario y los resultados de Football-Data no coinciden en {problems.length} partido(s).
        </p>
      )}
    </div>
  )
}
