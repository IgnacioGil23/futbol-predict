import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { Odo, PageBand, Reveal, SplitBar, Title } from '../components/Motion'
import { TeamBadge } from '../components/TeamBadge'
import { TeamName } from '../components/TeamName'
import { formatDate, num, pct, pct1 } from '../lib/data'
import { kitOf, onColor, sideColors } from '../lib/kits'
import { useLeague, useLeagueData } from '../lib/league'
import { forecast, topScores } from '../lib/model'
import { useTeamIndex } from '../lib/teams'
import type {
  MetaFile, ModelFile, Probabilities, ReviewSeasonSummary, SeasonFile, StateFile, StatsFile, StatsIndex, TeamIndexItem, UpcomingFile,
  UpcomingMatch,
} from '../lib/types'
import './home.css'

const delay = (ms: number) => ({ '--d': `${ms}ms` }) as CSSProperties

/** "sáb 11 oct · 08:30" (hora argentina) o solo la fecha si no hay horario. */
function when(date: string, kickoff: string | null, long = false) {
  const opts: Intl.DateTimeFormatOptions = long ? { weekday: 'long', day: 'numeric', month: 'long' } : { weekday: 'short', day: 'numeric', month: 'short' }
  return `${formatDate(date, opts)}${kickoff ? ` · ${kickoff.slice(11)}` : ''}`
}

interface Featured {
  home: string; away: string; homeName: string; awayName: string
  probs: Probabilities; market: Probabilities | null; lam: number; mu: number
  elo: { home: number; away: number }
  scores: { home: number; away: number; p: number }[]
  label: string; date: string | null; kickoff: string | null; href: string
}

function colorsFor(home: string, away: string, homeName: string, awayName: string, teams: Map<string, TeamIndexItem>) {
  return sideColors(kitOf(homeName, teams.get(home)?.colors), kitOf(awayName, teams.get(away)?.colors, '#777777'))
}

function MatchPoster({ f, teams }: { f: Featured; teams: Map<string, TeamIndexItem> }) {
  const { hc, ac } = colorsFor(f.home, f.away, f.homeName, f.awayName, teams)
  const side = (team: string, name: string, elo: number, color: string, cls: string) => {
    const t = teams.get(team)
    return (
      <div className={`lead-side ${cls}`} style={{ background: color, color: onColor(color), '--d': '240ms' } as CSSProperties}>
        {t ? <TeamBadge badge={t.badge} short={t.short} name={name} size={72} colors={t.colors ?? null} eager decorative /> : null}
        <div>
          <p className="lead-name">{name}</p>
          <p className="lead-meta">Elo {num(elo, 0)}</p>
        </div>
      </div>
    )
  }
  return (
    <>
      <h2 className="rise lead-title" style={delay(160)}>{f.label}</h2>
      <article className="card lead poster" aria-label={`${f.homeName} contra ${f.awayName}`}>
        <div className="lead-sides">
          {side(f.home, f.homeName, f.elo.home, hc, 'from-l')}
          {side(f.away, f.awayName, f.elo.away, ac, 'lead-away from-r')}
          <div className="poster-mid rise" style={delay(420)}>
            <span className="poster-vs">VS</span>
            <span className="num poster-xg">{num(f.lam)} – {num(f.mu)}</span>
            <span className="poster-xg-label">goles esperados</span>
          </div>
        </div>
        <div className="lead-body">
          {f.date && <span className="data-label">{when(f.date, f.kickoff, true)}</span>}
          <SplitBar probs={[f.probs.home, f.probs.draw, f.probs.away]} colors={[hc, ac]} height={44} font={16} base={560}
                    label={`Local ${pct(f.probs.home)}, empate ${pct(f.probs.draw)}, visitante ${pct(f.probs.away)}`} />
          <div className="bar-legend"><span>{f.homeName}</span><span>Empate</span><span>{f.awayName}</span></div>
          <div className="poster-scores">
            <span className="note">Marcadores más probables</span>
            <div className="poster-score-list">
              {f.scores.map((s, i) => (
                <div key={`${s.home}-${s.away}`} className={`poster-score ${i === 0 ? 'top' : ''}`}>
                  <span className="num">{s.home}–{s.away}</span>
                  <small className="num">{pct1(s.p)}</small>
                </div>
              ))}
            </div>
          </div>
          {f.market && (
            <p className="note">
              Mercado: {pct(f.market.home)} · {pct(f.market.draw)} · {pct(f.market.away)} (Bet365, sin margen)
            </p>
          )}
          <div className="lead-foot">
            <Link className="btn btn-primary lead-cta" to={f.href}>Ver el análisis completo →</Link>
          </div>
        </div>
      </article>
    </>
  )
}

