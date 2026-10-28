import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useData } from '../lib/data'
import { LEAGUE_STORAGE_KEY, LeagueContext, PREMIER, type LeagueInfo } from '../lib/league'

function stored(): string | null {
  try { return localStorage.getItem(LEAGUE_STORAGE_KEY) } catch { return null }
}

function remember(slug: string) {
  try { localStorage.setItem(LEAGUE_STORAGE_KEY, slug) } catch { /* sin storage */ }
}

/**
 * Liga elegida para todo el sitio.
 *
 * Fuera de la Premier, la URL lleva siempre `?liga=<slug>`: un enlace compartido abre la misma liga. Un enlace sin
 * `liga` es de la Premier; solo la portada usa la última liga elegida en este navegador.
 */
export function LeagueProvider({ children }: { children: ReactNode }) {
  const index = useData<LeagueInfo[]>('leagues.json')
  const [params, setParams] = useSearchParams()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const fromUrl = params.get('liga')
  const [chosen, setChosen] = useState<string>(() => fromUrl ?? (pathname === '/' ? stored() : null) ?? PREMIER.slug)
  // Un enlace con ?liga= pasa a ser la liga elegida (también después de navegar a otra página sin el parámetro).
  if (fromUrl && fromUrl !== chosen) setChosen(fromUrl)
  const slug = fromUrl ?? chosen
  const leagues = useMemo(() => (index.data?.length ? index.data : [PREMIER]), [index.data])
  const known = leagues.find((l) => l.slug === slug)
  const league = known ?? leagues[0]
  // Mientras carga leagues.json, una liga que no es la Premier todavía no se puede resolver: no se muestra la Premier
  // por un instante (cargaría sus datos y, en una ficha, diría que el equipo no existe).
  const waiting = index.loading && slug !== PREMIER.slug

  useEffect(() => {
    if (known && fromUrl === known.slug) remember(known.slug)          // solo ligas que existen
  }, [known, fromUrl])

  // La liga queda en la URL de cada página (fuera de la Premier), así se puede compartir.
  useEffect(() => {
    if (waiting || league.slug === PREMIER.slug || fromUrl === league.slug) return
    setParams((p) => { p.set('liga', league.slug); return p }, { replace: true })
  }, [waiting, league.slug, fromUrl, setParams])

  const setLeague = useCallback((next: string) => {
    setChosen(next)
    remember(next)
    const search = next === PREMIER.slug ? '' : `?liga=${next}`
    // Una ficha de equipo o una previa son de una liga: al cambiar de liga se vuelve a la lista o a una previa vacía.
    if (pathname.startsWith('/equipos/')) navigate({ pathname: '/equipos', search })
    else if (pathname === '/partidos/previa') navigate({ pathname, search })
    else setParams((p) => { if (next === PREMIER.slug) p.delete('liga'); else p.set('liga', next); return p }, { replace: true })
  }, [pathname, navigate, setParams])

  const value = useMemo(() => ({ league, leagues, setLeague }), [league, leagues, setLeague])
  if (waiting) return null
  return <LeagueContext.Provider value={value}>{children}</LeagueContext.Provider>
}
