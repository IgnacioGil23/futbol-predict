import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { CountUp } from '../components/CountUp'
import { Icon } from '../components/Icon'
import { OutcomeBar } from '../components/OutcomeBar'
import { Pitch } from '../components/Pitch'
import { TeamBadge } from '../components/TeamBadge'
import { TeamName } from '../components/TeamName'
import { formatDate, num, pct, pct1, useData } from '../lib/data'
import { forecast, topScores } from '../lib/model'
import { useTeamIndex } from '../lib/teams'
import type {
  MetaFile, ModelFile, Probabilities, ReviewSeasonSummary, SeasonFile, StateFile, TeamIndexItem, UpcomingFile, UpcomingMatch,
} from '../lib/types'
import './home.css'

const delay = (d: number) => ({ '--d': d }) as CSSProperties

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

function MatchPoster({ f, teams }: { f: Featured; teams: Map<string, TeamIndexItem> }) {
  const side = (team: string, name: string, elo: number) => {
    const t = teams.get(team)
    return (
      <div className="poster-team">
        <div className="poster-badge">
          {t ? <TeamBadge badge={t.badge} short={t.short} name={name} size={84} eager decorative /> : null}
        </div>
        <strong>{name}</strong>
        <span className="small muted tabular">Elo {num(elo, 0)}</span>
      </div>
    )
  }
  return (
    <article className="poster reveal" style={delay(3)} aria-label={`${f.homeName} contra ${f.awayName}`}>
      <div className="poster-head">
        <span className="eyebrow">{f.label}</span>
        {f.date && <span className="small muted">{when(f.date, f.kickoff, true)}</span>}
      </div>
      <div className="poster-teams">
        {side(f.home, f.homeName, f.elo.home)}
        <div className="poster-mid">
          <span className="poster-vs">VS</span>
          <span className="poster-xg tabular">{num(f.lam)} <span className="muted">–</span> {num(f.mu)}</span>
          <span className="poster-xg-label">goles esperados</span>
        </div>
        {side(f.away, f.awayName, f.elo.away)}
      </div>
      <OutcomeBar probs={f.probs} homeName={f.homeName} awayName={f.awayName} size="lg" />
      <div className="poster-scores">
        <span className="poster-scores-label">Marcadores más probables</span>
        <div className="poster-score-list">
          {f.scores.map((s, i) => (
            <div key={`${s.home}-${s.away}`} className={`poster-score ${i === 0 ? 'top' : ''}`}>
              <span className="tabular">{s.home}–{s.away}</span>
              <small className="tabular">{pct1(s.p)}</small>
            </div>
          ))}
        </div>
      </div>
      {f.market && (
        <p className="small muted">
          Mercado: {pct(f.market.home)} · {pct(f.market.draw)} · {pct(f.market.away)} (Bet365, sin margen)
        </p>
      )}
      <Link className="btn btn-primary poster-cta" to={f.href}>
        Ver el análisis completo <span className="arrow"><Icon name="arrow" size={16} /></span>
      </Link>
    </article>
  )
}

function FixtureCard({ m, matchday, teams, i }: { m: UpcomingMatch; matchday: number; teams: Map<string, TeamIndexItem>; i: number }) {
  const p = m.probabilities
  const top = m.top_scores[0]
  const fav = p.home >= p.away ? 'home' : 'away'
  const row = (team: string, name: string, prob: number, color: string, isFav: boolean) => {
    const t = teams.get(team)
    return (
      <div className={`fx-row ${isFav ? 'fav' : ''}`}>
        {t && <TeamBadge badge={t.badge} short={t.short} name={name} size={30} decorative />}
        <span className="fx-name">{name}</span>
        <span className="fx-pct tabular" style={{ color: isFav ? color : undefined }}>{pct(prob)}</span>
      </div>
    )
  }
  return (
    <Link className="card card-link fixture reveal" style={delay(i)}
          to={`/proximos?jornada=${matchday}&partido=${encodeURIComponent(`${m.home_team}|${m.away_team}`)}`}>
      <div className="fx-when small muted">{when(m.date, m.kickoff_ar)}</div>
      {row(m.home_team, m.home_name, p.home, 'var(--home)', fav === 'home')}
      {row(m.away_team, m.away_name, p.away, 'var(--away)', fav === 'away')}
      <div className="fx-bar" style={{ gridTemplateColumns: `${p.home}fr ${p.draw}fr ${p.away}fr` }} aria-hidden="true">
        <span style={{ background: 'var(--home)' }} /><span style={{ background: 'var(--draw)' }} /><span style={{ background: 'var(--away)' }} />
      </div>
      <div className="fx-foot small">
        <span className="muted">Empate <strong className="tabular">{pct(p.draw)}</strong></span>
        <span className="muted">Más probable <strong className="tabular">{top.home_goals}-{top.away_goals}</strong></span>
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
      <span className="eyebrow">{eyebrow}</span>
      <h3>{title}</h3>
      <ol className="race-list">
        {rows.map((r, i) => (
          <li key={r.team}>
            <span className="race-rank tabular">{i + 1}</span>
            <TeamName team={teams.get(r.team)} name={r.name} size={24} className="race-team" />
            <span className="race-bar"><span style={{ width: `${Math.max(2, r.width * 100)}%`, background: color }} /></span>
            <span className="race-val tabular">{r.label}</span>
          </li>
        ))}
      </ol>
      <div className="race-foot">
        <span className="small muted">{foot}</span>
        <Link className="small race-link" to={to}>Ver todo <Icon name="arrow" size={14} /></Link>
      </div>
    </div>
  )
}

