import { scaleLinear } from 'd3-scale'
import { line } from 'd3-shape'
import { useMemo, useState } from 'react'
import { formatDate, num } from '../lib/data'
import type { XgMatch } from '../lib/types'
import { useWidth } from '../lib/useWidth'

interface Props { matches: XgMatch[]; window?: number; height?: number }

/** xG a favor y en contra partido a partido, como promedio móvil; tooltip con el partido. */
export function XgChart({ matches, window = 5, height = 220 }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>(600)
  const [hover, setHover] = useState<number | null>(null)
  const m = { top: 12, right: 16, bottom: 26, left: 36 }

  const points = useMemo(() => matches.map((mt, i) => {
    const w = matches.slice(Math.max(0, i - window + 1), i + 1)
    const avg = (f: (x: XgMatch) => number) => w.reduce((s, x) => s + f(x), 0) / w.length
    return { i, mt, xf: avg((x) => x.xg_for), xa: avg((x) => x.xg_against) }
  }), [matches, window])

  if (points.length < 2) return <p className="muted small">Todavía hay pocos partidos con xG para graficar.</p>

  const x = scaleLinear().domain([0, points.length - 1]).range([m.left, width - m.right])
  const top = Math.max(2.5, ...points.map((p) => Math.max(p.xf, p.xa)))
  const y = scaleLinear().domain([0, top]).nice().range([height - m.bottom, m.top])
  const pathFor = line<(typeof points)[number]>().x((p) => x(p.i)).y((p) => y(p.xf))
  const pathAgainst = line<(typeof points)[number]>().x((p) => x(p.i)).y((p) => y(p.xa))
  const seasonStarts = points.filter((p, k) => k > 0 && p.mt.season !== points[k - 1].mt.season)
  const h = hover === null ? null : points[hover]

  return (
    <div ref={ref} className="chart-wrap">
      <svg width={width} height={height} role="img" aria-label={`xG a favor y en contra, promedio de ${window} partidos`}
           onMouseMove={(e) => {
             const px = e.clientX - (e.currentTarget as SVGSVGElement).getBoundingClientRect().left
             const k = Math.round(x.invert(px))
             setHover(px >= m.left && px <= width - m.right ? Math.min(points.length - 1, Math.max(0, k)) : null)
           }}
           onMouseLeave={() => setHover(null)}>
        {y.ticks(4).map((t) => (
          <g key={t}>
            <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} stroke="var(--line)" />
            <text x={m.left - 6} y={y(t) + 4} textAnchor="end">{num(t, 1)}</text>
          </g>
        ))}
        {seasonStarts.map((p) => (
          <g key={p.mt.season}>
            <line x1={x(p.i - 0.5)} x2={x(p.i - 0.5)} y1={m.top} y2={height - m.bottom} stroke="var(--axis)" strokeDasharray="4 3" />
            <text x={x(p.i - 0.5) + 4} y={height - 8}>{p.mt.season}</text>
          </g>
        ))}
        <text x={m.left} y={height - 8}>{points[0].mt.season}</text>
        <path d={pathFor(points) ?? ''} fill="none" stroke="var(--home)" strokeWidth={2} strokeLinejoin="round" />
        <path d={pathAgainst(points) ?? ''} fill="none" stroke="var(--away)" strokeWidth={2} strokeLinejoin="round" />
        {h && (
          <g>
            <line x1={x(h.i)} x2={x(h.i)} y1={m.top} y2={height - m.bottom} stroke="var(--axis)" />
            <circle cx={x(h.i)} cy={y(h.xf)} r={4.5} fill="var(--home)" stroke="var(--surface)" strokeWidth={2} />
            <circle cx={x(h.i)} cy={y(h.xa)} r={4.5} fill="var(--away)" stroke="var(--surface)" strokeWidth={2} />
          </g>
        )}
      </svg>
      {h && (
        <div className="tooltip" style={{ left: x(h.i), top: m.top + 8 }}>
          <div><strong>{formatDate(h.mt.date)}</strong> · {h.mt.home ? 'vs' : 'en'} {h.mt.opponent} {h.mt.goals_for}-{h.mt.goals_against}</div>
          <div style={{ opacity: 0.85 }}>xG del partido: {num(h.mt.xg_for)} a favor · {num(h.mt.xg_against)} en contra</div>
          <div><span style={{ color: 'var(--home)' }}>●</span> Promedio a favor {num(h.xf)} · <span style={{ color: 'var(--away)' }}>●</span> en contra {num(h.xa)}</div>
        </div>
      )}
      <div className="small muted" style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 4 }}>
        <span><span style={{ display: 'inline-block', width: 14, height: 3, background: 'var(--home)', verticalAlign: 'middle', marginRight: 6 }} />xG a favor</span>
        <span><span style={{ display: 'inline-block', width: 14, height: 3, background: 'var(--away)', verticalAlign: 'middle', marginRight: 6 }} />xG en contra</span>
        <span>Promedio móvil de {window} partidos</span>
      </div>
    </div>
  )
}
