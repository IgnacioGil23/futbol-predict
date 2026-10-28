import { useState, type ReactNode } from 'react'
import { SortableTable, type Column } from '../components/SortableTable'
import { TeamName } from '../components/TeamName'
import { LeagueSwitcher } from '../components/LeagueSwitcher'
import { num, pct } from '../lib/data'
import { useLeague, useLeagueData } from '../lib/league'
import { useTeamIndex } from '../lib/teams'
import type { LeagueSummary, RefereeStats, StatsFile, StatsIndex, TeamIndexItem, TeamStats } from '../lib/types'
import './estadisticas.css'

const MIN_PLAYED = 10

const SECTIONS = [
  { id: 'liga', label: 'La liga' },
  { id: 'local', label: 'Local y visitante' },
  { id: 'tiempos', label: 'Por tiempos' },
  { id: 'remontadas', label: 'Remontadas' },
  { id: 'ataque', label: 'Ataque y defensa' },
  { id: 'suerte', label: 'Suerte o rendimiento' },
  { id: 'disciplina', label: 'Disciplina' },
  { id: 'calendario', label: 'Lo que viene' },
]

const f2 = (v: number) => num(v, 2)
const f1 = (v: number) => num(v, 1)
const f0 = (v: number) => num(v, 0)
const signed = (v: number) => `${v > 0 ? '+' : ''}${num(v, 1)}`

type Col = Column<TeamStats>
const col = (key: string, label: string, value: (t: TeamStats) => number | null, format: (v: number) => string,
             better: 'high' | 'low' = 'high', title?: string): Col => ({ key, label, value, format, better, title })

function Section({ id, title, intro, children }: { id: string; title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="stats-section">
      <h2>{title}</h2>
      {intro ? <p className="card-sub stats-intro">{intro}</p> : null}
      {children}
    </section>
  )
}

function LeagueCard({ label, value, reference, format = pct }: {
  label: string; value: number | null; reference: number | null; format?: (v: number) => string
}) {
  return (
    <div className="card stat-card">
      <span className="stat-label">{label}</span>
      <span className="big-num tabular">{value === null ? '—' : format(value)}</span>
      <span className="small muted">Promedio histórico: {reference === null ? '—' : format(reference)}</span>
    </div>
  )
}

function LeagueNumbers({ l, r, seasons }: { l: LeagueSummary; r: LeagueSummary; seasons: string }) {
  return (
    <Section id="liga" title="La liga en números"
             intro={<>Sobre {l.matches} partidos jugados. El promedio histórico es el de las temporadas {seasons}, contando todos sus partidos juntos.</>}>
      <div className="stat-grid">
        <LeagueCard label="Gana el local" value={l.home_win_pct} reference={r.home_win_pct} />
        <LeagueCard label="Empate" value={l.draw_pct} reference={r.draw_pct} />
        <LeagueCard label="Gana el visitante" value={l.away_win_pct} reference={r.away_win_pct} />
        <LeagueCard label="Goles por partido" value={l.goals_per_match} reference={r.goals_per_match} format={f2} />
        <LeagueCard label="Goles en el primer tiempo" value={l.first_half_goals_share} reference={r.first_half_goals_share} />
        <LeagueCard label="Marcan los dos" value={l.btts_pct} reference={r.btts_pct} />
        <LeagueCard label="Más de 2,5 goles" value={l.over25_pct} reference={r.over25_pct} />
        <LeagueCard label="El que gana al entretiempo, gana" value={l.ht_leader_win_pct} reference={r.ht_leader_win_pct} />
        <LeagueCard label="El que pierde al entretiempo, lo da vuelta" value={l.ht_trailer_comeback_pct} reference={r.ht_trailer_comeback_pct} />
      </div>
    </Section>
  )
}

/** La temporada elegida es del estado de la liga: se reinicia al cambiar de liga. */
export function Estadisticas() {
  const { league } = useLeague()
  return <EstadisticasLiga key={league.slug} />
}

