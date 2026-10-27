import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { formatDate, REPO, useData } from '../lib/data'
import type { MetaFile } from '../lib/types'
import { BrandMark, Icon } from './Icon'
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
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#05080a' : '#f3f4ef')
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

export function Layout() {
  const { isDark, toggle } = useTheme()
  const meta = useData<MetaFile>('meta.json')
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const { navRef, box } = useNavIndicator(pathname)
  const [groupAt, setGroupAt] = useState<{ label: string; path: string } | null>(null)
  const group = groupAt?.path === pathname ? groupAt.label : null
  const setGroup = (label: string | null) => setGroupAt(label ? { label, path: pathname } : null)

  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  useEffect(() => {
    if (!group) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setGroupAt(null) }
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
    <>
      <a href="#main" className="skip">Saltar al contenido</a>
      <header className={`topbar ${scrolled || open ? 'scrolled' : ''}`}>
        <div className="container topbar-inner">
          <NavLink to="/" className="brand" aria-label="Marcador Probable, inicio" onClick={() => setOpen(false)}>
            <BrandMark size={32} />
            <span className="brand-text">
              <span className="brand-name">Marcador Probable</span>
              <span className="brand-sub">Premier League · ML</span>
            </span>
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
                <div key={g.label} className={`nav-group ${expanded ? 'expanded' : ''}`}>
                  <button type="button" className={`nav-top nav-group-btn${active ? ' active' : ''}`}
                          aria-expanded={expanded} aria-haspopup="true"
                          onClick={() => setGroup(expanded ? null : g.label)}>
                    {g.label}<span className="nav-caret" aria-hidden="true" />
                  </button>
                  <div className="nav-group-label">{g.label}</div>
                  <div className="nav-menu">
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
            <button className="icon-btn" onClick={toggle} aria-label={isDark ? 'Usar modo claro' : 'Usar modo oscuro'} title="Cambiar tema">
              <Icon name={isDark ? 'sun' : 'moon'} />
            </button>
            <button className="icon-btn menu-btn" aria-expanded={open} aria-controls="nav" aria-label={open ? 'Cerrar menú' : 'Abrir menú'}
                    onClick={() => setOpen(!open)}>
              <Icon name={open ? 'close' : 'menu'} />
            </button>
          </div>
        </div>
      </header>
      {open && <div className="nav-scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
      <main id="main"><Outlet /></main>
      <footer className="footer">
        <div className="container">
          <div className="footer-grid">
            <div className="footer-brand">
              <Link to="/" className="brand" aria-label="Inicio">
                <BrandMark size={28} />
                <span className="brand-name">Marcador Probable</span>
              </Link>
              <p className="small muted">
                Proyecto de portfolio de Machine Learning: un modelo de Poisson sobre Elo que calcula la probabilidad de
                cada marcador de la Premier League. Probabilidades, no certezas: el modelo no conoce lesiones,
                alineaciones ni noticias.
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
                <li><a href="https://commons.wikimedia.org/" target="_blank" rel="noreferrer">Wikimedia Commons</a> <span className="muted">(fotos de estadios)</span></li>
              </ul>
            </div>
          </div>
          <div className="footer-bottom small muted">
            <span>{meta.data ? <>Datos actualizados al {formatDate(meta.data.last_match_in_data)}</> : ' '}</span>
            <span>No es un servicio de apuestas.</span>
          </div>
        </div>
      </footer>
    </>
  )
}
