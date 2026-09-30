import { extent, bisector } from 'd3-array'
import { scaleLinear, scaleUtc } from 'd3-scale'
import { line } from 'd3-shape'
import { useMemo, useState } from 'react'
import { formatDate, num } from '../lib/data'
import type { EloPoint } from '../lib/types'
import { useWidth } from '../lib/useWidth'

export interface EloSeries { name: string; color: string; points: EloPoint[] }

interface Props { series: EloSeries[]; height?: number; markDate?: string }

const toDate = (s: string) => new Date(`${s.slice(0, 10)}T00:00:00Z`)

/** Evolución del Elo; tramos jugados en Championship en línea punteada. Tooltip con cursor. */
export function EloChart({ series, height = 260, markDate }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>(600)
  const [hoverX, setHoverX] = useState<number | null>(null)
  const m = { top: 12, right: 16, bottom: 26, left: 44 }
  const all = series.flatMap((s) => s.points)

  const { x, y } = useMemo(() => {
    const xd = extent(all, (p) => toDate(p.date)) as [Date, Date]
    const yd = extent(all, (p) => p.elo) as [number, number]
    const pad = Math.max(20, (yd[1] - yd[0]) * 0.08)
    return {
      x: scaleUtc().domain(xd[0] ? xd : [new Date(0), new Date(0)]).range([m.left, width - m.right]),
      y: scaleLinear().domain([yd[0] - pad, yd[1] + pad]).nice().range([height - m.bottom, m.top]),
    }
  }, [all, width, height, m.left, m.right, m.bottom, m.top])

  if (!all.length) return <p className="muted small">Sin historial de Elo para mostrar.</p>

  const path = line<EloPoint>().x((p) => x(toDate(p.date))).y((p) => y(p.elo))
  const byDate = bisector<EloPoint, Date>((p) => toDate(p.date)).left
  const hovered = hoverX === null ? [] : series.map((s) => {
    const d = x.invert(hoverX)
    const i = Math.min(s.points.length - 1, Math.max(0, byDate(s.points, d) - 1))
    return { s, p: s.points[i] }
  }).filter((h) => h.p)

  // Tramos consecutivos por división (Championship punteado).
  const segments = (pts: EloPoint[]) => {
    const out: { div: string; pts: EloPoint[] }[] = []
    pts.forEach((p, i) => {
      if (!out.length || out[out.length - 1].div !== p.division) out.push({ div: p.division, pts: i ? [pts[i - 1]] : [] })
      out[out.length - 1].pts.push(p)
    })
    return out
  }

  return (
    <div ref={ref} className="chart-wrap">
      <svg width={width} height={height} role="img" aria-label="Evolución del Elo"
           onMouseMove={(e) => {
             const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
             const px = e.clientX - rect.left
             setHoverX(px >= m.left && px <= width - m.right ? px : null)
           }}
           onMouseLeave={() => setHoverX(null)}>
        {y.ticks(5).map((t) => (
          <g key={t}>
            <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} stroke="var(--line)" />
            <text x={m.left - 6} y={y(t) + 4} textAnchor="end">{t}</text>
          </g>
        ))}
        {(() => {
          // Rangos largos: solo el año. Rangos cortos: mes y año (si no, se repetiría el año).
          const [d0, d1] = x.domain()
          const years = (d1.getTime() - d0.getTime()) / (365.25 * 864e5)
          const fmt = (t: Date) => years > 4
            ? String(t.getUTCFullYear())
            : t.toLocaleDateString('es-AR', { month: 'short', year: '2-digit', timeZone: 'UTC' })
          return x.ticks(width < 500 ? 4 : years > 4 ? 8 : 6).map((t) => (
            <text key={t.toISOString()} x={x(t)} y={height - 6} textAnchor="middle">{fmt(t)}</text>
          ))
        })()}
        {markDate && (
          <line x1={x(toDate(markDate))} x2={x(toDate(markDate))} y1={m.top} y2={height - m.bottom}
                stroke="var(--axis)" strokeDasharray="4 3" />
        )}
        {series.map((s) => segments(s.points).map((seg, i) => (
          <path key={`${s.name}-${i}`} d={path(seg.pts) ?? ''} fill="none" stroke={s.color}
                strokeWidth={2} strokeDasharray={seg.div === 'E1' ? '4 3' : undefined} strokeLinejoin="round" />
        )))}
        {hoverX !== null && (
          <g>
            <line x1={hoverX} x2={hoverX} y1={m.top} y2={height - m.bottom} stroke="var(--axis)" />
            {hovered.map(({ s, p }) => (
              <circle key={s.name} cx={x(toDate(p.date))} cy={y(p.elo)} r={4.5} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
            ))}
          </g>
        )}
      </svg>
      {hoverX !== null && hovered.length > 0 && (
        <div className="tooltip" style={{ left: hoverX, top: m.top + 8 }}>
          {hovered.map(({ s, p }) => (
            <div key={s.name}>
              <span style={{ color: s.color }}>●</span> {s.name}: <strong>{num(p.elo, 0)}</strong>
              <span style={{ opacity: 0.75 }}> · {formatDate(p.date)} · {p.home ? 'vs' : 'en'} {p.opponent} {p.score}{p.division === 'E1' ? ' (Championship)' : ''}</span>
            </div>
          ))}
        </div>
      )}
      <div className="small muted" style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 4 }}>
        {series.map((s) => (
          <span key={s.name}><span style={{ display: 'inline-block', width: 14, height: 3, background: s.color, verticalAlign: 'middle', marginRight: 6 }} />{s.name}</span>
        ))}
        <span>- - - en Championship</span>
      </div>
    </div>
  )
}
