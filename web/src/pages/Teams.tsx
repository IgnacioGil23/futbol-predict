import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CountUp } from '../components/CountUp'
import { EloChart } from '../components/EloChart'
import { Icon } from '../components/Icon'
import { FormStrip } from '../components/MatchContext'
import { TeamBadge } from '../components/TeamBadge'
import { TeamName } from '../components/TeamName'
import { TeamPreviewPopover, type TeamSeasonSummary } from '../components/TeamPreview'
import { XgChart } from '../components/XgChart'
import { formatDate, num, pct, pct1, useData } from '../lib/data'
import { useTeamIndex } from '../lib/teams'
import type { SeasonFile, StateFile, TeamFile, TeamIndexItem, TeamSeason, XgFile, XgSeason } from '../lib/types'
import './teams.css'

const signed = (x: number, digits = 1) => `${x > 0 ? '+' : ''}${num(x, digits)}`
const delay = (d: number) => ({ '--d': d }) as CSSProperties

/** Aclaración que acompaña al xG en toda la web: no son los "goles esperados" del modelo. */
function XgNote() {
  return (
    <p className="small muted" style={{ marginTop: 10 }}>
      El <strong>xG</strong> (expected goals) mide la calidad de las ocasiones según los tiros de cada partido: un xG de 1,5
      equivale a ocasiones que en promedio terminan en 1,5 goles. No es lo mismo que los "goles esperados" de cada
      pronóstico, que el modelo calcula antes del partido con el Elo. Fuente: estadísticas de Fantasy Premier League,
      sumadas por equipo.
    </p>
  )
}

