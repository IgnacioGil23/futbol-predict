import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { useLeagueData } from '../lib/league'
import { num, pct, pct1 } from '../lib/data'
import { kitOf, onColor, sideColors } from '../lib/kits'
import { topScores } from '../lib/model'
import { useTeamIndex } from '../lib/teams'
import type { EloPoint, FormMatch, H2H, MetaFile, Probabilities, Rest } from '../lib/types'
import { EloChart } from './EloChart'
import { FormStrip, H2HBlock, RestBlock } from './MatchContext'
import { Odo, Reveal, SplitBar } from './Motion'
import { ScoreHeatmap } from './ScoreHeatmap'
import { TeamBadge } from './TeamBadge'
import './match.css'

/** Todo lo que se muestra de un partido (Previa y Próximos partidos usan el mismo formato). */
export interface MatchView {
  elo: { home: number; away: number }
  lam: number
  mu: number
  probabilities: Probabilities
  grid: number[][]
  market: Probabilities | null
  form: { home: FormMatch[]; away: FormMatch[] }
  rest: { home: Rest; away: Rest }
  h2h: H2H
  eloHistory: { home: EloPoint[]; away: EloPoint[] } | null   // null = todavía cargando
}

interface Props {
  view: MatchView
  home: string
  away: string
  homeName: string
  awayName: string
  homeSlug?: string
  awaySlug?: string
}

