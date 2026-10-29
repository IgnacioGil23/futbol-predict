import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { formatDate, REPO } from '../lib/data'
import { LEAGUE_CLASS } from '../lib/kits'
import { useLeague, useLeagueData } from '../lib/league'
import type { MetaFile } from '../lib/types'
import { Icon } from './Icon'
import { LeagueSwitcher } from './LeagueSwitcher'
import { MotionContext, reducedMotion } from '../lib/motion'
import './layout.css'

type NavItem = { to: string; label: string }
const NAV: { label: string; to?: string; items?: NavItem[] }[] = [
  { label: 'Partidos', to: '/partidos' },
  { label: 'Liga', items: [
    { to: '/temporada', label: 'Tabla y proyección' },
    { to: '/estadisticas', label: 'Estadísticas' },
    { to: '/equipos', label: 'Equipos' } ] },
  { label: 'El modelo', items: [
    { to: '/metodologia', label: 'Cómo funciona' },
    { to: '/revision', label: 'Revisión' },
    { to: '/monitoreo', label: 'Monitoreo' } ] },
]

const FOOTER_LINKS: NavItem[] = [
  { to: '/partidos', label: 'Partidos' },
  { to: '/partidos/previa', label: 'Armar una previa' },
  ...NAV.flatMap((g) => g.items ?? []),
]

const isIn = (pathname: string, to: string) => pathname === to || pathname.startsWith(`${to}/`)
const groupActive = (pathname: string, items: NavItem[]) => items.some((i) => isIn(pathname, i.to))

type Theme = 'light' | 'dark'

// Oscuro por defecto; index.html aplica el tema guardado antes del primer pintado (sin parpadeo).
function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'))
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#110A16' : '#F3EDF7')
    try { localStorage.setItem('theme', theme) } catch { /* sin storage */ }
  }, [theme])
  return { isDark: theme === 'dark', toggle: () => setTheme(theme === 'dark' ? 'light' : 'dark') }
}

