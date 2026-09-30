import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { formatDate, REPO, useData } from '../lib/data'
import type { MetaFile } from '../lib/types'
import { BrandMark, Icon } from './Icon'
import './layout.css'

const LINKS = [
  { to: '/proximos', label: 'Próximos' },
  { to: '/previa', label: 'Previa' },
  { to: '/temporada', label: 'Temporada' },
  { to: '/equipos', label: 'Equipos' },
  { to: '/revision', label: 'Revisión' },
  { to: '/monitoreo', label: 'Monitoreo' },
  { to: '/metodologia', label: 'Cómo funciona' },
]

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
      const active = nav.querySelector<HTMLElement>('a.active')
      setBox(active ? { left: active.offsetLeft, width: active.offsetWidth } : null)
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

  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
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
            {LINKS.map((l) => (
              <NavLink key={l.to} to={l.to} onClick={() => setOpen(false)}
                       className={({ isActive }) => (isActive ? 'active' : undefined)}>{l.label}</NavLink>
            ))}
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
                {LINKS.map((l) => <li key={l.to}><Link to={l.to}>{l.label}</Link></li>)}
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
            <span>{meta.data ? <>Datos actualizados al {formatDate(meta.data.last_match_in_data)} · modelo {meta.data.model_version}</> : ' '}</span>
            <span>No es un servicio de apuestas.</span>
          </div>
        </div>
      </footer>
    </>
  )
}
