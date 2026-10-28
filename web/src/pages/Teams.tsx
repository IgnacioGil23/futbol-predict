import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Link, useParams } from 'react-router-dom'
import { EloChart } from '../components/EloChart'
import { Icon } from '../components/Icon'
import { FormStrip } from '../components/MatchContext'
import { Odo, PageBand, Title } from '../components/Motion'
import { TeamBadge } from '../components/TeamBadge'
import { TeamPreviewPopover, type TeamSeasonSummary } from '../components/TeamPreview'
import { formatDate, num, pct, pct1 } from '../lib/data'
import { kitOf } from '../lib/kits'
import { useLeague, useLeagueData } from '../lib/league'
import { useTeamIndex } from '../lib/teams'
import type { SeasonFile, StateFile, StatsFile, StatsIndex, TeamFile, TeamSeason } from '../lib/types'
import './teams.css'

const delay = (i: number) => ({ '--d': `${Math.min(i * 35, 600)}ms` }) as CSSProperties

/** Tarjeta de un club de la temporada en curso: abre la vista previa con hover, foco o el botón de información. */
function ClubCard({ s, i, onOpen, onLeave, active }: {
  s: TeamSeasonSummary; i: number; active: boolean
  onOpen: (s: TeamSeasonSummary, el: HTMLElement, how: 'hover' | 'focus' | 'tap') => void; onLeave: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const t = s.state.table
  return (
    <div ref={ref} className={`club row rise ${active ? 'active' : ''}`} style={{ ...delay(i), '--hc': kitOf(s.team.name, s.team.colors).primary, '--ac': kitOf(s.team.name, s.team.colors).secondary } as CSSProperties}
         onPointerEnter={(e) => { if (e.pointerType === 'mouse') onOpen(s, ref.current!, 'hover') }}
         onPointerLeave={(e) => { if (e.pointerType === 'mouse') onLeave() }}>
      <Link to={`/equipos/${s.team.slug}`} className="club-card"
            aria-describedby={active ? `tp-${s.team.slug}` : undefined}
            onFocus={(e) => { if (e.currentTarget.matches(':focus-visible')) onOpen(s, ref.current!, 'focus') }}
            onBlur={onLeave}>
        {s.team.stadium && <span className="club-bg" style={{ backgroundImage: active ? `url("${s.team.stadium.image}")` : undefined }} aria-hidden="true" />}
        <span className="club-pos tabular" aria-label={t?.played ? `${t.position}º` : undefined}>{t?.played ? String(t.position).padStart(2, '0') : '–'}</span>
        <TeamBadge badge={s.team.badge} short={s.team.short} name={s.team.name} size={34} colors={s.team.colors ?? null} decorative className="med-h" />
        <span className="club-main">
          <strong>{s.team.name} <span className="club-code">{s.team.short}</span></strong>
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

/** La búsqueda y la vista previa abierta son del estado de la liga: se reinician al cambiar de liga. */
export function Teams() {
  const { league } = useLeague()
  return <TeamsLiga key={league.slug} />
}

function TeamsLiga() {
  const { league } = useLeague()
  const { list, byTeam } = useTeamIndex()
  const state = useLeagueData<StateFile>('state.json')
  const season = useLeagueData<SeasonFile>('season.json')
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
    <>
      <PageBand layout="7">
        <div className="hero-main">
          <Title lines={['Equipos']} />
          <p className="rise lede" style={{ '--d': '260ms' } as CSSProperties}>
            Pasá el mouse por un club para ver su temporada sobre la foto de su estadio; hacé clic para abrir la ficha
            completa con la evolución del Elo y el rendimiento frente a la liga, temporada por temporada.
          </p>
          <span className="rise data-label" style={{ '--d': '320ms' } as CSSProperties}>Fichas de equipo{state.data ? ` · temporada ${state.data.season}` : ''}</span>
        </div>
        <div className="hero-aside">
          <div className="field search teams-search rise" style={{ '--d': '380ms' } as CSSProperties}>
            <label htmlFor="q" className="sr-only">Buscar un equipo</label>
            <Icon name="search" size={17} />
            <input id="q" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar un equipo…" autoComplete="off" />
          </div>
        </div>
      </PageBand>
    <div className="container page">

      {!state.data && <div className="club-grid">{Array.from({ length: 8 }, (_, i) => <div key={i} className="skeleton" style={{ minHeight: 84 }} />)}</div>}

      {shown.length > 0 && (
        <section className="teams-block sec">
          <div className="section-title">
            <h2>Los {state.data?.teams.length} de esta temporada</h2>
            <span className="data-label hover-hint">{league.competition} {state.data?.season} · ordenados por su posición en la tabla</span>
          </div>
          <div className="club-cols" aria-hidden="true"><span>#</span><span>Club</span><span>Puntos · PJ</span></div>
          <div className="club-grid">
            {shown.map((s, i) => (
              <ClubCard key={s.team.slug} s={s} i={i} onOpen={onOpen} onLeave={onLeave} active={open?.s.team.slug === s.team.slug} />
            ))}
          </div>
        </section>
      )}

      {others.length > 0 && (
        <section className="teams-block">
          {/* Con una búsqueda activa se abre: si no, un club histórico que coincide quedaría escondido. */}
          <details className="archive" open={query.trim() !== '' || undefined}>
          <summary>Otros clubes en {league.competition} desde 2000-01 ({others.length})</summary>
          <div className="club-grid club-grid-sm">
            {others.map((t) => (
              <Link key={t.slug} to={`/equipos/${t.slug}`} className="club-card club-card-sm">
                <TeamBadge badge={t.badge} short={t.short} name={t.name} size={30} colors={t.colors ?? null} decorative />
                <span className="club-main">
                  <strong>{t.name}</strong>
                  <span className="small muted">{t.top_seasons} temporadas · última {t.last_top_season}</span>
                </span>
              </Link>
            ))}
          </div>
          </details>
        </section>
      )}
      {state.data && !shown.length && !others.length && <p className="callout">Ningún club coincide con "{query}".</p>}

      {open && (
        <TeamPreviewPopover key={open.s.team.slug} s={open.s} anchor={open.rect} modal={open.modal}
                            onClose={close} onPointerEnter={keep} onPointerLeave={onLeave} />
      )}
    </div>
    </>
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

const ratio = (v: number | null, digits = 2) => (v === null ? '—' : num(v, digits))

/** Detalle de la temporada en curso (local/visitante, por tiempos, entretiempo) según Estadísticas. */
function SeasonDetail({ team }: { team: string }) {
  const index = useLeagueData<StatsIndex>('stats/index.json')
  const current = index.data?.find((x) => x.current)?.season ?? index.data?.[0]?.season
  const { data: s } = useLeagueData<StatsFile>(current ? `stats/${current}.json` : null)
  const t = s?.teams.find((x) => x.team === team)
  if (!s || !t) return null
  const rows = [['Local', t.home], ['Visitante', t.away]] as const
  const { halves: h, ht } = t
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <h3>Esta temporada en detalle</h3>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th></th><th className="num">PJ</th><th className="num">G</th><th className="num">E</th><th className="num">P</th><th className="num">Pts/PJ</th><th className="num">GF</th><th className="num">GC</th></tr>
          </thead>
          <tbody>
            {rows.map(([label, v]) => (
              <tr key={label}>
                <td>{label}</td>
                <td className="num">{v.played}</td><td className="num">{v.won}</td><td className="num">{v.drawn}</td><td className="num">{v.lost}</td>
                <td className="num">{ratio(v.points_per_game)}</td><td className="num">{v.gf}</td><td className="num">{v.ga}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small" style={{ marginTop: 10, color: 'var(--ink-2)' }}>
        Goles por tiempo: 1T {h.gf_1h}-{h.ga_1h} · 2T {h.gf_2h}-{h.ga_2h}
      </p>
      <p className="small" style={{ marginTop: 4, color: 'var(--ink-2)' }}>
        Al entretiempo: ganando {ht.leading.n} (ganó {ht.leading.won}) · empatando {ht.level.n} · perdiendo {ht.trailing.n} (rescató {ht.points_won_trailing} pts)
      </p>
      <p className="small" style={{ marginTop: 8 }}><Link to="/estadisticas">Ver todas las estadísticas →</Link></p>
    </div>
  )
}

export function TeamDetail() {
  const { league } = useLeague()
  const { slug } = useParams()
  const team = useLeagueData<TeamFile>(slug ? `teams/${slug}.json` : null)
  const state = useLeagueData<StateFile>('state.json')
  const season = useLeagueData<SeasonFile>('season.json')
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

  if (team.error) return <div className="container page sec"><p className="callout">No encontramos ese equipo. <Link to="/equipos">Volver a equipos</Link></p></div>
  if (!t) return <div className="container page sec"><div className="skeleton" style={{ minHeight: 400 }} /></div>

  const seasons = [...t.seasons].reverse()
  const latest: TeamSeason | undefined = seasons[0]
  const latestIsCurrent = latest && state.data && latest.season === state.data.season
  const table = current?.table
  const nTeams = state.data?.teams.length ?? 20

  return (
    <>
      <PageBand layout="7" className="team-hero">
        <div className="hero-main">
          <Link to="/equipos" className="hero-back rise"><Icon name="back" size={15} /> Equipos</Link>
          <div className="team-hero-id">
            <span className="rise" style={{ '--d': '120ms' } as CSSProperties}>
              <TeamBadge badge={t.badge} short={t.short} name={t.name} size={104} colors={t.colors ?? null} eager />
            </span>
            <Title lines={[t.name]} />
          </div>
          {t.stadium
            ? <span className="rise data-label" style={{ '--d': '260ms' } as CSSProperties}><Icon name="pin" size={13} /> {t.stadium.name}</span>
            : <span className="rise data-label" style={{ '--d': '260ms' } as CSSProperties}>{t.seasons.length} temporadas en {league.competition} desde 2000-01</span>}
          {current && (
            <dl className="team-hero-stats rise" style={{ '--d': '320ms' } as CSSProperties}>
              {table?.played ? (
                <>
                  <div><dt>Posición</dt><dd><Odo value={`${table.position}º`} now /></dd></div>
                  <div><dt>Puntos</dt><dd><Odo value={num(table.points, 0)} now /><small> en {table.played} PJ</small></dd></div>
                </>
              ) : null}
              <div><dt>Elo</dt><dd><Odo value={num(current.elo, 0)} now />{eloRank && <small> {eloRank}º de {state.data!.teams.length}</small>}</dd></div>
              {sim && <div><dt>Pts esperados</dt><dd><Odo value={num(sim.expected_points, 1)} now /></dd></div>}
              {sim && sim.p_champion >= 0.001 && <div><dt>Campeón</dt><dd><Odo value={sim.p_champion < 0.1 ? pct1(sim.p_champion) : pct(sim.p_champion)} now /></dd></div>}
              {sim && sim.p_champion < 0.001 && sim.p_relegation >= 0.001 && <div><dt>Descenso</dt><dd><Odo value={sim.p_relegation < 0.1 ? pct1(sim.p_relegation) : pct(sim.p_relegation)} now /></dd></div>}
            </dl>
          )}
        </div>
        <div className="hero-aside">
          {t.stadium && (
            <figure className={`team-photo from-r ${imgLoaded ? 'loaded' : ''}`} style={{ '--d': '240ms' } as CSSProperties}>
              <img src={t.stadium.image} alt="" onLoad={() => setImgLoaded(true)} />
            </figure>
          )}
          {(t.stadium || t.badge_credit) && (
            <div className="team-hero-credit data-label">
              {t.stadium && (
                <>
                  <Icon name="camera" size={12} />{' '}
                  <a href={t.stadium.credit.source} target="_blank" rel="noreferrer">{t.stadium.credit.author}</a> ·{' '}
                  <a href={t.stadium.credit.license_url} target="_blank" rel="noreferrer">{t.stadium.credit.license}</a> · Wikimedia Commons
                </>
              )}
              {t.badge_credit && (
                <>
                  {t.stadium ? ' · ' : ''}Escudo:{' '}
                  <a href={t.badge_credit.source} target="_blank" rel="noreferrer">{t.badge_credit.author}</a> ·{' '}
                  <a href={t.badge_credit.license_url} target="_blank" rel="noreferrer">{t.badge_credit.license}</a>
                </>
              )}
            </div>
          )}
        </div>
      </PageBand>

      <div className="container page team-body">
        {latest && (
          <div className="card" style={{ marginBottom: 18 }}>
            <h3>{latestIsCurrent ? `Esta temporada (${latest.season}), hasta ahora` : `Su última temporada en ${league.competition} (${latest.season})`}</h3>
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

        <SeasonDetail team={t.team} />

        <div className="card" style={{ marginBottom: 18 }}>
          <div className="card-head">
            <h3 style={{ margin: 0 }}>Evolución del Elo</h3>
            <div className="seg" role="group" aria-label="Rango">
              <button aria-pressed={range === '3'} onClick={() => setRange('3')}>3 años</button>
              <button aria-pressed={range === 'all'} onClick={() => setRange('all')}>Desde 2000</button>
            </div>
          </div>
          <EloChart series={[{ name: t.name, color: `color-mix(in srgb, ${kitOf(t.name, t.colors, '#888888').primary} 72%, var(--ink))`, points: series }]} height={300} />
          {range === 'all' && <p className="small muted">2000-01 a 2003-04: arranque del Elo (no hay cuotas antes de 2002-03 y todos los equipos de cada división empiezan igual); no se usa para evaluar.</p>}
        </div>

        <div className="grid grid-main">
          <div className="card">
            <h3>Temporadas en {league.competition}</h3>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Temporada</th><th className="num">Pos.</th><th className="num">Pts</th><th className="num">GF/PJ</th><th className="num">GC/PJ</th><th className="num">Ataque vs liga</th><th className="num">Defensa vs liga</th></tr></thead>
                <tbody>
                  {seasons.map((s) => (
                    <tr key={s.season}>
                      <td>{s.season}{s.played < 2 * ((s.teams ?? nTeams) - 1) ? <span className="muted"> ({s.played} PJ)</span> : ''}</td>
                      <td className="num"><span className={`pos-badge ${s.position === 1 ? 'gold' : s.position <= 4 ? 'top' : s.position > (s.teams ?? nTeams) - (s.relegation ?? league.relegation) ? 'rel' : ''}`}>{s.position}º</span></td>
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
