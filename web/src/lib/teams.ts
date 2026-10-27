import { useMemo } from 'react'
import { useLeagueData } from './league'
import type { TeamIndexItem } from './types'

/** Índice de clubes de la liga elegida (escudo, abreviatura, estadio) por nombre canónico y por slug. */
export function useTeamIndex() {
  const index = useLeagueData<TeamIndexItem[]>('teams.json')
  return useMemo(() => {
    const byTeam = new Map<string, TeamIndexItem>()
    const bySlug = new Map<string, TeamIndexItem>()
    for (const t of index.data ?? []) { byTeam.set(t.team, t); bySlug.set(t.slug, t) }
    return { list: index.data ?? [], byTeam, bySlug, loading: index.loading }
  }, [index.data, index.loading])
}
