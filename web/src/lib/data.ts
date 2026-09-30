import { useEffect, useState } from 'react'
import type { ApiPrediction } from './types'

const cache = new Map<string, Promise<unknown>>()

/** Carga (y cachea) un JSON de /data. */
export function loadData<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    const url = `${import.meta.env.BASE_URL}data/${path}`
    const p = fetch(url).then((r) => {
      if (!r.ok) throw new Error(`No se pudo cargar ${path} (${r.status})`)
      return r.json()
    })
    p.catch(() => cache.delete(path))
    cache.set(path, p)
  }
  return cache.get(path) as Promise<T>
}

export interface Async<T> { data: T | null; error: string | null; loading: boolean }

export function useData<T>(path: string | null): Async<T> {
  // Se guarda el resultado junto con la ruta que lo produjo: si la ruta cambia, el
  // estado de carga se deriva en el render (sin setState sincrónico en el efecto).
  const [result, setResult] = useState<{ path: string; data: T | null; error: string | null } | null>(null)
  useEffect(() => {
    if (!path) return
    let alive = true
    loadData<T>(path)
      .then((data) => alive && setResult({ path, data, error: null }))
      .catch((e: Error) => alive && setResult({ path, data: null, error: e.message }))
    return () => { alive = false }
  }, [path])
  if (!path) return { data: null, error: null, loading: false }
  if (!result || result.path !== path) return { data: null, error: null, loading: true }
  return { data: result.data, error: result.error, loading: false }
}

// ------------------------------------------------------------------- API
export const API_URL: string | undefined = import.meta.env.VITE_API_URL || undefined

export async function fetchPrediction(home: string, away: string, date: string, signal?: AbortSignal): Promise<ApiPrediction> {
  if (!API_URL) throw new Error('La API no está configurada en esta versión del sitio.')
  const params = new URLSearchParams({ home, away, date })
  const r = await fetch(`${API_URL}/predict?${params}`, { signal })
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Error ${r.status} de la API`)
  return body as ApiPrediction
}

// ------------------------------------------------------------- formato
const pctFmt = new Intl.NumberFormat('es-AR', { style: 'percent', maximumFractionDigits: 0 })
const pct1Fmt = new Intl.NumberFormat('es-AR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 })
const numFmt = (d: number) => new Intl.NumberFormat('es-AR', { minimumFractionDigits: d, maximumFractionDigits: d })

export const pct = (x: number) => pctFmt.format(x)
export const pct1 = (x: number) => pct1Fmt.format(x)
export const num = (x: number, digits = 2) => numFmt(digits).format(x)
export const signedPct = (x: number) => `${x > 0 ? '+' : ''}${pctFmt.format(x)}`

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' }) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('es-AR', { ...opts, timeZone: 'UTC' })
}