export function MatchAnalysis({ view, home, away, homeName, awayName, homeSlug, awaySlug }: Props) {
  const top = topScores(view.grid, 3)
  const review = useLeagueData<MetaFile>('meta.json').data?.review
  const diff = view.elo.home - view.elo.away
  const { byTeam } = useTeamIndex()
  const ht = byTeam.get(home)
  const at = byTeam.get(away)
  const { hc, ac } = sideColors(kitOf(homeName, ht?.colors), kitOf(awayName, at?.colors, '#777777'))
  // Dentro del análisis, "local" y "visitante" son los colores de cada club (grilla, cara a cara, Elo).
  // Las líneas se mezclan un poco con la tinta del tema para que camisetas muy claras u oscuras se lean sobre el fondo.
  const scope = {
    '--home': hc, '--away': ac,
    '--home-line': `color-mix(in srgb, ${hc} 72%, var(--ink))`, '--away-line': `color-mix(in srgb, ${ac} 72%, var(--ink))`,
  } as CSSProperties
  const p = view.probabilities
  const outcomes = [
    { key: 'home' as const, label: `Gana ${homeName}` },
    { key: 'draw' as const, label: 'Empate' },
    { key: 'away' as const, label: `Gana ${awayName}` },
  ]
  const stadium = ht?.stadium

  const side = (team: typeof ht, name: string, elo: number, xg: number, color: string, cls: string) => (
    <div className={`ma-side ${cls}`} style={{ background: color, color: onColor(color) }}>
      {team && <TeamBadge badge={team.badge} short={team.short} name={name} size={56} colors={team.colors ?? null} decorative />}
      <p className="ma-name">{name}</p>
      <dl className="ma-facts">
        <div><dt>Elo</dt><dd className="num"><Odo value={num(elo, 0)} /></dd></div>
        <div><dt>Goles esperados</dt><dd className="num"><Odo value={num(xg)} /></dd></div>
      </dl>
    </div>
  )

  return (
    <div className="ma" style={scope}>
      <div className="ma-head">
        {side(ht, homeName, view.elo.home, view.lam, hc, 'ma-home')}
        <div className="ma-diff">
          <span className="data-label">Diferencia de Elo</span>
          <span className="num ma-diff-v">{diff > 0 ? '+' : ''}{num(diff, 0)}</span>
        </div>
        {side(at, awayName, view.elo.away, view.mu, ac, 'ma-away')}
      </div>

      <Reveal className="ma-sec ma-result" aria-label="Resultado">
        <h3>Resultado</h3>
        <SplitBar probs={[p.home, p.draw, p.away]} colors={[hc, ac]} height={44} font={16}
                  label={`Gana ${homeName} ${pct(p.home)}, empate ${pct(p.draw)}, gana ${awayName} ${pct(p.away)}`} />
        <div className="bar-legend"><span>Gana {homeName}</span><span>Empate</span><span>Gana {awayName}</span></div>
        <div className="ma-market">
          <h3>Modelo vs mercado</h3>
          {!view.market && <p className="note">Las cuotas de este partido todavía no se publicaron: el mercado aparece pocos días antes de cada fecha.</p>}
          <div className="mvm" role="list">
            {outcomes.map((o) => (
              <div key={o.key} className="mvm-row" role="listitem">
                <span className="mvm-label">{o.label}</span>
                <span className="mvm-track">
                  <span className="mvm-model grow-x" style={{ width: `${p[o.key] * 100}%` }} />
                  {view.market && <span className="mvm-dot" style={{ left: `${view.market[o.key] * 100}%` }} title="Mercado" />}
                </span>
                <span className="num mvm-v">{pct(p[o.key])} <span className="muted">modelo</span></span>
                <span className="num mvm-m">{view.market ? <>mercado {pct(view.market[o.key])}</> : 'mercado: sin cuotas'}</span>
              </div>
            ))}
          </div>
          {view.market && <p className="note">Mercado (Bet365, sin margen): probabilidades implícitas con el margen quitado (método de Shin).</p>}
        </div>
      </Reveal>

      <Reveal className="ma-sec ma-grid">
        <div className="ma-heat">
          <h3>Probabilidad de cada marcador</h3>
          <p className="note">Goles esperados: {homeName} {num(view.lam)} · {awayName} {num(view.mu)}</p>
          <ScoreHeatmap grid={view.grid} homeName={homeName} awayName={awayName} />
        </div>
        <div className="ma-side-col">
          <div>
            <h3>Marcadores más probables</h3>
            <ol className="ma-top">
              {top.map((s) => (
                <li key={`${s.home}-${s.away}`}><b className="num">{s.home}-{s.away}</b> <span className="num muted">{num(s.p * 100, 1)}%</span></li>
              ))}
            </ol>
            {review && (
              <p className="note" style={{ marginTop: 8 }}>
                En las {num(review.matches, 0)} predicciones fuera de muestra del modelo ({review.first_season} a{' '}
                {review.last_season}), el marcador más probable nunca pasó del {pct1(review.max_top_score)}: en fútbol hay
                demasiados resultados posibles como para "acertar el resultado exacto".
              </p>
            )}
          </div>
          <div className="ma-unknown">
            <h3>Lo que el modelo no sabe</h3>
            <ul className="list">
              <li>Lesiones, suspensiones y alineaciones confirmadas.</li>
              <li>Rotaciones por copas o competiciones europeas.</li>
              <li>Lo que pasó en la semana del partido (las cuotas del propio partido nunca se usan).</li>
              <li>Noticias de la semana: el mercado de apuestas sí las incorpora, y por eso predice mejor.</li>
            </ul>
            <p style={{ marginTop: 12 }}><Link className="btn" to="/metodologia">¿Qué tan bien predice? →</Link></p>
          </div>
          {stadium && (
            <figure className="ma-stadium">
              <img src={stadium.image} alt={`${stadium.name}, estadio de ${homeName}`} loading="lazy" decoding="async" />
              <figcaption className="data-label">
                {stadium.name}. Foto: {stadium.credit.author} · <a href={stadium.credit.license_url} target="_blank" rel="noreferrer">{stadium.credit.license}</a>, vía <a href={stadium.credit.source} target="_blank" rel="noreferrer">Wikimedia Commons</a>.
              </figcaption>
            </figure>
          )}
        </div>
      </Reveal>

      <Reveal className="ma-sec ma-context">
        <div className="ma-form" style={{ '--chip-g': hc, '--chip-g-ink': onColor(hc) } as CSSProperties}>
          <h3>Forma · {homeName}</h3><FormStrip form={view.form.home} name={homeName} />
        </div>
        <div className="ma-form" style={{ '--chip-g': ac, '--chip-g-ink': onColor(ac) } as CSSProperties}>
          <h3>Forma · {awayName}</h3><FormStrip form={view.form.away} name={awayName} />
        </div>
        <div>
          <h3>Cara a cara</h3>
          <H2HBlock h2h={view.h2h} homeTeam={home} homeName={homeName} awayName={awayName} />
        </div>
      </Reveal>

      <Reveal className="ma-sec ma-rest">
        <h3>Descanso y congestión</h3>
        <div className="grid grid-2">
          <RestBlock rest={view.rest.home} name={homeName} />
          <RestBlock rest={view.rest.away} name={awayName} />
        </div>
        <p className="note" style={{ marginTop: 12 }}>
          Solo cuenta partidos de liga: los datos no incluyen copas ni competiciones europeas, así que un equipo que
          jugó Champions a mitad de semana aparece "descansado". Por eso (y porque no mejoró la validación) el
          modelo no usa este dato.
        </p>
      </Reveal>

      <Reveal className="ma-sec ma-elo">
        <h3>Evolución del Elo (dos temporadas)</h3>
        <p className="note">El rating de cada equipo: después de cada partido se acerca a lo que el mercado esperaba de él antes de jugarlo.</p>
        {view.eloHistory ? (
          <EloChart series={[
            { name: homeName, color: 'var(--home-line)', points: view.eloHistory.home },
            { name: awayName, color: 'var(--away-line)', points: view.eloHistory.away },
          ]} />
        ) : <div className="skeleton" style={{ minHeight: 260 }} />}
        <div className="ma-links">
          {homeSlug && <Link className="btn" to={`/equipos/${homeSlug}`}>Ficha de {homeName} →</Link>}
          {awaySlug && <Link className="btn" to={`/equipos/${awaySlug}`}>Ficha de {awayName} →</Link>}
        </div>
      </Reveal>
    </div>
  )
}