function FixtureCard({ m, matchday, teams, i }: { m: UpcomingMatch; matchday: number; teams: Map<string, TeamIndexItem>; i: number }) {
  const p = m.probabilities
  const top = m.top_scores[0]
  const fav = p.home >= p.away ? 'home' : 'away'
  const { hc, ac } = colorsFor(m.home_team, m.away_team, m.home_name, m.away_name, teams)
  const row = (team: string, name: string, prob: number, isFav: boolean, cls: string) => {
    const t = teams.get(team)
    return (
      <div className={`hf-team ${isFav ? 'fav' : ''}`}>
        {t && <TeamBadge badge={t.badge} short={t.short} name={name} size={28} colors={t.colors ?? null} decorative className={cls} />}
        <span className="hf-name">{name}</span>
        <span className="hf-pct num">{pct(prob)}</span>
      </div>
    )
  }
  return (
    <Link className="row hf rise" style={{ ...delay(Math.min(i * 40, 600)), '--hc': hc, '--ac': ac } as CSSProperties}
          to={`/partidos?jornada=${matchday}&partido=${encodeURIComponent(`${m.home_team}|${m.away_team}`)}`}>
      <div className="hf-when data-label">{when(m.date, m.kickoff_ar)}</div>
      {row(m.home_team, m.home_name, p.home, fav === 'home', 'med-h')}
      {row(m.away_team, m.away_name, p.away, fav === 'away', 'med-a')}
      <SplitBar probs={[p.home, p.draw, p.away]} colors={[hc, ac]} height={22} font={11} base={Math.min(i * 40, 360)} odometer={false}
                label={`Local ${pct(p.home)}, empate ${pct(p.draw)}, visitante ${pct(p.away)}`} />
      <div className="hf-foot note">
        <span>Empate <strong className="num">{pct(p.draw)}</strong></span>
        <span>Más probable <strong className="num big">{top.home_goals}-{top.away_goals}</strong></span>
      </div>
    </Link>
  )
}

interface RaceRow { team: string; name: string; value: number; label: string; width: number }

function Race({ title, eyebrow, rows, color, teams, foot, to }: {
  title: string; eyebrow: string; rows: RaceRow[]; color: string; teams: Map<string, TeamIndexItem>; foot: string; to: string
}) {
  return (
    <div className="card race">
      <h3>{title}</h3>
      <span className="data-label">{eyebrow}</span>
      <ol className="race-list">
        {rows.map((r, i) => (
          <li key={r.team}>
            <span className="race-rank num">{i + 1}</span>
            <TeamName team={teams.get(r.team)} name={r.name} size={24} className="race-team" />
            <span className="track race-bar"><span className="grow-x" style={{ width: `${Math.max(2, r.width * 100)}%`, background: color, '--d': `${120 + i * 70}ms` } as CSSProperties} /></span>
            <span className="race-val num">{r.label}</span>
          </li>
        ))}
      </ol>
      <div className="race-foot">
        <span className="note">{foot}</span>
        <Link className="race-link" to={to}>Ver todo <Icon name="arrow" size={14} /></Link>
      </div>
    </div>
  )
}

