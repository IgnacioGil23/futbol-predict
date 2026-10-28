import { useEffect, useRef, useState } from 'react'
import { LEAGUE_FIELD } from '../lib/kits'
import { useLeague } from '../lib/league'
import { useCurtain } from '../lib/motion'
import './league-switcher.css'

/**
 * Selector de liga. `menu`: botón compacto con lista desplegable (barra superior). `pills`: todas las ligas a la
 * vista (encabezado de las páginas por liga).
 */
export function LeagueSwitcher({ variant = 'pills' }: { variant?: 'menu' | 'pills' }) {
  const { league, leagues, setLeague } = useLeague()
  const [open, setOpen] = useState(false)
  const curtain = useCurtain()
  // Cambiar de liga es un evento: la cortina del color de destino barre la pantalla y el cambio llega a los 360 ms.
  const pick = (slug: string) => (slug === league.slug ? setLeague(slug) : curtain(LEAGUE_FIELD[slug] ?? '#000000', () => setLeague(slug)))
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    const onDown = (e: MouseEvent) => { if (!(e.target instanceof Node) || !ref.current?.contains(e.target)) setOpen(false) }
    window.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => { window.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onDown) }
  }, [open])

  if (leagues.length < 2) return null

  if (variant === 'pills') {
    return (
      <div className="league-tabs" role="group" aria-label="Liga">
        {leagues.map((l) => (
          <button key={l.slug} type="button" className="league-tab" aria-pressed={l.slug === league.slug} onClick={() => pick(l.slug)}>
            {l.competition}
          </button>
        ))}
      </div>
    )
  }

  return (
    <div className={`league-menu ${open ? 'open' : ''}`} ref={ref}>
      <button type="button" className="league-menu-btn" aria-expanded={open} aria-controls="league-menu-list"
              onClick={() => setOpen(!open)}>
        <span className="league-menu-label">Liga</span>
        <span className="league-menu-name">{league.competition}</span>
        <span className="nav-caret" aria-hidden="true" />
      </button>
      <ul id="league-menu-list" className="league-menu-list" hidden={!open}>
        {leagues.map((l) => (
          <li key={l.slug}>
            <button type="button" aria-current={l.slug === league.slug ? 'true' : undefined}
                    onClick={() => { pick(l.slug); setOpen(false) }}>
              <strong>{l.competition}</strong><span className="muted small">{l.country}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
