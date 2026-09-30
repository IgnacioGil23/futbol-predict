import { Link } from 'react-router-dom'
import { formatDate } from '../lib/data'
import type { FormMatch, H2H, Rest } from '../lib/types'

const OUTCOME_LABEL = { G: 'Ganó', E: 'Empató', P: 'Perdió' } as const

export function FormStrip({ form, name }: { form: FormMatch[]; name: string }) {
  if (!form.length) return <p className="small muted">Sin partidos previos en los datos.</p>
  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }} aria-label={`Últimos partidos de ${name}`}>
        {[...form].reverse().map((m) => (
          <span key={m.date} className={`chip chip-${m.outcome}`}
                title={`${formatDate(m.date)} · ${m.home ? 'vs' : 'en'} ${m.opponent} ${m.goals_for}-${m.goals_against}`}>
            {m.outcome}
          </span>
        ))}
      </div>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }} className="small">
        {form.slice(0, 5).map((m) => (
          <li key={m.date} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '3px 0', borderBottom: '1px solid var(--line)' }}>
            <span className="muted tabular">{formatDate(m.date, { day: 'numeric', month: 'short' })}</span>
            <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {m.home ? 'vs' : 'en'} {m.opponent}{m.division === 'E1' ? ' · Champ.' : ''}
            </span>
            <span className="tabular" title={OUTCOME_LABEL[m.outcome]}><strong>{m.goals_for}-{m.goals_against}</strong></span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function RestBlock({ rest, name }: { rest: Rest; name: string }) {
  return (
    <div className="small">
      <div style={{ fontWeight: 650, marginBottom: 2 }}>{name}</div>
      <div className="tabular">
        {rest.days_since_last_match === null ? 'Sin partido previo' : `${rest.days_since_last_match} días desde su último partido de liga`}
      </div>
      <div className="muted tabular">{rest.matches_last_21_days} partidos de liga en los últimos 21 días</div>
    </div>
  )
}

export function H2HBlock({ h2h, homeTeam, homeName, awayName }: { h2h: H2H; homeTeam: string; homeName: string; awayName: string }) {
  if (!h2h.matches) return <p className="small muted">No se enfrentaron en Premier ni Championship desde 2000-01.</p>
  const total = h2h.matches
  const rows = [
    { label: homeName, n: h2h.home_team_wins, color: 'var(--home)' },
    { label: 'Empates', n: h2h.draws, color: 'var(--draw)' },
    { label: awayName, n: h2h.away_team_wins, color: 'var(--away)' },
  ]
  return (
    <div className="small">
      <p className="muted" style={{ marginBottom: 8 }}>{total} partidos de liga desde 2000-01</p>
      {rows.map((r) => (
        <div key={r.label} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 2fr 28px', gap: 8, alignItems: 'center', marginBottom: 4 }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</span>
          <span style={{ background: 'var(--surface-2)', borderRadius: 4, height: 8 }}>
            <span style={{ display: 'block', width: `${(r.n / total) * 100}%`, height: 8, borderRadius: 4, background: r.color }} />
          </span>
          <span className="tabular" style={{ textAlign: 'right' }}>{r.n}</span>
        </div>
      ))}
      <ul style={{ listStyle: 'none', padding: 0, margin: '10px 0 0' }}>
        {h2h.last.slice(0, 5).map((m) => (
          <li key={m.date} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '3px 0', borderBottom: '1px solid var(--line)' }}>
            <span className="muted tabular">{formatDate(m.date, { month: 'short', year: 'numeric' })}</span>
            <span style={{ flex: 1, textAlign: 'right' }}>
              {m.home_team === homeTeam ? <strong>{m.home_team}</strong> : m.home_team} {m.score} {m.away_team === homeTeam ? <strong>{m.away_team}</strong> : m.away_team}
            </span>
          </li>
        ))}
      </ul>
      <p className="muted" style={{ marginTop: 8 }}>
        Contexto, no predicción: el modelo no usa el historial directo porque no mejoró la validación
        (<Link to="/metodologia">ver por qué</Link>).
      </p>
    </div>
  )
}
