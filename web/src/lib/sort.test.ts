import { describe, expect, it } from 'vitest'
import { sortRows } from './sort'

const rows = [{ k: 'a', v: 2 }, { k: 'b', v: null }, { k: 'c', v: 5 }, { k: 'd', v: 1 }]
const value = (r: { v: number | null }) => r.v

describe('sortRows', () => {
  it('ordena de mayor a menor con los null al final', () => {
    expect(sortRows(rows, value, 'desc').map((r) => r.k)).toEqual(['c', 'a', 'd', 'b'])
  })
  it('ordena de menor a mayor con los null también al final', () => {
    expect(sortRows(rows, value, 'asc').map((r) => r.k)).toEqual(['d', 'a', 'c', 'b'])
  })
  it('no modifica el arreglo original', () => {
    sortRows(rows, value, 'desc')
    expect(rows.map((r) => r.k)).toEqual(['a', 'b', 'c', 'd'])
  })
})
