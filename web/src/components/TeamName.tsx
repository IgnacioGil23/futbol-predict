import { Link } from 'react-router-dom'
import type { TeamIndexItem } from '../lib/types'
import { TeamBadge } from './TeamBadge'

interface Props { team?: TeamIndexItem; name: string; size?: number; to?: string | null; className?: string }

/** Escudo + nombre en una línea; enlaza a la ficha salvo que `to` sea null. */
export function TeamName({ team, name, size = 22, to, className }: Props) {
  const content = (
    <>
      {team ? <TeamBadge badge={team.badge} short={team.short} name={team.name} size={size} decorative /> : null}
      <span>{name}</span>
    </>
  )
  const href = to === undefined ? (team ? `/equipos/${team.slug}` : null) : to
  return href
    ? <Link to={href} className={`team-name ${className ?? ''}`}>{content}</Link>
    : <span className={`team-name ${className ?? ''}`}>{content}</span>
}