/** "Datos de la temporada": tres datos curiosos de la temporada en curso, tomados de Estadísticas. */
function SeasonData({ teams }: { teams: Map<string, TeamIndexItem> }) {
  const index = useLeagueData<StatsIndex>('stats/index.json')
  const current = index.data?.find((x) => x.current)?.season ?? index.data?.[0]?.season
  const { data: s } = useLeagueData<StatsFile>(current ? `stats/${current}.json` : null)
  if (!s) return null
  const link = (team: string) => {
    const t = teams.get(team)
    return t ? <Link to={`/equipos/${t.slug}`}>{t.name}</Link> : team
  }
  let over: { team: string; diff: number } | null = null
  let rescue: { team: string; points: number } | null = null
  for (const t of s.teams) {
    const d = t.market.difference
    if (d !== null && d > 0 && (!over || d > over.diff)) over = { team: t.team, diff: d }
    if (t.ht.points_won_trailing > 0 && (!rescue || t.ht.points_won_trailing > rescue.points)) rescue = { team: t.team, points: t.ht.points_won_trailing }
  }
  const gpm = s.league.goals_per_match
  const ref = s.league_reference.goals_per_match
  const avgPlayed = s.teams.length ? s.teams.reduce((a, t) => a + t.played, 0) / s.teams.length : 0
  return (
    <Reveal className="container sec home-section">
      <div className="section-title">
        <h2>Datos de la temporada</h2>
        <Link className="btn" to="/estadisticas">Ver todas las estadísticas →</Link>
      </div>
      <p className="data-label home-sub">Estadísticas · temporada {s.season}</p>
      <div className="grid grid-3">
        <div className="card datum-card">
          <span className="note">Goles por partido</span>
          <strong className="big-num">{gpm === null ? '—' : <Odo value={num(gpm, 2)} />}</strong>
          <span className="note">Promedio histórico: {ref === null ? '—' : num(ref, 2)}</span>
        </div>
        {over && (
          <div className="card datum-card">
            <span className="note">Suma más de lo que esperaba el mercado</span>
            <strong className="datum-team">{link(over.team)}</strong>
            <strong className="num">+{num(over.diff, 1)} puntos</strong>
            <span className="note">Puntos reales contra los que le daban las cuotas antes de cada partido</span>
          </div>
        )}
        {rescue && (
          <div className="card datum-card">
            <span className="note">Rescata puntos yendo abajo</span>
            <strong className="datum-team">{link(rescue.team)}</strong>
            <strong className="num">{rescue.points} puntos rescatados</strong>
            <span className="note">Sumados en partidos que perdía al entretiempo</span>
          </div>
        )}
      </div>
      {avgPlayed < 10 && (
        <p className="note" style={{ marginTop: 10 }}>
          Con {num(avgPlayed, 0)} partidos por equipo, estas diferencias todavía pueden ser casualidad.
        </p>
      )}
    </Reveal>
  )
}

