import { pct } from '../lib/data'
import type { Probabilities } from '../lib/types'

interface Props {
  probs: Probabilities
  homeName: string
  awayName: string
  market?: Probabilities | null
  marketLabel?: string
  size?: 'md' | 'lg'
}

/** Barra 1X2 con etiquetas directas y, si existe, la referencia del mercado debajo de cada resultado. */
export function OutcomeBar({ probs, homeName, awayName, market, marketLabel = 'Mercado (Bet365, sin margen)', size = 'md' }: Props) {
  const segs = [
    { key: 'home', label: homeName, p: probs.home, color: 'var(--home)' },
    { key: 'draw', label: 'Empate', p: probs.draw, color: 'var(--draw)' },
    { key: 'away', label: awayName, p: probs.away, color: 'var(--away)' },
  ] as const
  const top = Math.max(probs.home, probs.draw, probs.away)
  return (
    <div className={`outcome outcome-${size}`}>
      <div className="outcome-track" style={{ gridTemplateColumns: `${probs.home}fr ${probs.draw}fr ${probs.away}fr` }}
           role="img" aria-label={`Local ${pct(probs.home)}, empate ${pct(probs.draw)}, visitante ${pct(probs.away)}`}>
        {segs.map((s) => <span key={s.key} style={{ background: s.color, opacity: s.p === top ? 1 : 0.78 }} />)}
      </div>
      <div className="outcome-labels">
        {segs.map((s) => (
          <div key={s.key} className={`outcome-${s.key}`}>
            <div className="outcome-pct tabular" style={s.p === top ? { color: s.color } : undefined}>{pct(s.p)}</div>
            <div className="outcome-name"><span className="dot" style={{ background: s.color }} />{s.label}</div>
            {market && <div className="small muted tabular" title={marketLabel}>mercado {pct(market[s.key])}</div>}
          </div>
        ))}
      </div>
      {market && <p className="small muted" style={{ marginTop: 10 }}>{marketLabel}: probabilidades implícitas con el margen quitado (método de Shin).</p>}
    </div>
  )
}
