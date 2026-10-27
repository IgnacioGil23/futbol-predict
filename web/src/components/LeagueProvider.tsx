import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useData } from '../lib/data'
import { LEAGUE_STORAGE_KEY, LeagueContext, PREMIER, type LeagueInfo } from '../lib/league'

function stored(): string | null {
  try { return localStorage.getItem(LEAGUE_STORAGE_KEY) } catch { return null }
}

/**
 * Liga elegida para todo el sitio. Se recuerda en el navegador y se puede compartir con `?liga=<slug>` en cualquier
 * página (por ejemplo `#/temporada?liga=laliga`).
 */
export function LeagueProvider({ children }: { children: ReactNode }) {
  const index = useData<LeagueInfo[]>('leagues.json')
  const [params, setParams] = useSearchParams()
  const fromUrl = params.get('liga')
  const [chosen, setChosen] = useState<string>(() => fromUrl ?? stored() ?? PREMIER.slug)
  // Un enlace con ?liga= pasa a ser la liga elegida (también después de navegar a otra página sin el parámetro).
  if (fromUrl && fromUrl !== chosen) setChosen(fromUrl)
  const slug = fromUrl ?? chosen
  const leagues = useMemo(() => (index.data?.length ? index.data : [PREMIER]), [index.data])
  const league = leagues.find((l) => l.slug === slug) ?? leagues[0]

  // Un enlace con ?liga= cambia la liga recordada.
  useEffect(() => {
    if (!fromUrl) return
    try { localStorage.setItem(LEAGUE_STORAGE_KEY, fromUrl) } catch { /* sin storage */ }
  }, [fromUrl])

  const setLeague = useCallback((next: string) => {
    setChosen(next)
    try { localStorage.setItem(LEAGUE_STORAGE_KEY, next) } catch { /* sin storage */ }
    setParams((p) => { p.delete('liga'); return p }, { replace: true })
  }, [setParams])

  const value = useMemo(() => ({ league, leagues, setLeague }), [league, leagues, setLeague])
  return <LeagueContext.Provider value={value}>{children}</LeagueContext.Provider>
}