export function Home() {
  const { league } = useLeague()
  const meta = useLeagueData<MetaFile>('meta.json')
  const state = useLeagueData<StateFile>('state.json')
  const model = useLeagueData<ModelFile>('model.json')
  const upcoming = useLeagueData<UpcomingFile>('upcoming.json')
  const season = useLeagueData<SeasonFile>('season.json')
  const review = useLeagueData<ReviewSeasonSummary[]>('review/index.json')
  const { byTeam } = useTeamIndex()

  const teams = [...(state.data?.teams ?? [])].sort((a, b) => b.elo - a.elo)
  const nextMd = upcoming.data?.matchdays[0]
  // Partido destacado: el "partido grande" de la próxima jornada (mayor Elo combinado) o,
  // si no hay calendario, el cruce de los dos mejores por Elo.
  const fixture = nextMd ? [...nextMd.matches].sort((a, b) => (b.elo.home + b.elo.away) - (a.elo.home + a.elo.away))[0] : undefined
  let featured: Featured | null = null
  if (fixture && nextMd) {
    featured = {
      home: fixture.home_team, away: fixture.away_team, homeName: fixture.home_name, awayName: fixture.away_name,
      probs: fixture.probabilities, market: fixture.market, lam: fixture.expected_goals.home, mu: fixture.expected_goals.away,
      elo: fixture.elo, scores: fixture.top_scores.slice(0, 3).map((s) => ({ home: s.home_goals, away: s.away_goals, p: s.probability })),
      label: `Partido destacado · jornada ${nextMd.matchday}`, date: fixture.date, kickoff: fixture.kickoff_ar,
      href: `/partidos?jornada=${nextMd.matchday}&partido=${encodeURIComponent(`${fixture.home_team}|${fixture.away_team}`)}`,
    }
  } else if (teams.length >= 2 && model.data) {
    const f = forecast(model.data.params, teams[0].elo, teams[1].elo)
    featured = {
      home: teams[0].team, away: teams[1].team, homeName: teams[0].name, awayName: teams[1].name,
      probs: f.probabilities, market: null, lam: f.lam, mu: f.mu, elo: { home: teams[0].elo, away: teams[1].elo },
      scores: topScores(f.grid, 3), label: 'Si se enfrentaran hoy', date: null, kickoff: null,
      href: `/partidos/previa?home=${encodeURIComponent(teams[0].team)}&away=${encodeURIComponent(teams[1].team)}`,
    }
  }

  const tm = meta.data?.model.test_metrics
  const gap = tm ? tm.model.log_loss - tm.bet365_pre_closing.log_loss : 0   // > 0: el mercado predice mejor
  const reviewed = review.data?.reduce((s, x) => s + x.matches, 0)
  const sim = season.data
  const eloMax = teams[0]?.elo ?? 0
  const eloMin = teams[teams.length - 1]?.elo ?? 0
  const champ = sim ? [...sim.teams].sort((a, b) => b.p_champion - a.p_champion).slice(0, 5) : []
  const releg = sim ? [...sim.teams].sort((a, b) => b.p_relegation - a.p_relegation).slice(0, 5) : []
  const probLabel = (p: number) => (p === 0 ? '—' : p < 0.001 ? '<0,1%' : p < 0.1 ? pct1(p) : pct(p))

  return (
    <>
      <PageBand layout="full">
        <div className="hero-main">
          <Title lines={['Cada marcador,', 'con su', 'probabilidad.']} />
        </div>
        <div className="home-hero-copy">
          <p className="lede rise" style={delay(260)}>
            Un modelo de Machine Learning calcula la probabilidad de cada resultado de la Premier League, LaLiga, la Serie A, la Bundesliga y la Ligue 1.
            Lo comparamos en vivo con el mercado de apuestas.
          </p>
          <div className="hero-controls rise" style={delay(320)}>
            <Link className="btn btn-primary" to="/partidos">Ver la próxima jornada →</Link>
            <Link className="btn ghost-stack" to="/partidos/previa">
              <strong>Armar una previa →</strong>
              <span>Elegí dos equipos y una fecha, y mirá ese cruce</span>
            </Link>
          </div>
          <span className="data-label rise" style={delay(380)}>
            {state.data ? `Temporada ${state.data.season} · datos al ${formatDate(meta.data?.last_match_in_data ?? state.data.as_of)}` : league.competition}
          </span>
          {tm && meta.data && (
            <dl className="hero-stats rise" style={delay(420)}>
              <div>
                <dt>Partidos de entrenamiento</dt>
                <dd className="num"><Odo value={num(meta.data.model.trained_on.matches, 0)} now /></dd>
              </div>
              {reviewed ? (
                <div>
                  <dt>Predicciones fuera de muestra</dt>
                  <dd className="num"><Odo value={num(reviewed, 0)} now /></dd>
                </div>
              ) : null}
              <div>
                <dt>Resultado acertado (test)</dt>
                <dd className="num"><Odo value={pct(tm.model.accuracy)} now /></dd>
              </div>
            </dl>
          )}
        </div>
        <div className="home-hero-aside">
          {featured ? <MatchPoster f={featured} teams={byTeam} /> : <div className="skeleton" style={{ minHeight: 480 }} />}
        </div>
      </PageBand>

      <div className="page">
        {nextMd && (
          <Reveal className="container sec home-section">
            <div className="section-title">
              <h2>Jornada {nextMd.matchday}</h2>
              <Link className="btn" to="/partidos">La jornada completa →</Link>
            </div>
            <p className="data-label home-sub">
              Próximos partidos · {formatDate(nextMd.from, { weekday: 'long', day: 'numeric', month: 'long' })} al{' '}
              {formatDate(nextMd.to, { weekday: 'long', day: 'numeric', month: 'long' })} · horarios de Argentina
            </p>
            <div className="hf-grid">
              {nextMd.matches.map((m, i) => <FixtureCard key={`${m.home_team}-${m.away_team}`} m={m} matchday={nextMd.matchday} teams={byTeam} i={i} />)}
            </div>
          </Reveal>
        )}
        {upcoming.data && !nextMd && (
          <section className="container sec home-section">
            <p className="callout">
              No hay partidos pendientes publicados en el calendario. Mientras tanto, podés armar cualquier cruce en la{' '}
              <Link to="/partidos/previa">previa</Link>.
            </p>
          </section>
        )}

        <Reveal className="container sec home-section">
          <div className="section-title">
            <h2>Cómo viene {league.competition}</h2>
            <Link className="btn" to="/temporada">Todas las posiciones →</Link>
          </div>
          <p className="data-label home-sub">{sim ? `${num(sim.n_sims, 0)} simulaciones de la temporada` : 'La temporada'}</p>
          <div className="grid grid-3">
            {sim ? (
              <>
                <Race eyebrow="Campeón" title="La carrera por el título" color="var(--acc)" teams={byTeam} to="/temporada"
                      rows={champ.map((t) => ({ team: t.team, name: t.name, value: t.p_champion, label: probLabel(t.p_champion), width: t.p_champion / champ[0].p_champion }))}
                      foot="Probabilidad de terminar primero" />
                <Race eyebrow="Descenso" title="Pelea por no descender" color="var(--away)" teams={byTeam} to="/temporada"
                      rows={releg.map((t) => ({ team: t.team, name: t.name, value: t.p_relegation, label: probLabel(t.p_relegation), width: t.p_relegation / releg[0].p_relegation }))}
                      foot={`Probabilidad de terminar ${sim.teams.length - (sim.zones?.relegation ?? 3) + 1}º a ${sim.teams.length}º`} />
              </>
            ) : (
              <><div className="skeleton" style={{ minHeight: 320 }} /><div className="skeleton" style={{ minHeight: 320 }} /></>
            )}
            {teams.length ? (
              <Race eyebrow="Ranking Elo" title="Los más fuertes hoy" color="var(--ink)" teams={byTeam} to="/equipos"
                    rows={teams.slice(0, 5).map((t) => ({ team: t.team, name: t.name, value: t.elo, label: num(t.elo, 0), width: (t.elo - eloMin) / (eloMax - eloMin || 1) }))}
                    foot="El Elo se ajusta a lo que el mercado esperaba de cada equipo" />
            ) : <div className="skeleton" style={{ minHeight: 320 }} />}
          </div>
        </Reveal>

        <SeasonData teams={byTeam} />

        <Reveal className="container sec home-section">
          <div className="section-title">
            <h2>De un resultado a cada marcador</h2>
            <Link className="btn" to="/metodologia">La metodología →</Link>
          </div>
          <p className="data-label home-sub">Cómo funciona</p>
          <div className="steps">
            {[
              { n: '01', t: 'Un Elo que aprende', d: 'Después de cada partido de primera y segunda división, el rating de cada equipo se acerca a lo que el mercado esperaba de él antes de jugarlo.' },
              { n: '02', t: 'Goles esperados', d: 'Dos regresiones de Poisson convierten la diferencia de Elo en los goles esperados del local y del visitante.' },
              { n: '03', t: 'Cada marcador', d: 'Con esos goles se calcula la probabilidad de cada resultado exacto; sumando celdas, la de victoria, empate o derrota.' },
            ].map((s) => (
              <div key={s.n} className="step">
                <span className="step-n num">{s.n}</span>
                <h3>{s.t}</h3>
                <p className="note">{s.d}</p>
              </div>
            ))}
            {tm && (
              <div className="band step-honest">
                <h3 className="honest-h"><span className="honest-big">Sin maquillaje</span> ¿Le gana al mercado? {gap > 0 ? 'No.' : 'Sí.'}</h3>
                <div className="honest-bars">
                  {[
                    { k: 'Este modelo', v: tm.model.log_loss },
                    { k: 'Bet365 (días antes)', v: tm.bet365_pre_closing.log_loss },
                  ].map((b) => (
                    <div key={b.k} className="honest-row">
                      <span>{b.k}</span>
                      <strong className="num">{num(b.v, 3)}</strong>
                    </div>
                  ))}
                  <div className="honest-gap">
                    <span>Diferencia</span>
                    <strong className="num">{gap > 0 ? '+' : ''}{num(gap, 3)}</strong>
                  </div>
                </div>
                <p className="note">
                  Log loss en test {tm.seasons} (menor es mejor). Las cuotas de cada partido saben de sus lesiones y alineaciones;
                  el modelo solo aprende de las cuotas de partidos anteriores.
                  Sus probabilidades, en cambio, están bien calibradas.
                </p>
              </div>
            )}
          </div>
        </Reveal>
      </div>
    </>
  )
}