function EstadisticasLiga() {
  const { league } = useLeague()
  const index = useLeagueData<StatsIndex>('stats/index.json')
  const [chosen, setChosen] = useState<string | null>(null)
  const season = chosen ?? index.data?.find((s) => s.current)?.season ?? index.data?.[0]?.season ?? null
  const { data: s, error, loading } = useLeagueData<StatsFile>(season ? `stats/${season}.json` : null)
  const { byTeam } = useTeamIndex()

  if (index.error) return <div className="container section"><p className="callout">Todavía no hay estadísticas publicadas.</p></div>

  const teamCell = (t: { team: string }) => {
    const info: TeamIndexItem | undefined = byTeam.get(t.team)
    return <TeamName team={info} name={info?.name ?? t.team} size={20} />
  }
  const teamLabel = { title: 'Equipo', render: teamCell }
  const avgPlayed = s && s.teams.length ? s.teams.reduce((a, t) => a + t.played, 0) / s.teams.length : 0

  return (
    <div className="container section">
      <div className="section-head">
        <span className="eyebrow">{league.competition}{s ? ` · temporada ${s.season}` : ''}</span>
        <h1>Estadísticas</h1>
        <p className="lede">
          Los números que se miran antes de un partido: cómo rinde cada equipo de local y de visitante, en cada tiempo,
          cuando va ganando o perdiendo, y señales de si su campaña se sostiene con su juego o con una racha. Tocá el
          encabezado de una columna para ordenar.
        </p>
        <LeagueSwitcher />
      </div>

      <div className="stats-toolbar">
        {index.data && index.data.length > 1 ? (
          <div className="seg" role="group" aria-label="Temporada">
            {index.data.map((i) => (
              <button key={i.season} type="button" aria-pressed={i.season === season} onClick={() => setChosen(i.season)}>
                {i.season}{i.current ? ' (en curso)' : ''}
              </button>
            ))}
          </div>
        ) : null}
        <nav className="stats-jump" aria-label="Secciones">
          {SECTIONS.filter((x) => x.id !== 'calendario' || s?.difficulty).map((x) => (
            <button key={x.id} type="button" onClick={() => document.getElementById(x.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
              {x.label}
            </button>
          ))}
        </nav>
      </div>

      {loading || index.loading ? <div className="skeleton" style={{ minHeight: 400 }} /> : null}
      {error ? <p className="callout">No se pudieron cargar las estadísticas de {season}.</p> : null}

      {s ? (
        <>
          {avgPlayed < MIN_PLAYED ? (
            <p className="callout">
              Pocos partidos: cada equipo jugó {num(avgPlayed, 0)} en promedio. Estos números todavía se mueven mucho de
              una fecha a otra.
            </p>
          ) : null}

          <LeagueNumbers l={s.league} r={s.league_reference} seasons={s.reference_seasons} />

          <Section id="local" title="Local y visitante" intro="Puntos por partido en cada condición. La diferencia muestra cuánto depende cada equipo de jugar en casa.">
            <div className="card">
              <SortableTable rows={s.teams} rowKey={(t) => t.team} label={teamLabel} initialSort="home_ppg" caption="Local y visitante"
                columns={[
                  col('home_played', 'PJ local', (t) => t.home.played, f0),
                  col('home_ppg', 'Pts/PJ local', (t) => t.home.points_per_game, f2),
                  col('home_gd', 'Dif. gol local', (t) => t.home.gf - t.home.ga, (v) => `${v > 0 ? '+' : ''}${v}`),
                  col('away_played', 'PJ visit.', (t) => t.away.played, f0),
                  col('away_ppg', 'Pts/PJ visit.', (t) => t.away.points_per_game, f2),
                  col('away_gd', 'Dif. gol visit.', (t) => t.away.gf - t.away.ga, (v) => `${v > 0 ? '+' : ''}${v}`),
                  col('gap', 'Local − visit.', (t) => (t.home.points_per_game === null || t.away.points_per_game === null
                    ? null : t.home.points_per_game - t.away.points_per_game), (v) => `${v > 0 ? '+' : ''}${num(v, 2)}`, 'high',
                    'Puntos por partido de local menos los de visitante'),
                ]} />
            </div>
          </Section>

          <Section id="tiempos" title="Primer y segundo tiempo"
                   intro="Goles de cada tiempo y dos tablas: cómo estaría el campeonato si los partidos terminaran en el entretiempo, y si solo contaran los segundos tiempos.">
            <div className="card">
              <SortableTable rows={s.teams} rowKey={(t) => t.team} label={teamLabel} initialSort="pts_1h" caption="Por tiempos"
                columns={[
                  col('gf_1h', 'GF 1T', (t) => t.halves.gf_1h, f0),
                  col('ga_1h', 'GC 1T', (t) => t.halves.ga_1h, f0, 'low'),
                  col('gf_2h', 'GF 2T', (t) => t.halves.gf_2h, f0),
                  col('ga_2h', 'GC 2T', (t) => t.halves.ga_2h, f0, 'low'),
                  col('pts_1h', 'Pts 1T', (t) => t.halves.points_1h, f0, 'high', 'Puntos si cada partido terminaba en el entretiempo'),
                  col('pts_2h', 'Pts 2T', (t) => t.halves.points_2h, f0, 'high', 'Puntos contando solo los goles del segundo tiempo'),
                ]} />
            </div>
          </Section>

          <Section id="remontadas" title="Remontadas y cierres"
                   intro="Según el marcador al entretiempo: los datos no tienen el minuto de cada gol, así que no se puede saber quién empezó ganando.">
            <div className="grid grid-2">
              <div className="card">
                <h3>Cuando ganaba al entretiempo</h3>
                <SortableTable rows={s.teams} rowKey={(t) => t.team} label={teamLabel} initialSort="dropped" caption="Ganando al entretiempo"
                  columns={[
                    col('lead_n', 'PJ', (t) => t.ht.leading.n, f0),
                    col('lead_w', 'Ganó', (t) => t.ht.leading.won, f0),
                    col('lead_d', 'Empató', (t) => t.ht.leading.drawn, f0, 'low'),
                    col('lead_l', 'Perdió', (t) => t.ht.leading.lost, f0, 'low'),
                    col('dropped', 'Pts perdidos', (t) => t.ht.points_dropped_leading, f0, 'high', 'Puntos que dejó escapar estando arriba'),
                  ]} />
              </div>
              <div className="card">
                <h3>Cuando perdía al entretiempo</h3>
                <SortableTable rows={s.teams} rowKey={(t) => t.team} label={teamLabel} initialSort="rescued" caption="Perdiendo al entretiempo"
                  columns={[
                    col('trail_n', 'PJ', (t) => t.ht.trailing.n, f0, 'low'),
                    col('trail_w', 'Lo dio vuelta', (t) => t.ht.trailing.won, f0),
                    col('trail_d', 'Empató', (t) => t.ht.trailing.drawn, f0),
                    col('trail_l', 'Perdió', (t) => t.ht.trailing.lost, f0, 'low'),
                    col('rescued', 'Pts rescatados', (t) => t.ht.points_won_trailing, f0, 'high', 'Puntos que sumó yendo abajo'),
                  ]} />
              </div>
            </div>
          </Section>

          <Section id="ataque" title="Ataque y defensa">
            <div className="grid">
              <div className="card">
                <h3>Goles</h3>
                <SortableTable rows={s.teams} rowKey={(t) => t.team} label={teamLabel} initialSort="gf" caption="Goles"
                  columns={[
                    col('gf', 'GF/PJ', (t) => t.goals.gf_per_game, f2),
                    col('ga', 'GC/PJ', (t) => t.goals.ga_per_game, f2, 'low'),
                    col('cs', 'Valla invicta', (t) => t.goals.clean_sheet_pct, pct),
                    col('fts', 'Sin convertir', (t) => t.goals.failed_to_score_pct, pct, 'low'),
                    col('btts', 'Marcan los dos', (t) => t.goals.btts_pct, pct),
                    col('o25', '+2,5 goles', (t) => t.goals.over25_pct, pct),
                  ]} />
              </div>
              <div className="card">
                <h3>Tiros</h3>
                <p className="card-sub">
                  "% de los tiros" es la parte de los tiros del partido que hace el equipo: arriba de 50% domina las
                  situaciones de gol, más allá del resultado.
                </p>
                <SortableTable rows={s.teams} rowKey={(t) => t.team} label={teamLabel} initialSort="sot_share" caption="Tiros"
                  columns={[
                    col('shots', 'Tiros/PJ', (t) => t.shots.shots_per_game, f1),
                    col('shots_a', 'Recibidos/PJ', (t) => t.shots.shots_against_per_game, f1, 'low'),
                    col('sot', 'Al arco/PJ', (t) => t.shots.sot_per_game, f1),
                    col('sot_a', 'Al arco recib./PJ', (t) => t.shots.sot_against_per_game, f1, 'low'),
                    col('acc', '% al arco', (t) => t.shots.accuracy, pct, 'high', 'Tiros al arco sobre tiros totales'),
                    col('shot_share', '% de los tiros', (t) => t.shots.shot_share, pct),
                    col('sot_share', '% de los tiros al arco', (t) => t.shots.sot_share, pct),
                  ]} />
              </div>
            </div>
          </Section>

          <Section id="suerte" title="Suerte o rendimiento"
                   intro={<>Puntos esperados: los que le daba el mercado de apuestas antes de cada partido (3 × probabilidad de ganar + probabilidad de empatar). PDO = % de tiros al arco convertidos + % de tiros al arco atajados, × 1000. Muy por encima de 1000 suele indicar una buena racha que tiende a normalizarse; muy por debajo, lo contrario.</>}>
            <div className="card">
              <SortableTable rows={s.teams} rowKey={(t) => t.team} label={teamLabel} initialSort="diff" caption="Suerte o rendimiento"
                columns={[
                  col('pts', 'Pts', (t) => t.market.points, f0),
                  col('xpts', 'Pts esperados', (t) => t.market.expected_points, f1),
                  col('diff', 'Diferencia', (t) => t.market.difference, signed, 'high', 'Puntos reales menos los esperados por el mercado'),
                  col('conv', 'Conversión', (t) => t.shots.conversion, pct, 'high', 'Goles sobre tiros al arco'),
                  col('save', '% atajadas', (t) => t.shots.save_pct, pct, 'high', 'Tiros al arco recibidos que no fueron gol'),
                  col('pdo', 'PDO', (t) => t.shots.pdo, f0),
                ]} />
              <p className="small muted" style={{ marginTop: 8 }}>
                Los goles incluyen penales y goles en contra. Partidos sin cuotas publicadas quedan fuera de los puntos esperados.
              </p>
            </div>
          </Section>

          <Section id="disciplina" title="Disciplina y árbitros">
            <div className="grid grid-2">
              <div className="card">
                <h3>Equipos</h3>
                <SortableTable rows={s.teams} rowKey={(t) => t.team} label={teamLabel} initialSort="yellow" caption="Tarjetas por equipo"
                  columns={[
                    col('yellow', 'Amarillas/PJ', (t) => t.discipline.yellow_per_game, f2),
                    col('red', 'Rojas', (t) => t.discipline.red_total, f0),
                  ]} />
              </div>
              <div className="card">
                <h3>Árbitros</h3>
                <p className="card-sub">Tarjetas de los dos equipos por partido. Solo árbitros con 3 partidos o más.</p>
                {s.referees.length ? (
                  <SortableTable<RefereeStats> rows={s.referees} rowKey={(r) => r.referee} initialSort="yellow" caption="Árbitros"
                    label={{ title: 'Árbitro', render: (r) => r.referee }}
                    columns={[
                      { key: 'matches', label: 'PJ', value: (r) => r.matches, format: f0, better: 'high' },
                      { key: 'yellow', label: 'Amarillas/PJ', value: (r) => r.yellow_per_game, format: f2, better: 'high' },
                      { key: 'red', label: 'Rojas', value: (r) => r.red_total, format: f0, better: 'high' },
                    ]} />
                ) : <p className="small muted">Todavía ningún árbitro dirigió 3 partidos.</p>}
                {s.referees_next ? (
                  <>
                    <h3 style={{ marginTop: 20 }}>Árbitros designados para los próximos partidos</h3>
                    <ul className="ref-next">
                      {Object.entries(s.referees_next).map(([pair, ref]) => {
                        const [h, a] = pair.split('|')
                        return <li key={pair}><span>{byTeam.get(h)?.name ?? h} – {byTeam.get(a)?.name ?? a}</span><strong>{ref}</strong></li>
                      })}
                    </ul>
                  </>
                ) : null}
              </div>
            </div>
          </Section>

          {s.difficulty ? (
            <Section id="calendario" title="Lo que viene"
                     intro="Dificultad del calendario que le queda a cada equipo: el Elo medio de los rivales que todavía tiene que enfrentar (el mismo Elo que usa el modelo). Puesto 1 = el calendario más difícil.">
              <div className="card">
                <SortableTable rows={Object.keys(s.difficulty).map((team) => ({ team }))} rowKey={(t) => t.team} label={teamLabel}
                  initialSort="rank" caption="Dificultad del calendario"
                  columns={[
                    { key: 'rank', label: 'Puesto', value: (t) => s.difficulty?.[t.team]?.rank ?? null, format: f0, better: 'low' },
                    { key: 'rating', label: 'Elo medio de los rivales', value: (t) => s.difficulty?.[t.team]?.avg_opponent_rating ?? null, format: f0, better: 'high' },
                    { key: 'remaining', label: 'Partidos que faltan', value: (t) => s.difficulty?.[t.team]?.remaining ?? null, format: f0, better: 'high' },
                  ]} />
              </div>
            </Section>
          ) : null}

          <p className="small muted" style={{ marginTop: 24 }}>
            Fuente: Football-Data.co.uk (resultados, entretiempo, tiros, tarjetas, árbitros y cuotas de Bet365).
          </p>
        </>
      ) : null}
    </div>
  )
}
