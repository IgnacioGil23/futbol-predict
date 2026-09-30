import { useState } from 'react'

interface Props { badge: string | null; short: string; name: string; size?: number }

/** Escudo oficial del club (si su código está verificado) o sus iniciales. Si la imagen no carga, también iniciales. */
export function TeamBadge({ badge, short, name, size = 40 }: Props) {
  const [failed, setFailed] = useState(false)
  if (badge && !failed) {
    return (
      <img src={badge} alt={`Escudo de ${name}`} width={size} height={size} loading="lazy" decoding="async"
           className="team-badge" onError={() => setFailed(true)} />
    )
  }
  return (
    <span className="team-badge team-initials" style={{ width: size, height: size, fontSize: size * 0.3 }}
          role="img" aria-label={name}>
      {short}
    </span>
  )
}
