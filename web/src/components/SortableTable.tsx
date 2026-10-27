import { useState, type ReactNode } from 'react'
import { sortRows, type SortDir } from '../lib/sort'

export interface Column<T> {
  key: string
  label: string
  value: (r: T) => number | null
  format: (v: number) => string
  /** Qué es mejor: define el primer orden al hacer clic en la columna. */
  better: 'high' | 'low'
  title?: string
}

interface Props<T> {
  rows: T[]
  columns: Column<T>[]
  /** Primera columna (el equipo o el árbitro): no se ordena. */
  label: { title: string; render: (r: T) => ReactNode }
  rowKey: (r: T) => string
  initialSort: string
  caption?: string
}

/** Tabla con orden por columna (clic en el encabezado; un segundo clic invierte el orden). */
export function SortableTable<T>({ rows, columns, label, rowKey, initialSort, caption }: Props<T>) {
  const first = columns.find((c) => c.key === initialSort) ?? columns[0]
  const [sort, setSort] = useState<{ key: string; dir: SortDir }>({
    key: first.key, dir: first.better === 'high' ? 'desc' : 'asc',
  })
  const active = columns.find((c) => c.key === sort.key) ?? first
  const sorted = sortRows(rows, active.value, sort.dir)
  const onSort = (c: Column<T>) => setSort((s) => (s.key === c.key
    ? { key: c.key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
    : { key: c.key, dir: c.better === 'high' ? 'desc' : 'asc' }))

  return (
    <div className="table-wrap">
      <table className="table sortable">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            <th scope="col">{label.title}</th>
            {columns.map((c) => {
              const isActive = c.key === sort.key
              return (
                <th key={c.key} scope="col" className="num"
                    aria-sort={isActive ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" className={`sort-btn ${isActive ? 'active' : ''}`} onClick={() => onSort(c)}
                          title={c.title}>
                    {c.label}
                    <span className="sort-caret" aria-hidden="true">{isActive ? (sort.dir === 'asc' ? '▲' : '▼') : ''}</span>
                  </button>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={rowKey(r)}>
              <td>{label.render(r)}</td>
              {columns.map((c) => {
                const v = c.value(r)
                return <td key={c.key} className={`num tabular ${c.key === sort.key ? 'sorted' : ''}`}>{v === null ? '—' : c.format(v)}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
