import { createContext, useContext } from 'react'
import { useData } from './data'

/** Una liga publicada (leagues.json, que exporta `python -m src.export.site`). */
export interface LeagueInfo {
  code: string
  slug: string
  competition: string
  country: string
  /** Segunda división (los ascendidos llegan con historia de Elo de ahí). */
  second: string
  /** Códigos de Football-Data de la primera y la segunda división (E0/E1, SP1/SP2, …). */
  top_division: string
  second_division: string
  /** Carpeta de sus JSON dentro de /data ('' = la Premier, en la raíz). */
  path: string
  relegation: number
  playoff: number | null
  head_to_head: boolean
  model_version: string
}

// Mientras carga leagues.json (o si falta), el sitio funciona con la Premier.
export const PREMIER: LeagueInfo = {
  code: 'ENG', slug: 'premier', competition: 'Premier League', country: 'Inglaterra', second: 'Championship',
  top_division: 'E0', second_division: 'E1', path: '',
  relegation: 3, playoff: null, head_to_head: false, model_version: '',
}

export const LEAGUE_STORAGE_KEY = 'liga'

export interface LeagueState { league: LeagueInfo; leagues: LeagueInfo[]; setLeague: (slug: string) => void }

export const LeagueContext = createContext<LeagueState>({ league: PREMIER, leagues: [PREMIER], setLeague: () => {} })

export function useLeague(): LeagueState {
  return useContext(LeagueContext)
}

/** Ruta de un JSON de la liga elegida dentro de /data. */
export function leagueFile(league: LeagueInfo, file: string): string {
  return `${league.path}${file}`
}

/** `useData` sobre los JSON de la liga elegida (state.json, upcoming.json, teams/<slug>.json, …). */
export function useLeagueData<T>(file: string | null) {
  const { league } = useLeague()
  return useData<T>(file === null ? null : leagueFile(league, file))
}
