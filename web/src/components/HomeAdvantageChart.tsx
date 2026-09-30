import { scaleBand, scaleLinear } from 'd3-scale'
import { area, line } from 'd3-shape'
import { useState } from 'react'
import { num, pct } from '../lib/data'
import type { HomeAdvantageFile } from '../lib/types'
import { useWidth } from '../lib/useWidth'

const ERA_COLORS = ['var(--era-1)', 'var(--era-2)', 'var(--era-3)']
// Temporadas que abarca cada era (2019-20 y 2020-21 comparten eras).
const ERA_SPANS: [string, string][] = [['2000-01', '2019-20'], ['2019-20', '2020-21'], ['2021-22', '']]

/** Diferencia de gol media del local por temporada (con IC) y media de cada era de público. */
export function HomeAdvantageChart({ data, compact = false }: { data: HomeAdvantageFile; compact?: boolean }) {
  const [ref, width] = useWidth<HTMLDivElement>(700)
  const [hover, setHover] = useState<number | null>(null)
  const height = compact ? 220 : 340
  const m = { top: 16, right: 12, bottom: 34, left: 40 }
  const seasons = data.seasons
  const x = scaleBand<string>().domain(seasons.map((s) => s.season)).range([m.left, width - m.right]).padding(0.2)
  const lo = Math.min(-0.25, ...seasons.map((s) => s.goal_diff_ci[0]))
  const hi = Math.max(0.85, ...seasons.map((s) => s.goal_diff_ci[1]))
  const y = scaleLinear().domain([lo, hi]).nice().range([height - m.bottom, m.top])
  const cx = (s: string) => (x(s) ?? 0) + x.bandwidth() / 2
  const band = area<(typeof seasons)[number]>().x((d) => cx(d.season)).y0((d) => y(d.goal_diff_ci[0])).y1((d) => y(d.goal_diff_ci[1]))
  const path = line<(typeof seasons)[number]>().x((d) => cx(d.season)).y((d) => y(d.goal_diff))
  const lastSeason = seasons[seasons.length - 1].season
  const hs = hover !== null ? seasons[hover] : null
  const labelEvery = width < 520 ? 5 : width < 800 ? 3 : 2

  return (
    <div ref={ref} className="chart-wrap">
      <svg width={width} height={height} role="img"
           aria-label="Diferencia de gol media del local por temporada, con la media de cada era de público">
        {y.ticks(5).map((t) => (
          <g key={t}>
            <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? 'var(--axis)' : 'var(--line)'} />
            <text x={m.left - 6} y={y(t) + 4} textAnchor="end">{t > 0 ? `+${t}` : t}</text>
          </g>
        ))}
        <path d={band(seasons) ?? ''} fill="var(--muted)" opacity={0.14} />
        <path d={path(seasons) ?? ''} fill="none" stroke="var(--ink-2)" strokeWidth={1.5} />
        {data.eras.map((e, i) => {
          const [a, b] = ERA_SPANS[i]
          const x1 = (x(a) ?? m.left) - x.step() * 0.1
          const x2 = (x(b || lastSeason) ?? 0) + x.bandwidth() + x.step() * 0.1
          return (
            <g key={e.era}>
              <line x1={x1} x2={x2} y1={y(e.goal_diff)} y2={y(e.goal_diff)} stroke={ERA_COLORS[i]} strokeWidth={4} strokeLinecap="round" />
              {!compact && (
                <text x={x1} y={y(e.goal_diff) + (i === 1 ? 18 : -10)} style={{ fill: ERA_COLORS[i], fontWeight: 700, fontSize: 12 }}>
                  {num(e.goal_diff, 2)}
                </text>
              )}
            </g>
          )
        })}
        {seasons.map((s, i) => (
          <g key={s.season}>
            <circle cx={cx(s.season)} cy={y(s.goal_diff)} r={hover === i ? 5 : 3} fill="var(--ink-2)" />
            <rect x={x(s.season)} y={m.top} width={x.bandwidth()} height={height - m.top - m.bottom} fill="transparent"
                  onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
            {i % labelEvery === 0 && (
              <text x={cx(s.season)} y={height - 12} textAnchor="middle">{s.season.slice(2)}</text>
            )}
          </g>
        ))}
      </svg>
      {hs && (
        <div className="tooltip" style={{ left: cx(hs.season), top: y(hs.goal_diff_ci[1]) }}>
          <strong>{hs.season}</strong> · {num(hs.matches, 0)} partidos<br />
          Dif. de gol del local: {num(hs.goal_diff, 2)} (IC 95% {num(hs.goal_diff_ci[0], 2)} a {num(hs.goal_diff_ci[1], 2)})<br />
          Local gana {pct(hs.home_win)} · empate {pct(hs.draw)} · visitante {pct(hs.away_win)}
        </div>
      )}
      <div className="small muted" style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 4 }}>
        {data.eras.map((e, i) => (
          <span key={e.era}><span style={{ display: 'inline-block', width: 14, height: 4, borderRadius: 2, background: ERA_COLORS[i], verticalAlign: 'middle', marginRight: 6 }} />{e.era}</span>
        ))}
        <span>Gris: cada temporada, con su IC 95%</span>
      </div>
    </div>
  )
}