export function Home() {
  const meta = useData<MetaFile>('meta.json')
  const state = useData<StateFile>('state.json')
  const model = useData<ModelFile>('model.json')
  const upcoming = useData<UpcomingFile>('upcoming.json')
  const season = useData<SeasonFile>('season.json')
  const review = useData<ReviewSeasonSummary[]>('review/index.json')
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
      href: `/proximos?jornada=${nextMd.matchday}&partido=${encodeURIComponent(`${fixture.home_team}|${fixture.away_team}`)}`,
    }
  } else if (teams.length >= 2 && model.data) {
    const f = forecast(model.data.params, teams[0].elo, teams[1].elo)
    featured = {
      home: teams[0].team, away: teams[1].team, homeName: teams[0].name, awayName: teams[1].name,
      probs: f.probabilities, market: null, lam: f.lam, mu: f.mu, elo: { home: teams[0].elo, away: teams[1].elo },
      scores: topScores(f.grid, 3), label: 'Si se enfrentaran hoy', date: null, kickoff: null,
      href: `/previa?home=${encodeURIComponent(teams[0].team)}&away=${encodeURIComponent(teams[1].team)}`,
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
      <section className="hero">
        <div className="hero-pitch" aria-hidden="true"><Pitch /></div>
        <div className="container hero-grid">
          <div className="hero-copy">
            <span className="pill pill-accent reveal"><span className="live-dot" />
              {state.data ? `Temporada ${state.data.season} · datos al ${formatDate(meta.data?.last_match_in_data ?? state.data.as_of)}` : 'Premier League'}
            </span>
            <h1 className="reveal" style={delay(1)}>Cada marcador,<br /><span className="grad-text">con su probabilidad.</span></h1>
            <p className="lede reveal" style={delay(2)}>
              Un modelo de Machine Learning estima los goles esperados de cada equipo a partir de su Elo y los convierte
              en la probabilidad de cada resultado exacto de la Premier League. Evaluado con honestidad contra el
              mercado de apuestas.
            </p>
            <div className="hero-ctas reveal" style={delay(3)}>
              <Link className="btn btn-primary" to="/proximos">Ver la próxima jornada <span className="arrow"><Icon name="arrow" size={16} /></span></Link>
              <Link className="btn" to="/previa">Armar una previa</Link>
            </div>
            {tm && meta.data && (
              <dl className="hero-stats reveal" style={delay(4)}>
                <div>
                  <dt>Partidos de entrenamiento</dt>
                  <dd><CountUp value={meta.data.model.trained_on.matches} format={(x) => num(x, 0)} /></dd>
                </div>
                {reviewed ? (
                  <div>
                    <dt>Predicciones fuera de muestra</dt>
                    <dd><CountUp value={reviewed} format={(x) => num(x, 0)} /></dd>
                  </div>
                ) : null}
                <div>
                  <dt>Resultado acertado (test)</dt>
                  <dd><CountUp value={tm.model.accuracy} format={pct} /></dd>
                </div>
              </dl>
            )}
          </div>
          {featured ? <MatchPoster f={featured} teams={byTeam} /> : <div className="skeleton" style={{ minHeight: 520 }} />}
        </div>
      </section>

      {nextMd && (
        <section className="container home-section">
          <div className="section-title">
            <div>
              <span className="eyebrow">Próximos partidos</span>
              <h2>Jornada {nextMd.matchday}</h2>
              <p className="small muted" style={{ marginTop: 6 }}>
                {formatDate(nextMd.from, { weekday: 'long', day: 'numeric', month: 'long' })} al{' '}
                {formatDate(nextMd.to, { weekday: 'long', day: 'numeric', month: 'long' })} · horarios de Argentina
              </p>
            </div>
            <Link className="btn" to="/proximos">La jornada completa <span className="arrow"><Icon name="arrow" size={16} /></span></Link>
          </div>
          <div className="fixture-grid">
            {nextMd.matches.map((m, i) => <FixtureCard key={`${m.home_team}-${m.away_team}`} m={m} matchday={nextMd.matchday} teams={byTeam} i={i} />)}
          </div>
        </section>
      )}
      {upcoming.data && !nextMd && (
        <section className="container home-section">
          <p className="callout">
            No hay partidos pendientes publicados en el calendario. Mientras tanto, podés armar cualquier cruce en la{' '}
            <Link to="/previa">previa</Link>.
          </p>
        </section>
      )}

      <section className="container home-section">
        <div className="section-title">
          <div>
            <span className="eyebrow">{sim ? `${num(sim.n_sims, 0)} simulaciones de la temporada` : 'La temporada'}</span>
            <h2>Cómo viene la Premier</h2>
          </div>
          <Link className="btn" to="/temporada">Todas las posiciones <span className="arrow"><Icon name="arrow" size={16} /></span></Link>
        </div>
        <div className="grid grid-3">
          {sim ? (
            <>
              <Race eyebrow="Campeón" title="La carrera por el título" color="var(--grad-accent)" teams={byTeam} to="/temporada"
                    rows={champ.map((t) => ({ team: t.team, name: t.name, value: t.p_champion, label: probLabel(t.p_champion), width: t.p_champion / champ[0].p_champion }))}
                    foot="Probabilidad de terminar primero" />
              <Race eyebrow="Descenso" title="Pelea por no descender" color="var(--away)" teams={byTeam} to="/temporada"
                    rows={releg.map((t) => ({ team: t.team, name: t.name, value: t.p_relegation, label: probLabel(t.p_relegation), width: t.p_relegation / releg[0].p_relegation }))}
                    foot="Probabilidad de terminar 18º a 20º" />
            </>
          ) : (
            <><div className="skeleton" style={{ minHeight: 320 }} /><div className="skeleton" style={{ minHeight: 320 }} /></>
          )}
          {teams.length ? (
            <Race eyebrow="Ranking Elo" title="Los más fuertes hoy" color="var(--home)" teams={byTeam} to="/equipos"
                  rows={teams.slice(0, 5).map((t) => ({ team: t.team, name: t.name, value: t.elo, label: num(t.elo, 0), width: (t.elo - eloMin) / (eloMax - eloMin || 1) }))}
                  foot="El Elo mide la fuerza según todos los resultados" />
          ) : <div className="skeleton" style={{ minHeight: 320 }} />}
        </div>
      </section>

      <section className="container home-section">
        <div className="section-title">
          <div>
            <span className="eyebrow">Cómo funciona</span>
            <h2>De un resultado a cada marcador</h2>
          </div>
          <Link className="btn" to="/metodologia">La metodología <span className="arrow"><Icon name="arrow" size={16} /></span></Link>
        </div>
        <div className="steps">
          {[
            { n: '01', t: 'Elo desde cero', d: 'Cada partido de Premier y Championship desde 2000-01 mueve la fuerza de los dos equipos: más cuanto más amplia la victoria.' },
            { n: '02', t: 'Goles esperados', d: 'Dos regresiones de Poisson convierten la diferencia de Elo en los goles esperados del local y del visitante.' },
            { n: '03', t: 'Cada marcador', d: 'Con esos goles se calcula la probabilidad de cada resultado exacto; sumando celdas, la de victoria, empate o derrota.' },
          ].map((s) => (
            <div key={s.n} className="card step">
              <span className="step-n">{s.n}</span>
              <h3>{s.t}</h3>
              <p className="small" style={{ color: 'var(--ink-2)' }}>{s.d}</p>
            </div>
          ))}
          {tm && (
            <div className="card step step-honest">
              <span className="eyebrow">Sin maquillaje</span>
              <h3>¿Le gana al mercado? {gap > 0 ? 'No.' : 'Sí.'}</h3>
              <div className="honest-bars">
                {[
                  { k: 'Este modelo', v: tm.model.log_loss },
                  { k: 'Bet365 (días antes)', v: tm.bet365_pre_closing.log_loss },
                ].map((b) => (
                  <div key={b.k} className="honest-row">
                    <span className="small">{b.k}</span>
                    <strong className="tabular">{num(b.v, 3)}</strong>
                  </div>
                ))}
                <div className="honest-gap small">
                  <span>Diferencia</span>
                  <strong className="tabular" style={gap > 0 ? undefined : { color: 'var(--good)' }}>{gap > 0 ? '+' : ''}{num(gap, 3)}</strong>
                </div>
              </div>
              <p className="small muted">
                Log loss en test {tm.seasons} (menor es mejor). Las cuotas saben de lesiones y alineaciones; el modelo no.
                Sus probabilidades, en cambio, están bien calibradas.
              </p>
            </div>
          )}
        </div>
      </section>
    </>
  )
}
