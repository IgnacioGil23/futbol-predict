import { scaleLinear } from 'd3-scale'
import { line } from 'd3-shape'
import { pct } from '../lib/data'
import type { CalibrationBin, Outcome } from '../lib/types'
import { useWidth } from '../lib/useWidth'

const TITLES: Record<Outcome, string> = { H: 'Gana local', D: 'Empate', A: 'Gana visitante' }

/** Diagrama de confiabilidad (pronóstico vs frecuencia observada) para modelo y mercado. */
export function CalibrationChart({ model, market }: { model: CalibrationBin[]; market: CalibrationBin[] }) {
  const [ref, width] = useWidth<HTMLDivElement>(700)
  const cols = width < 560 ? 1 : 3
  const w = Math.floor((width - (cols - 1) * 16) / cols)
  const h = Math.min(w, 240)
  const m = { top: 24, right: 10, bottom: 28, left: 36 }
  const x = scaleLinear().domain([0, 1]).range([m.left, w - m.right])
  const y = scaleLinear().domain([0, 1]).range([h - m.bottom, m.top])
  const path = line<CalibrationBin>().x((d) => x(d.mean_predicted)).y((d) => y(d.observed))
  const series = [
    { name: 'Modelo', color: 'var(--home)', bins: model },
    { name: 'Mercado (Bet365)', color: 'var(--away)', bins: market },
  ]
  return (
    <div ref={ref}>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 16 }}>
        {(['H', 'D', 'A'] as Outcome[]).map((o) => (
          <div key={o} className="chart-wrap">
            <svg width={w} height={h} role="img" aria-label={`Calibración: ${TITLES[o]}`}>
              <text x={m.left} y={14} style={{ fill: 'var(--ink)', fontWeight: 650, fontSize: 12 }}>{TITLES[o]}</text>
              {[0, 0.25, 0.5, 0.75, 1].map((t) => (
                <g key={t}>
                  <line x1={x(t)} x2={x(t)} y1={m.top} y2={h - m.bottom} stroke="var(--line)" />
                  <line x1={m.left} x2={w - m.right} y1={y(t)} y2={y(t)} stroke="var(--line)" />
                  <text x={x(t)} y={h - 10} textAnchor="middle">{pct(t)}</text>
                  <text x={m.left - 4} y={y(t) + 4} textAnchor="end">{pct(t)}</text>
                </g>
              ))}
              <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--axis)" strokeDasharray="4 3" />
              {series.map((s) => {
                const bins = s.bins.filter((b) => b.outcome === o)
                return (
                  <g key={s.name}>
                    {bins.map((b) => (
                      <line key={b.bin} x1={x(b.mean_predicted)} x2={x(b.mean_predicted)} y1={y(b.ci_low)} y2={y(b.ci_high)}
                            stroke={s.color} strokeWidth={1.5} opacity={0.5} />
                    ))}
                    <path d={path(bins) ?? ''} fill="none" stroke={s.color} strokeWidth={2} />
                    {bins.map((b) => (
                      <circle key={b.bin} cx={x(b.mean_predicted)} cy={y(b.observed)} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={1.5}>
                        <title>{`${s.name}: pronosticó ${pct(b.mean_predicted)}, ocurrió ${pct(b.observed)} (${b.n} partidos)`}</title>
                      </circle>
                    ))}
                  </g>
                )
              })}
            </svg>
          </div>
        ))}
      </div>
      <div className="small muted" style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 6 }}>
        {series.map((s) => (
          <span key={s.name}><span style={{ display: 'inline-block', width: 14, height: 3, background: s.color, verticalAlign: 'middle', marginRight: 6 }} />{s.name}</span>
        ))}
        <span>Eje X: probabilidad pronosticada · Eje Y: frecuencia real · Diagonal: calibración perfecta · Barras: IC 95%</span>
      </div>
    </div>
  )
}
