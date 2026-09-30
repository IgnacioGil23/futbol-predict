import { useMemo, useState } from 'react'
import { pct1 } from '../lib/data'
import { useWidth } from '../lib/useWidth'

interface Props {
  grid: number[][]          // [local][visitante]; se muestran 0..size-1
  homeName: string
  awayName: string
  actual?: [number, number] // resultado real (modo revisión)
  size?: number
  compact?: boolean         // sin la nota de lectura (portada)
}

const SEQ = ['var(--seq-1)', 'var(--seq-2)', 'var(--seq-3)', 'var(--seq-4)', 'var(--seq-5)']

/** Grilla de probabilidades de marcador exacto con marginales de goles por equipo. */
export function ScoreHeatmap({ grid, homeName, awayName, actual, size = 6, compact = false }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>(520)
  const [hover, setHover] = useState<[number, number] | null>(null)

  const cells = useMemo(() => grid.slice(0, size).map((row) => row.slice(0, size)), [grid, size])
  const max = Math.max(...cells.flat())
  const best = useMemo(() => {
    let b: [number, number] = [0, 0]
    cells.forEach((row, x) => row.forEach((p, y) => { if (p > cells[b[0]][b[1]]) b = [x, y] }))
    return b
  }, [cells])
  // Marginales sobre la grilla completa (no solo la parte visible).
  const homeMarg = grid.map((row) => row.reduce((a, b) => a + b, 0)).slice(0, size)
  const awayMarg = grid[0].map((_, y) => grid.reduce((a, row) => a + row[y], 0)).slice(0, size)
  const visibleMass = cells.flat().reduce((a, b) => a + b, 0)

  const margin = { left: 44, top: 40, right: 64, bottom: 8 }
  const cell = Math.max(34, Math.min(64, Math.floor((width - margin.left - margin.right) / size)))
  const gw = cell * size
  const svgW = margin.left + gw + margin.right
  const svgH = margin.top + gw + 56 + margin.bottom
  const barMax = Math.max(...homeMarg, ...awayMarg)
  const color = (p: number) => SEQ[Math.min(SEQ.length - 1, Math.floor((p / max) * SEQ.length * 0.999))]
  const textOn = (p: number) => (p / max > 0.55 ? 'var(--surface)' : 'var(--ink)')

  const focus = hover ?? best
  const focusP = grid[focus[0]][focus[1]]

  return (
    <div ref={ref} className="chart-wrap">
      <p className="heatmap-focus small muted" aria-live="polite">
        <strong>{homeName} <span className="heatmap-score tabular">{focus[0]}–{focus[1]}</span> {awayName}</strong>
        {' '}<span className="heatmap-p tabular">{pct1(focusP)}</span>
        {!hover && ' · el marcador más probable'}
        {actual && ` · resultado real ${actual[0]}-${actual[1]} (${pct1(grid[actual[0]]?.[actual[1]] ?? 0)})`}
      </p>
      <svg width={svgW} height={svgH} role="img"
           aria-label={`Probabilidad de cada marcador entre ${homeName} y ${awayName}`}
           style={{ maxWidth: '100%', height: 'auto', overflow: 'visible' }}
           viewBox={`0 0 ${svgW} ${svgH}`}>
        {/* encabezados */}
        <text x={margin.left + gw / 2} y={12} textAnchor="middle" style={{ fontWeight: 650, fill: 'var(--away)' }}>
          Goles {awayName}
        </text>
        <text transform={`translate(12 ${margin.top + gw / 2}) rotate(-90)`} textAnchor="middle"
              style={{ fontWeight: 650, fill: 'var(--home)' }}>
          Goles {homeName}
        </text>
        {Array.from({ length: size }, (_, i) => (
          <g key={i}>
            <text x={margin.left + i * cell + cell / 2} y={margin.top - 8} textAnchor="middle">{i}</text>
            <text x={margin.left - 8} y={margin.top + i * cell + cell / 2 + 4} textAnchor="end">{i}</text>
          </g>
        ))}
        {/* celdas */}
        {cells.map((row, x) => row.map((p, y) => {
          const isBest = x === best[0] && y === best[1]
          const isActual = actual && actual[0] === x && actual[1] === y
          const isHover = hover && hover[0] === x && hover[1] === y
          return (
            <g key={`${x}-${y}`} transform={`translate(${margin.left + y * cell} ${margin.top + x * cell})`}
               onMouseEnter={() => setHover([x, y])} onMouseLeave={() => setHover(null)}
               onFocus={() => setHover([x, y])} onBlur={() => setHover(null)}
               tabIndex={0} role="button" aria-label={`${homeName} ${x}, ${awayName} ${y}: ${pct1(p)}`}
               style={{ cursor: 'default', outline: 'none' }}>
              <rect x={1.5} y={1.5} width={cell - 3} height={cell - 3} rx={7} fill={color(p)}
                    stroke={isHover ? 'var(--ink)' : isBest ? 'var(--accent)' : x === y ? 'var(--axis)' : 'none'}
                    strokeWidth={isHover || isBest ? 2 : 1} strokeDasharray={x === y && !isHover && !isBest ? '3 3' : undefined}
                    style={{ transition: 'stroke 0.15s' }} />
              {cell >= 40 && (
                <text x={cell / 2} y={cell / 2 + 4} textAnchor="middle"
                      style={{ fill: textOn(p), fontSize: 11, fontWeight: isBest ? 700 : 500 }}>
                  {p >= 0.0005 ? (p * 100).toFixed(1).replace('.', ',') : '·'}
                </text>
              )}
              {isActual && <rect x={3} y={3} width={cell - 6} height={cell - 6} rx={4} fill="none"
                                 stroke="var(--away)" strokeWidth={2.5} />}
              {isBest && <circle cx={cell - 8} cy={8} r={3} fill={textOn(p)} />}
            </g>
          )
        }))}
        {/* marginal del local (derecha) */}
        {homeMarg.map((p, x) => (
          <g key={`hm${x}`} transform={`translate(${margin.left + gw + 8} ${margin.top + x * cell})`}>
            <rect y={cell * 0.25} height={cell * 0.5} width={Math.max(2, (p / barMax) * (margin.right - 30))}
                  rx={3} fill="var(--home)" opacity={0.85} />
            <text x={Math.max(2, (p / barMax) * (margin.right - 30)) + 4} y={cell / 2 + 4} style={{ fontSize: 10 }}>
              {Math.round(p * 100)}%
            </text>
          </g>
        ))}
        {/* marginal del visitante (abajo) */}
        {awayMarg.map((p, y) => {
          const h = Math.max(2, (p / barMax) * 40)
          return (
            <g key={`am${y}`} transform={`translate(${margin.left + y * cell} ${margin.top + gw + 6})`}>
              <rect x={cell * 0.25} width={cell * 0.5} height={h} rx={3} fill="var(--away)" opacity={0.85} />
              <text x={cell / 2} y={h + 11} textAnchor="middle" style={{ fontSize: 10 }}>{Math.round(p * 100)}%</text>
            </g>
          )
        })}
      </svg>
      {!compact && <p className="small muted" style={{ marginTop: 6 }}>
        Números en %: probabilidad de cada marcador (· = menos de 0,05%). Diagonal punteada: empates. Barras: probabilidad de que cada
        equipo marque exactamente esa cantidad de goles. La grilla muestra el {pct1(visibleMass)} de la probabilidad
        (el resto son marcadores con 6 goles o más de algún equipo).
      </p>}
    </div>
  )
}
