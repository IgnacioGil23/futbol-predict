import { useState } from 'react'

interface Props {
  badge: string | null; short: string; name: string; size?: number
  decorative?: boolean   // true cuando el nombre del club ya está escrito al lado
  eager?: boolean        // escudos visibles al cargar (portada): sin lazy loading
}

/** Escudo oficial del club (si su código está verificado) o sus iniciales. Si la imagen no carga, también iniciales. */
export function TeamBadge({ badge, short, name, size = 40, decorative = false, eager = false }: Props) {
  const [failed, setFailed] = useState(false)
  if (badge && !failed) {
    return (
      <img src={badge} alt={decorative ? '' : `Escudo de ${name}`} width={size} height={size}
           loading={eager ? 'eager' : 'lazy'} decoding="async"
           className="team-badge" onError={() => setFailed(true)} />
    )
  }
  return (
    <span className="team-badge team-initials" style={{ width: size, height: size, fontSize: size * 0.34 }}
          {...(decorative ? { 'aria-hidden': true } : { role: 'img', 'aria-label': name })}>
      {short}
    </span>
  )
}
