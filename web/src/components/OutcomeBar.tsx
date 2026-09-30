import { pct } from '../lib/data'
import type { Probabilities } from '../lib/types'

interface Props {
  probs: Probabilities
  homeName: string
  awayName: string
  market?: Probabilities | null
  marketLabel?: string
}

/** Barra 1X2 con etiquetas directas y, si existe, la referencia del mercado como marcas. */
export function OutcomeBar({ probs, homeName, awayName, market, marketLabel = 'Mercado (Bet365, sin margen)' }: Props) {
  const segs = [
    { key: 'home', label: homeName, p: probs.home, color: 'var(--home)' },
    { key: 'draw', label: 'Empate', p: probs.draw, color: 'var(--draw)' },
    { key: 'away', label: awayName, p: probs.away, color: 'var(--away)' },
  ] as const
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: `${probs.home}fr ${probs.draw}fr ${probs.away}fr`, gap: 3 }}
           role="img" aria-label={`Local ${pct(probs.home)}, empate ${pct(probs.draw)}, visitante ${pct(probs.away)}`}>
        {segs.map((s, i) => (
          <div key={s.key} style={{
            background: s.color, height: 14, minWidth: 4,
            borderRadius: i === 0 ? '7px 3px 3px 7px' : i === 2 ? '3px 7px 7px 3px' : 3,
          }} />
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', marginTop: 10, gap: 8 }}>
        {segs.map((s, i) => (
          <div key={s.key} style={{ textAlign: i === 0 ? 'left' : i === 1 ? 'center' : 'right', minWidth: 0 }}>
            <div className="tabular" style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: '2rem', lineHeight: 1 }}>
              {pct(s.p)}
            </div>
            <div className="small" style={{ color: 'var(--ink-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: s.color, marginRight: 6 }} />
              {s.label}
            </div>
            {market && (
              <div className="small muted tabular" title={marketLabel}>
                mercado {pct(market[s.key])}
              </div>
            )}
          </div>
        ))}
      </div>
      {market && <p className="small muted" style={{ marginTop: 8 }}>{marketLabel}: probabilidades implícitas con el margen quitado (método de Shin).</p>}
    </div>
  )
}