/** Píldora que se desliza hasta el enlace activo del menú (solo en escritorio). */
function useNavIndicator(pathname: string) {
  const navRef = useRef<HTMLElement>(null)
  const [box, setBox] = useState<{ left: number; width: number } | null>(null)
  useLayoutEffect(() => {
    const nav = navRef.current
    if (!nav) return
    const measure = () => {
      // Posición relativa al <nav> (no offsetLeft: los botones de grupo están dentro de un .nav-group posicionado).
      const active = nav.querySelector<HTMLElement>('.nav-top.active')
      const left = active ? active.getBoundingClientRect().left - nav.getBoundingClientRect().left - nav.clientLeft : 0
      setBox(active ? { left, width: active.offsetWidth } : null)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(nav)
    return () => ro.disconnect()
  }, [pathname])
  return { navRef, box }
}

const menuId = (label: string) => `nav-menu-${label.toLowerCase().replace(/\s+/g, '-')}`

const THEME_CURTAIN = { toLight: '#F3EFF5', toDark: '#0C0A10' }

/**
 * Clases del sistema visual en <html>: tema (t-oscuro / t-claro) y liga (lg-*), tomados del estado que ya existe.
 * `motion` habilita las animaciones (no con movimiento reducido) y el paso a `go` reinicia la entrada de la pantalla.
 */
function useSystemClasses(isDark: boolean, leagueSlug: string, pathname: string) {
  useLayoutEffect(() => {
    const root = document.documentElement
    root.classList.toggle('t-oscuro', isDark)
    root.classList.toggle('t-claro', !isDark)
    const current = LEAGUE_CLASS[leagueSlug] ?? 'lg-premier'
    for (const c of Object.values(LEAGUE_CLASS)) root.classList.toggle(c, c === current)
  }, [isDark, leagueSlug])
  useLayoutEffect(() => {
    const root = document.documentElement
    if (reducedMotion()) { root.classList.remove('motion', 'go'); return }
    root.classList.add('motion')
    root.classList.remove('go')
    const r = requestAnimationFrame(() => requestAnimationFrame(() => root.classList.add('go')))
    return () => cancelAnimationFrame(r)
  }, [isDark, leagueSlug, pathname])
}

/** Cortina de cambio de liga o de tema: barre la pantalla (340 ms), aplica el cambio a los 360 ms y se desvanece. */
function useCurtainState() {
  const [wipe, setWipe] = useState<{ phase: 'idle' | 'on' | 'off'; color: string }>({ phase: 'idle', color: 'transparent' })
  const timers = useRef<number[]>([])
  useEffect(() => () => timers.current.forEach(clearTimeout), [])
  const curtain = useCallback((color: string, apply: () => void) => {
    if (reducedMotion()) { apply(); return }
    timers.current.forEach(clearTimeout)
    setWipe({ phase: 'on', color })
    timers.current = [
      window.setTimeout(() => { apply(); setWipe({ phase: 'off', color }) }, 360),
      window.setTimeout(() => setWipe({ phase: 'idle', color }), 700),
    ]
  }, [])
  return { wipe, curtain }
}

/** El reflector del band respira solo mientras el band está en pantalla. */
function useFloodlight() {
  const ref = useRef<HTMLDivElement>(null)
  const [lit, setLit] = useState(true)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(([e]) => setLit(e.isIntersecting))
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return { ref, lit }
}

export function Layout() {
  const { isDark, toggle } = useTheme()
  const meta = useLeagueData<MetaFile>('meta.json')
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const { navRef, box } = useNavIndicator(pathname)
  const { league } = useLeague()
  useSystemClasses(isDark, league.slug, pathname)
  const { wipe, curtain } = useCurtainState()
  const { ref: bandRef, lit } = useFloodlight()
  const [slot, setSlot] = useState<HTMLDivElement | null>(null)
  const motion = useMemo(() => ({ slot, curtain }), [slot, curtain])
  const switchTheme = () => curtain(isDark ? THEME_CURTAIN.toLight : THEME_CURTAIN.toDark, toggle)
  const [groupAt, setGroupAt] = useState<{ label: string; path: string } | null>(null)
  const group = groupAt?.path === pathname ? groupAt.label : null
  const setGroup = (label: string | null) => setGroupAt(label ? { label, path: pathname } : null)

  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  useEffect(() => {
    if (!group) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setGroupAt(null)
      // El foco vuelve al botón del grupo (si quedaba en un enlace del menú, que se oculta, se perdería).
      document.querySelector<HTMLElement>(`[aria-controls="${menuId(group)}"]`)?.focus()
    }
    const onDown = (e: MouseEvent) => {
      if (!(e.target instanceof Element) || !e.target.closest('.nav-group')) setGroupAt(null)
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [group])
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <MotionContext.Provider value={motion}>
      <a href="#main" className="skip">Saltar al contenido</a>
      <svg className="grain" aria-hidden="true">
        <filter id="grainf"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves={2} stitchTiles="stitch" /><feColorMatrix type="saturate" values="0" /></filter>
        <rect width="100%" height="100%" filter="url(#grainf)" />
      </svg>
      <div className={`wipe ${wipe.phase === 'idle' ? '' : wipe.phase}`} aria-hidden="true" style={{ background: wipe.color }} />
      <div className="band site-band" ref={bandRef}>
        <div className={`light ${lit ? '' : 'idle'}`} aria-hidden="true" />
        <header className={`topbar ${scrolled || open ? 'scrolled' : ''}`}>
          <div className="container topbar-inner">
            <NavLink to="/" className="brand" aria-label="Marcador Probable, inicio" onClick={() => setOpen(false)}>
              <span className="brand-name">Marcador Probable</span>
              <span className="brand-sub">Cinco ligas · ML</span>
            </NavLink>
            <nav id="nav" ref={navRef} className={`nav ${open ? 'open' : ''}`} aria-label="Principal">
              {box && <span className="nav-indicator" style={{ transform: `translateX(${box.left}px)`, width: box.width }} aria-hidden="true" />}
              {NAV.map((g) => {
                if (!g.items) {
                  return (
                    <NavLink key={g.label} to={g.to!} onClick={() => setOpen(false)}
                             className={() => `nav-top${isIn(pathname, g.to!) ? ' active' : ''}`}>{g.label}</NavLink>
                  )
                }
                const active = groupActive(pathname, g.items)
                const expanded = group === g.label
                return (
                  <div key={g.label} className={`nav-group ${expanded ? 'expanded' : ''}`}
                       onBlur={(e) => {
                         // Con Tab fuera del grupo, el menú se cierra.
                         if (expanded && !(e.relatedTarget instanceof Node && e.currentTarget.contains(e.relatedTarget))) setGroup(null)
                       }}>
                    <button type="button" className={`nav-top nav-group-btn${active ? ' active' : ''}`}
                            aria-expanded={expanded} aria-controls={menuId(g.label)}
                            onClick={() => setGroup(expanded ? null : g.label)}>
                      {g.label}<span className="nav-caret" aria-hidden="true" />
                    </button>
                    <div className="nav-group-label">{g.label}</div>
                    <div className="nav-menu" id={menuId(g.label)}>
                      {g.items.map((it) => (
                        <NavLink key={it.to} to={it.to} onClick={() => { setOpen(false); setGroup(null) }}
                                 className={({ isActive }) => (isActive ? 'active' : undefined)}>{it.label}</NavLink>
                      ))}
                    </div>
                  </div>
                )
              })}
            </nav>
            <div className="topbar-actions">
              <button type="button" className="btn theme-btn" onClick={switchTheme} aria-label={isDark ? 'Cambiar a tema día' : 'Cambiar a tema noche'}>
                {isDark ? 'Noche' : 'Día'}
              </button>
              <button type="button" className="btn menu-btn" aria-expanded={open} aria-controls="nav" aria-label={open ? 'Cerrar menú' : 'Abrir menú'}
                      onClick={() => setOpen(!open)}>
                <Icon name={open ? 'close' : 'menu'} />
              </button>
            </div>
          </div>
          <div className="container league-row">
            <LeagueSwitcher />
          </div>
        </header>
        <div ref={setSlot} className="band-slot" />
      </div>
      {open && <div className="nav-scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
      <main id="main" tabIndex={-1}><Outlet /></main>
      <footer className="footer">
        <div className="container">
          <div className="footer-grid">
            <div className="footer-brand">
              <Link to="/" className="brand" aria-label="Inicio">
                <span className="brand-name">Marcador Probable</span>
              </Link>
              <p className="small muted">
                Proyecto de portfolio de Machine Learning: un modelo de Poisson sobre Elo que calcula la probabilidad de
                cada marcador de la Premier League, LaLiga, la Serie A, la Bundesliga y la Ligue 1. Probabilidades, no
                certezas: el modelo no conoce lesiones, alineaciones ni noticias.
              </p>
              <a className="btn btn-sm" href={REPO} target="_blank" rel="noreferrer"><Icon name="github" size={16} /> Código en GitHub</a>
            </div>
            <div>
              <div className="footer-title">Explorar</div>
              <ul className="footer-links">
                {FOOTER_LINKS.map((l) => <li key={l.to}><Link to={l.to}>{l.label}</Link></li>)}
              </ul>
            </div>
            <div>
              <div className="footer-title">Datos</div>
              <ul className="footer-links">
                {(meta.data?.sources ?? []).map((s) => (
                  <li key={s.name}><a href={s.url} target="_blank" rel="noreferrer">{s.name}</a></li>
                ))}
                <li><a href="https://commons.wikimedia.org/" target="_blank" rel="noreferrer">Wikimedia Commons</a> <span className="muted">(fotos de estadios y escudos de las otras ligas)</span></li>
              </ul>
            </div>
          </div>
          <div className="footer-bottom small muted">
            <span>{meta.data ? <>Datos actualizados al {formatDate(meta.data.last_match_in_data)}</> : ' '}</span>
            <span>No es un servicio de apuestas.</span>
          </div>
        </div>
      </footer>
    </MotionContext.Provider>
  )
}
