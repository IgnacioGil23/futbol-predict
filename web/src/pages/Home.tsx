import { Link } from 'react-router-dom'
import { HomeAdvantageChart } from '../components/HomeAdvantageChart'
import { OutcomeBar } from '../components/OutcomeBar'
import { ScoreHeatmap } from '../components/ScoreHeatmap'
import { formatDate, num, pct, useData } from '../lib/data'
import { forecast } from '../lib/model'
import type { FixturesFile, HomeAdvantageFile, MetaFile, ModelFile, StateFile } from '../lib/types'
import './home.css'

export function Home() {
  const meta = useData<MetaFile>('meta.json')
  const state = useData<StateFile>('state.json')
  const model = useData<ModelFile>('model.json')
  const fixtures = useData<FixturesFile>('fixtures.json')
  const ha = useData<HomeAdvantageFile>('home_advantage.json')

  const teams = [...(state.data?.teams ?? [])].sort((a, b) => b.elo - a.elo)
  const fixture = fixtures.data?.matches[0]
  // Partido destacado: el primer partido publicado o, si no hay, el cruce de los dos mejores por Elo.
  const featured = fixture
    ? { home: fixture.home_team, away: fixture.away_team, homeName: fixture.home_name, awayName: fixture.away_name,
        grid: fixture.score_grid, probs: fixture.probabilities, market: fixture.market, date: fixture.date, lam: fixture.expected_goals.home, mu: fixture.expected_goals.away }
    : teams.length >= 2 && model.data
      ? (() => {
          const f = forecast(model.data.params, teams[0].elo, teams[1].elo)
          return { home: teams[0].team, away: teams[1].team, homeName: teams[0].name, awayName: teams[1].name,
                   grid: f.grid, probs: f.probabilities, market: null, date: null, lam: f.lam, mu: f.mu }
        })()
      : null
  const tm = meta.data?.model.test_metrics

  return (
    <>
      <section className="hero">
        <div className="container hero-grid">
          <div className="hero-copy">
            <span className="eyebrow">Premier League · modelo de goles de Poisson</span>
            <h1>¿Cuántos goles? <br /><span className="hero-accent">Todas las respuestas,</span> con su probabilidad.</h1>
            <p className="lede">
              Un modelo de Machine Learning que estima los goles esperados de cada equipo a partir de su Elo y los
              convierte en la probabilidad de cada marcador exacto. Evaluado con honestidad contra el mercado de apuestas.
            </p>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 20 }}>
              <Link className="btn btn-primary" to="/previa">Armar una previa →</Link>
              <Link className="btn" to="/revision">¿Qué predijo en el pasado?</Link>
            </div>
            {tm && (
              <div className="hero-stats">
                <div><strong className="tabular">{num(meta.data!.model.trained_on.matches, 0)}</strong><span>partidos de entrenamiento</span></div>
                <div><strong className="tabular">{num(tm.model.log_loss, 3)}</strong><span>log loss en test (mercado: {num(tm.bet365_pre_closing.log_loss, 3)})</span></div>
                <div><strong className="tabular">{pct(tm.model.accuracy)}</strong><span>aciertos del resultado en test</span></div>
              </div>
            )}
          </div>
          <div className="card hero-card">
            {featured ? (
              <>
                <span className="eyebrow">{fixture ? `Próximo partido · ${formatDate(featured.date!)}` : 'Si se enfrentaran hoy'}</span>
                <h3 style={{ margin: '6px 0 4px', fontSize: '1.5rem' }}>{featured.homeName} vs {featured.awayName}</h3>
                <p className="card-sub">Goles esperados {num(featured.lam)} – {num(featured.mu)}</p>
                <ScoreHeatmap grid={featured.grid} homeName={featured.homeName} awayName={featured.awayName} size={5} />
                <div style={{ marginTop: 12 }}>
                  <OutcomeBar probs={featured.probs} homeName={featured.homeName} awayName={featured.awayName} market={featured.market} />
                </div>
                <Link className="btn" style={{ marginTop: 14 }}
                      to={`/previa?home=${encodeURIComponent(featured.home)}&away=${encodeURIComponent(featured.away)}`}>
                  Ver la previa completa →
                </Link>
              </>
            ) : <div className="skeleton" style={{ minHeight: 380 }} />}
          </div>
        </div>
      </section>

      <section className="container section">
        <div className="grid grid-2">
          <div className="card">
            <span className="eyebrow">Próximos partidos</span>
            <h3 style={{ margin: '6px 0 12px' }}>Esta semana en la Premier</h3>
            {fixtures.data && fixtures.data.matches.length === 0 && (
              <p className="small muted">
                Football-Data todavía no publicó los partidos de la próxima fecha (suele hacerlo pocos días antes).
                Mientras tanto, podés armar cualquier cruce en la <Link to="/previa">previa</Link>.
              </p>
            )}
            <ul className="fixture-list">
              {fixtures.data?.matches.map((m) => (
                <li key={`${m.home_team}-${m.away_team}`}>
                  <Link to={`/previa?home=${encodeURIComponent(m.home_team)}&away=${encodeURIComponent(m.away_team)}`}>
                    <span className="muted small tabular">{formatDate(m.date, { weekday: 'short', day: 'numeric', month: 'short' })}</span>
                    <span className="fx-teams">{m.home_name} <span className="muted">vs</span> {m.away_name}</span>
                    <span className="fx-probs tabular small">
                      <span style={{ color: 'var(--home)' }}>{pct(m.probabilities.home)}</span> ·{' '}
                      <span>{pct(m.probabilities.draw)}</span> ·{' '}
                      <span style={{ color: 'var(--away)' }}>{pct(m.probabilities.away)}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div className="card">
            <span className="eyebrow">Ranking Elo</span>
            <h3 style={{ margin: '6px 0 12px' }}>Los más fuertes hoy</h3>
            <table className="table">
              <thead><tr><th>#</th><th>Equipo</th><th className="num">Elo</th><th className="num">Pos. tabla</th></tr></thead>
              <tbody>
                {teams.slice(0, 8).map((t, i) => (
                  <tr key={t.team}>
                    <td className="muted">{i + 1}</td>
                    <td><Link to={`/equipos/${t.slug}`}>{t.name}</Link></td>
                    <td className="num"><strong>{num(t.elo, 0)}</strong></td>
                    <td className="num muted">{t.table?.played ? `${t.table.position}º` : '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="small muted" style={{ marginTop: 8 }}>
              El Elo mide la fuerza según todos los resultados; la tabla, solo los de esta temporada.
            </p>
          </div>
        </div>
      </section>

      <section className="container section">
        <div className="card">
          <span className="eyebrow">El hallazgo</span>
          <h2 style={{ margin: '6px 0 8px' }}>Sin público, la ventaja de local casi desapareció</h2>
          {ha.data && (
            <p className="lede" style={{ marginBottom: 16 }}>
              Antes de la pandemia el local sacaba {num(ha.data.eras[0].goal_diff)} goles de diferencia por partido. Con
              estadios vacíos, {num(ha.data.eras[1].goal_diff)}. Con el público de vuelta, la ventaja regresó… pero más chica:{' '}
              {num(ha.data.eras[2].goal_diff)}.
            </p>
          )}
          {ha.data ? <HomeAdvantageChart data={ha.data} compact /> : <div className="skeleton" />}
          <Link className="btn" style={{ marginTop: 14 }} to="/ventaja-local">Ver el análisis completo →</Link>
        </div>
      </section>
    </>
  )
}