function XgLeagueTable({ data, teams }: { data: XgFile; teams: Map<string, TeamIndexItem> }) {
  const [season, setSeason] = useState(data.seasons[0]?.season)
  const s: XgSeason | undefined = data.seasons.find((x) => x.season === season)
  if (!s) return null
  const maxDiff = Math.max(...s.teams.map((t) => Math.abs(t.xg_for - t.xg_against) / t.played))
  return (
    <section className="card xg-card">
      <div className="xg-head">
        <div>
          <span className="eyebrow">Calidad de las ocasiones</span>
          <h3 style={{ margin: '8px 0 0' }}>Tabla de xG</h3>
        </div>
        <div className="field" style={{ minWidth: 150 }}>
          <label htmlFor="xg-season">Temporada</label>
          <select id="xg-season" value={season} onChange={(e) => setSeason(e.target.value)}>
            {data.seasons.map((x) => <option key={x.season} value={x.season}>{x.season}</option>)}
          </select>
        </div>
      </div>
      <p className="card-sub" style={{ marginTop: 12 }}>
        {s.matches} partidos{s.partial_start ? ` (el xG se registró recién desde el ${formatDate(s.first_date)})` : ''} ·
        promedio de la liga: {num(s.league.xg_per_team_game)} de xG y {num(s.league.goals_per_team_game)} goles por equipo y partido.
        Ordenado por diferencia de xG por partido.
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>#</th><th>Equipo</th><th className="num">PJ</th><th className="num">xG a favor/PJ</th><th className="num">xG en contra/PJ</th>
              <th className="num">Dif. xG/PJ</th><th className="num" title="Goles convertidos menos xG a favor">Goles − xG</th>
              <th className="num" title="Goles recibidos menos xG en contra">Recibidos − xG</th>
            </tr>
          </thead>
          <tbody>
            {s.teams.map((t, i) => {
              const diff = (t.xg_for - t.xg_against) / t.played
              return (
                <tr key={t.slug}>
                  <td className="muted tabular">{i + 1}</td>
                  <td><TeamName team={teams.get(t.team)} name={t.name} to={`/equipos/${t.slug}`} /></td>
                  <td className="num">{t.played}</td>
                  <td className="num">{num(t.xg_for / t.played)}</td>
                  <td className="num">{num(t.xg_against / t.played)}</td>
                  <td className="num">
                    <span className="xg-diff">
                      <span className="xg-diff-bar"><span style={{
                        width: `${(Math.abs(diff) / maxDiff) * 50}%`, [diff >= 0 ? 'left' : 'right']: '50%',
                        background: diff >= 0 ? 'var(--good)' : 'var(--bad)',
                      }} /></span>
                      <strong>{signed(diff, 2)}</strong>
                    </span>
                  </td>
                  <td className="num">{signed(t.goals_for - t.xg_for)}</td>
                  <td className="num">{signed(t.goals_against - t.xg_against)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>
        "Goles − xG" positivo: convirtió más de lo que sus ocasiones anticipaban. "Recibidos − xG" negativo: le hicieron
        menos goles de lo esperado (arquero, defensa o suerte). Esas diferencias suelen achicarse con el tiempo.
      </p>
      <XgNote />
    </section>
  )
}

/** Tarjeta de la ficha de equipo: xG de la temporada más reciente frente a la liga y su evolución. */
function TeamXg({ data, slug, name }: { data: XgFile; slug: string; name: string }) {
  const matches = data.series[slug] ?? []
  const s = data.seasons.find((x) => x.teams.some((t) => t.slug === slug))
  const row = s?.teams.find((t) => t.slug === slug)
  if (!s || !row) return null
  const xf = row.xg_for / row.played
  const xa = row.xg_against / row.played
  const finishing = row.goals_for - row.xg_for
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <h3>Calidad de las ocasiones (xG), {s.season}</h3>
      <p className="card-sub">
        {name} genera {num(xf)} de xG por partido y concede {num(xa)} (promedio de la liga: {num(s.league.xg_per_team_game)}).
        Convirtió {row.goals_for} goles con {num(row.xg_for, 1)} de xG ({signed(finishing)}) en {row.played} partidos.
      </p>
      {matches.length > 0 && <XgChart matches={matches} />}
      <XgNote />
    </div>
  )
}

/** Tarjeta de un club de la temporada en curso: abre la vista previa con hover, foco o el botón de información. */
function ClubCard({ s, i, onOpen, onLeave, active }: {
  s: TeamSeasonSummary; i: number; active: boolean
  onOpen: (s: TeamSeasonSummary, el: HTMLElement, how: 'hover' | 'focus' | 'tap') => void; onLeave: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const t = s.state.table
  return (
    <div ref={ref} className={`club reveal ${active ? 'active' : ''}`} style={delay(Math.min(i, 12))}
         onPointerEnter={(e) => { if (e.pointerType === 'mouse') onOpen(s, ref.current!, 'hover') }}
         onPointerLeave={(e) => { if (e.pointerType === 'mouse') onLeave() }}>
      <Link to={`/equipos/${s.team.slug}`} className="card card-link club-card"
            aria-describedby={active ? `tp-${s.team.slug}` : undefined}
            onFocus={(e) => { if (e.currentTarget.matches(':focus-visible')) onOpen(s, ref.current!, 'focus') }}
            onBlur={onLeave}>
        {s.team.stadium && <span className="club-bg" style={{ backgroundImage: active ? `url("${s.team.stadium.image}")` : undefined }} aria-hidden="true" />}
        <span className="club-pos tabular" aria-label={t?.played ? `${t.position}º` : undefined}>{t?.played ? String(t.position).padStart(2, '0') : '–'}</span>
        <TeamBadge badge={s.team.badge} short={s.team.short} name={s.team.name} size={46} decorative />
        <span className="club-main">
          <strong>{s.team.name}</strong>
          <span className="club-meta small muted tabular">
            <span>{t?.played ? `${t.points} pts · ${t.played} PJ` : `Elo ${num(s.state.elo, 0)}`}</span>
            <span className="club-form" aria-hidden="true">
              {[...s.state.form].reverse().map((m) => <span key={m.date} className={`club-dot chip-${m.outcome}`} />)}
            </span>
          </span>
        </span>
      </Link>
      <button className="club-info" aria-label={`Resumen de la temporada de ${s.team.name}`} onClick={() => onOpen(s, ref.current!, 'tap')}>
        <Icon name="info" size={16} />
      </button>
    </div>
  )
}

export function Teams() {
  const { list, byTeam } = useTeamIndex()
  const state = useData<StateFile>('state.json')
  const season = useData<SeasonFile>('season.json')
  const xg = useData<XgFile>('xg.json')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<{ s: TeamSeasonSummary; rect: DOMRect; modal: boolean } | null>(null)
  const timer = useRef<number | undefined>(undefined)

  const summaries = useMemo(() => {
    if (!state.data) return []
    const byElo = [...state.data.teams].sort((a, b) => b.elo - a.elo)
    return state.data.teams.flatMap((st): TeamSeasonSummary[] => {
      const team = byTeam.get(st.team)
      if (!team) return []
      return [{
        team, state: st, eloRank: byElo.indexOf(st) + 1, teamsInLeague: byElo.length,
        sim: season.data?.teams.find((x) => x.team === st.team) ?? null, nSims: season.data?.n_sims ?? null,
        season: state.data!.season,
      }]
    }).sort((a, b) => (a.state.table?.played && b.state.table?.played
      ? a.state.table.position - b.state.table.position : a.team.name.localeCompare(b.team.name)))
  }, [state.data, season.data, byTeam])

  const q = query.trim().toLowerCase()
  const current = new Set(state.data?.teams.map((t) => t.team))
  const shown = summaries.filter((s) => s.team.name.toLowerCase().includes(q))
  const others = list.filter((t) => !current.has(t.team) && t.name.toLowerCase().includes(q))

  const close = useCallback(() => { window.clearTimeout(timer.current); setOpen(null) }, [])
  const onOpen = useCallback((s: TeamSeasonSummary, el: HTMLElement, how: 'hover' | 'focus' | 'tap') => {
    window.clearTimeout(timer.current)
    const show = () => setOpen({ s, rect: el.getBoundingClientRect(), modal: how === 'tap' })
    if (how === 'hover') timer.current = window.setTimeout(show, 160)   // intención: no abrir al solo cruzar la grilla
    else show()
  }, [])
  const onLeave = useCallback(() => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setOpen((o) => (o?.modal ? o : null)), 180)
  }, [])
  const keep = useCallback(() => window.clearTimeout(timer.current), [])
  useEffect(() => () => window.clearTimeout(timer.current), [])

  return (
    <div className="container section">
      <div className="section-head">
        <span className="eyebrow">Fichas de equipo{state.data ? ` · temporada ${state.data.season}` : ''}</span>
        <h1>Equipos</h1>
        <p className="lede">
          Pasá el mouse por un club para ver su temporada sobre la foto de su estadio; hacé clic para abrir la ficha
          completa con la evolución del Elo, el rendimiento frente a la liga y la calidad de sus ocasiones (xG).
        </p>
        <div className="field search teams-search">
          <label htmlFor="q" className="sr-only">Buscar un equipo</label>
          <Icon name="search" size={17} />
          <input id="q" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar un equipo…" autoComplete="off" />
        </div>
      </div>

      {!state.data && <div className="club-grid">{Array.from({ length: 8 }, (_, i) => <div key={i} className="skeleton" style={{ minHeight: 84 }} />)}</div>}

      {shown.length > 0 && (
        <section className="teams-block">
          <div className="section-title">
            <div>
              <span className="eyebrow">Premier League {state.data?.season}</span>
              <h2>Los 20 de esta temporada</h2>
            </div>
            <span className="small muted hover-hint"><Icon name="info" size={15} /> Ordenados por su posición en la tabla</span>
          </div>
          <div className="club-grid">
            {shown.map((s, i) => (
              <ClubCard key={s.team.slug} s={s} i={i} onOpen={onOpen} onLeave={onLeave} active={open?.s.team.slug === s.team.slug} />
            ))}
          </div>
        </section>
      )}

      {!q && xg.data && xg.data.seasons.length > 0 && <XgLeagueTable data={xg.data} teams={byTeam} />}

      {others.length > 0 && (
        <section className="teams-block">
          <div className="section-title">
            <div>
              <span className="eyebrow">Archivo</span>
              <h2>Otros clubes en la Premier desde 2000-01</h2>
            </div>
          </div>
          <div className="club-grid club-grid-sm">
            {others.map((t) => (
              <Link key={t.slug} to={`/equipos/${t.slug}`} className="card card-link club-card club-card-sm">
                <TeamBadge badge={t.badge} short={t.short} name={t.name} size={34} decorative />
                <span className="club-main">
                  <strong>{t.name}</strong>
                  <span className="small muted">{t.premier_seasons} temporadas · última {t.last_premier_season}</span>
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}
      {state.data && !shown.length && !others.length && <p className="callout">Ningún club coincide con "{query}".</p>}

      {open && (
        <TeamPreviewPopover key={open.s.team.slug} s={open.s} anchor={open.rect} modal={open.modal}
                            onClose={close} onPointerEnter={keep} onPointerLeave={onLeave} />
      )}
    </div>
  )
}

function VsLeague({ value, label, goodWhenNegative = false }: { value: number; label: string; goodWhenNegative?: boolean }) {
  const good = goodWhenNegative ? value < 0 : value > 0
  const width = Math.min(100, Math.abs(value) * 100)
  const color = good ? 'var(--good)' : 'var(--bad)'
  return (
    <div className="vs-league">
      <div className="vs-league-num tabular" style={{ color }}>{value > 0 ? '+' : ''}{pct(value)}</div>
      <div className="small" style={{ color: 'var(--ink-2)', margin: '4px 0 10px' }}>{label}</div>
      <div className="vs-league-track"><div style={{ width: `${width}%`, background: color }} /></div>
    </div>
  )
}

export function TeamDetail() {
  const { slug } = useParams()
  const team = useData<TeamFile>(slug ? `teams/${slug}.json` : null)
  const state = useData<StateFile>('state.json')
  const season = useData<SeasonFile>('season.json')
  const xg = useData<XgFile>('xg.json')
  const [range, setRange] = useState<'3' | 'all'>('3')
  const [imgLoaded, setImgLoaded] = useState(false)
  const t = team.data
  const current = state.data?.teams.find((s) => s.slug === slug)
  const sim = season.data?.teams.find((s) => s.slug === slug)
  const eloRank = current && state.data ? [...state.data.teams].sort((a, b) => b.elo - a.elo).indexOf(current) + 1 : null
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
  const table = current?.table

  return (
    <>
      <section className={`team-hero ${t.stadium ? 'has-img' : ''}`}>
        {t.stadium && (
          <img className={`team-hero-img ${imgLoaded ? 'loaded' : ''}`} src={t.stadium.image} alt="" onLoad={() => setImgLoaded(true)} />
        )}
        <div className="team-hero-shade" />
        <div className="container team-hero-inner">
          <Link to="/equipos" className="back-link small"><Icon name="back" size={15} /> Equipos</Link>
          <div className="team-hero-id reveal">
            <TeamBadge badge={t.badge} short={t.short} name={t.name} size={104} eager />
            <div>
              {t.stadium
                ? <span className="team-hero-stadium"><Icon name="pin" size={14} /> {t.stadium.name}</span>
                : <span className="eyebrow">{t.seasons.length} temporadas en Premier desde 2000-01</span>}
              <h1>{t.name}</h1>
            </div>
          </div>
          {current && (
            <dl className="team-hero-stats reveal" style={delay(2)}>
              {table?.played ? (
                <>
                  <div><dt>Posición</dt><dd><CountUp value={table.position} format={(x) => `${Math.round(x)}º`} /></dd></div>
                  <div><dt>Puntos</dt><dd><CountUp value={table.points} format={(x) => num(x, 0)} /><small> en {table.played} PJ</small></dd></div>
                </>
              ) : null}
              <div><dt>Elo</dt><dd><CountUp value={current.elo} format={(x) => num(x, 0)} />{eloRank && <small> {eloRank}º de {state.data!.teams.length}</small>}</dd></div>
              {sim && <div><dt>Pts esperados</dt><dd><CountUp value={sim.expected_points} format={(x) => num(x, 1)} /></dd></div>}
              {sim && sim.p_champion >= 0.001 && <div><dt>Campeón</dt><dd><CountUp value={sim.p_champion} format={(x) => (sim.p_champion < 0.1 ? pct1(x) : pct(x))} /></dd></div>}
              {sim && sim.p_champion < 0.001 && sim.p_relegation >= 0.001 && <div><dt>Descenso</dt><dd><CountUp value={sim.p_relegation} format={(x) => (sim.p_relegation < 0.1 ? pct1(x) : pct(x))} /></dd></div>}
            </dl>
          )}
        </div>
        {t.stadium && (
          <div className="team-hero-credit">
            <Icon name="camera" size={12} />
            <a href={t.stadium.credit.source} target="_blank" rel="noreferrer">{t.stadium.credit.author}</a> ·{' '}
            <a href={t.stadium.credit.license_url} target="_blank" rel="noreferrer">{t.stadium.credit.license}</a> · Wikimedia Commons
          </div>
        )}
      </section>

      <div className="container section team-body">
        {latest && (
          <div className="card" style={{ marginBottom: 18 }}>
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

        {xg.data && slug && <TeamXg data={xg.data} slug={slug} name={t.name} />}

        <div className="card" style={{ marginBottom: 18 }}>
          <div className="card-head">
            <h3 style={{ margin: 0 }}>Evolución del Elo</h3>
            <div className="seg" role="group" aria-label="Rango">
              <button aria-pressed={range === '3'} onClick={() => setRange('3')}>3 años</button>
              <button aria-pressed={range === 'all'} onClick={() => setRange('all')}>Desde 2000</button>
            </div>
          </div>
          <EloChart series={[{ name: t.name, color: 'var(--home)', points: series }]} height={300} />
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
                      <td className="num"><span className={`pos-badge ${s.position === 1 ? 'gold' : s.position <= 4 ? 'top' : s.position >= 18 ? 'rel' : ''}`}>{s.position}º</span></td>
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
            <p className="small muted" style={{ marginTop: 10 }}>Defensa: negativo es mejor (recibe menos goles que el promedio). Posición y puntos según resultados en cancha (no incluye descuentos de puntos administrativos).</p>
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
    </>
  )
}
