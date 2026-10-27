export type SortDir = 'asc' | 'desc'

/** Copia ordenada de `rows`; los null quedan siempre al final. */
export function sortRows<T>(rows: T[], value: (r: T) => number | null, dir: SortDir): T[] {
  const sign = dir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => {
    const va = value(a)
    const vb = value(b)
    if (va === null && vb === null) return 0
    if (va === null) return 1
    if (vb === null) return -1
    return sign * (va - vb)
  })
}
