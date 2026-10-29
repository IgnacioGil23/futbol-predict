import { useState, type CSSProperties } from 'react'
import { kitBackground, kitOf, onColor, ring } from '../lib/kits'
import { useTeamIndex } from '../lib/teams'
import type { TeamColors } from '../lib/types'

interface Props {
  badge: string | null; short: string; name: string; size?: number
  decorative?: boolean   // true cuando el nombre del club ya está escrito al lado
  eager?: boolean        // escudos visibles al cargar (portada): sin lazy loading
  colors?: TeamColors | null
  className?: string
}

/**
 * Medallón del club. Con escudo de licencia libre: el escudo sobre un disco claro. Sin escudo (o si no carga): el aro
 * lleva el diseño de la camiseta y el centro, el código del club sobre su color. Nunca imita un escudo real.
 */
export function TeamBadge({ badge, short, name, size = 40, decorative = false, eager = false, colors, className = '' }: Props) {
  const [failed, setFailed] = useState(false)
  const { list } = useTeamIndex()
  const c = colors !== undefined ? colors : list.find((t) => t.name === name || t.short === short)?.colors
  const box: CSSProperties = { width: size, height: size }
  const a11y = decorative ? { 'aria-hidden': true as const } : { role: 'img', 'aria-label': name }
  if (badge && !failed) {
    return (
      <span className={`med crest team-badge ${className}`} style={box} {...a11y}>
        <img src={badge} alt="" width={size} height={size} loading={eager ? 'eager' : 'lazy'} decoding="async"
             onError={() => setFailed(true)} />
      </span>
    )
  }
  const kit = kitOf(name, c)
  return (
    <span className={`med kit team-badge team-initials ${className}`} style={box} {...a11y}>
      <span className="kitbg" style={{ background: kitBackground(kit) }} />
      <b style={{ background: kit.primary, color: onColor(kit.primary), boxShadow: ring(kit.primary), fontSize: Math.max(9, Math.round(size * 0.32)) }}>{short}</b>
    </span>
  )
}
