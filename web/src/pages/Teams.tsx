import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { EloChart } from '../components/EloChart'
import { FormStrip } from '../components/MatchContext'
import { formatDate, num, pct, useData } from '../lib/data'
import type { StateFile, TeamFile, TeamIndexItem, TeamSeason } from '../lib/types'

export function Teams() {
  const index = useData<TeamIndexItem[]>('teams.json')
  const state = useData<StateFile>('state.json')
  const [query, setQuery] = useState('')
  const current = new Set(state.data?.teams.map((t) => t.team))
  const list = (index.data ?? []).filter((t) => t.name.toLowerCase().includes(query.toLowerCase()))
  const groups = [
    { title: `Temporada ${state.data?.season ?? ''}`, items: list.filter((t) => current.has(t.team)) },
    { title: 'Otros equipos que jugaron la Premier desde 2000-01', items: list.filter((t) => !current.has(t.team)) },
  ]
  return (
    <div className="container section">
      <div className="section-head">
        <span className="eyebrow">Fichas de equipo</span>
        <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3.2rem)' }}>Equipos</h1>
        <p className="lede">Evolución del Elo y rendimiento de cada temporada comparado con la media de la liga.</p>
      </div>
      <div className="field" style={{ maxWidth: 360, marginBottom: 20 }}>
        <label htmlFor="q">Buscar</label>
        <input id="q" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ej.: Arsenal" />
      </div>
      {groups.map((g) => g.items.length > 0 && (
        <section key={g.title} style={{ marginBottom: 28 }}>
          <h3 style={{ marginBottom: 12 }}>{g.title}</h3>
          <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))' }}>
            {g.items.map((t) => (
              <Link key={t.slug} to={`/equipos/${t.slug}`} className="card" style={{ textDecoration: 'none', padding: 14 }}>
                <div style={{ fontWeight: 650 }}>{t.name}</div>
                <div className="small muted">{t.premier_seasons} temporadas en Premier · última {t.last_premier_season}</div>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

function VsLeague({ value, label, goodWhenNegative = false }: { value: number; label: string; goodWhenNegative?: boolean }) {
  const good = goodWhenNegative ? value < 0 : value > 0
  const width = Math.min(100, Math.abs(value) * 100)
  return (
    <div>
      <div style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: '2.4rem', lineHeight: 1, color: good ? 'var(--good)' : 'var(--bad)' }} className="tabular">
        {value > 0 ? '+' : ''}{pct(value)}
      </div>
      <div className="small" style={{ color: 'var(--ink-2)', margin: '4px 0 8px' }}>{label}</div>
      <div style={{ height: 6, background: 'var(--surface-2)', borderRadius: 3 }}>
        <div style={{ width: `${width}%`, height: 6, borderRadius: 3, background: good ? 'var(--good)' : 'var(--bad)' }} />
      </div>
    </div>
  )
}

export function TeamDetail() {
  const { slug } = useParams()
  const team = useData<TeamFile>(slug ? `teams/${slug}.json` : null)
  const state = useData<StateFile>('state.json')
  const [range, setRange] = useState<'3' | 'all'>('3')
  const t = team.data
  const current = state.data?.teams.find((s) => s.slug === slug)
  const series = useMemo(() => {
    if (!t) return []
    if (range === 'all') return t.elo
    const last = t.elo[t.elo.length - 1]?.date ?? ''
    const since = `${Number(last.slice(0, 4)) - 3}${last.slice(4, 10)}`
    return t.elo.filter((p) => p.date >= since)
  }, [t, range])

  if (team.error) return <div className="container section"><p className="callout">No encontramos ese equipo. <Link to="/equipos">Volver a equipos</Link></p></div>
  if (!t) return <div className="container section"><div className="skeleton" style={{ minHeight: 400 }} /></div>

  const seasons = [...t.seasons].reverse()
  const latest: TeamSeason | undefined = seasons[0]
  const latestIsCurrent = latest && state.data && latest.season === state.data.season

  return (
    <div className="container section">
      <div className="section-head">
        <Link to="/equipos" className="small muted">← Equipos</Link>
        <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3.4rem)' }}>{t.name}</h1>
        {current && <p className="lede">Elo actual <strong>{num(current.elo, 0)}</strong>{current.table?.played ? ` · ${current.table.position}º con ${current.table.points} puntos en ${current.table.played} partidos` : ''}.</p>}
      </div>

      {latest && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3>{latestIsCurrent ? `Esta temporada (${latest.season}), hasta ahora` : `Su última temporada en Premier (${latest.season})`}</h3>
          <p className="card-sub">
            Comparado con la media de la liga en esa temporada ({num(latest.league_goals_per_team_game)} goles por equipo y partido).
            {latestIsCurrent && latest.played < 10 && ` Ojo: con ${latest.played} partidos jugados, estos porcentajes todavía se mueven mucho.`}
          </p>
          <div className="grid grid-2">
            <VsLeague value={latest.attack_vs_league_pct}
                      label={`${latest.attack_vs_league_pct >= 0 ? 'más' : 'menos'} goles a favor que el promedio (${num(latest.goals_for_per_game)} por partido)`} />
            <VsLeague value={latest.defence_vs_league_pct} goodWhenNegative
                      label={`${latest.defence_vs_league_pct <= 0 ? 'menos' : 'más'} goles en contra que el promedio (${num(latest.goals_against_per_game)} por partido)`} />
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
          <h3>Evolución del Elo</h3>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className={`btn ${range === '3' ? 'btn-primary' : ''}`} onClick={() => setRange('3')}>3 años</button>
            <button className={`btn ${range === 'all' ? 'btn-primary' : ''}`} onClick={() => setRange('all')}>Desde 2000</button>
          </div>
        </div>
        <EloChart series={[{ name: t.name, color: 'var(--home)', points: series }]} height={280} />
        {range === 'all' && <p className="small muted">2000-2002: período de arranque del Elo (todos los equipos empiezan igual), no se usa para evaluar.</p>}
      </div>

      <div className="grid grid-main">
        <div className="card">
          <h3>Temporadas en Premier League</h3>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Temporada</th><th className="num">Pos.</th><th className="num">Pts</th><th className="num">GF/PJ</th><th className="num">GC/PJ</th><th className="num">Ataque vs liga</th><th className="num">Defensa vs liga</th></tr></thead>
              <tbody>
                {seasons.map((s) => (
                  <tr key={s.season}>
                    <td>{s.season}{s.played < 38 ? <span className="muted"> ({s.played} PJ)</span> : ''}</td>
                    <td className="num">{s.position}º</td>
                    <td className="num">{s.points}</td>
                    <td className="num">{num(s.goals_for_per_game)}</td>
                    <td className="num">{num(s.goals_against_per_game)}</td>
                    <td className="num" style={{ color: s.attack_vs_league_pct > 0 ? 'var(--good)' : 'var(--bad)' }}>{s.attack_vs_league_pct > 0 ? '+' : ''}{pct(s.attack_vs_league_pct)}</td>
                    <td className="num" style={{ color: s.defence_vs_league_pct < 0 ? 'var(--good)' : 'var(--bad)' }}>{s.defence_vs_league_pct > 0 ? '+' : ''}{pct(s.defence_vs_league_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginTop: 8 }}>Defensa: negativo es mejor (recibe menos goles que el promedio). Posición y puntos según resultados en cancha (no incluye descuentos de puntos administrativos).</p>
        </div>
        {current && (
          <div className="card" style={{ alignSelf: 'start' }}>
            <h3>Forma reciente</h3>
            <FormStrip form={current.form} name={t.name} />
            <p className="small muted" style={{ marginTop: 10 }}>Estado al {formatDate(state.data!.as_of)}.</p>
          </div>
        )}
      </div>
    </div>
  )
}
