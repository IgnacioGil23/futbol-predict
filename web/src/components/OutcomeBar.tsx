import { pct } from '../lib/data'
import { kitOf, sideColors } from '../lib/kits'
import { useTeamIndex } from '../lib/teams'
import type { Probabilities } from '../lib/types'
import { SplitBar } from './Motion'

interface Props {
  probs: Probabilities
  homeName: string
  awayName: string
  market?: Probabilities | null
  marketLabel?: string
  size?: 'md' | 'lg'
}

/** Barra 1X2 con el número en cada tramo y, si existe, la referencia del mercado debajo de cada resultado. */
export function OutcomeBar({ probs, homeName, awayName, market, marketLabel = 'Mercado (Bet365, sin margen)', size = 'md' }: Props) {
  const { list } = useTeamIndex()
  const colorsOf = (name: string) => list.find((t) => t.name === name)?.colors
  const { hc, ac } = sideColors(kitOf(homeName, colorsOf(homeName)), kitOf(awayName, colorsOf(awayName), '#777777'))
  const segs = [
    { key: 'home', label: homeName },
    { key: 'draw', label: 'Empate' },
    { key: 'away', label: awayName },
  ] as const
  return (
    <div className={`outcome outcome-${size}`}>
      <SplitBar probs={[probs.home, probs.draw, probs.away]} colors={[hc, ac]} height={size === 'lg' ? 44 : 32} font={size === 'lg' ? 16 : 13}
                label={`Local ${pct(probs.home)}, empate ${pct(probs.draw)}, visitante ${pct(probs.away)}`} />
      <div className="outcome-legend">
        {segs.map((s) => (
          <div key={s.key}>
            <div>{s.label}</div>
            {market && <div title={marketLabel}>mercado {pct(market[s.key])}</div>}
          </div>
        ))}
      </div>
      {market && <p className="outcome-market">{marketLabel}: probabilidades implícitas con el margen quitado (método de Shin).</p>}
    </div>
  )
}
