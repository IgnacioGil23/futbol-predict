import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { formatDate, useData } from '../lib/data'
import type { MetaFile } from '../lib/types'
import './layout.css'

const LINKS = [
  { to: '/previa', label: 'Previa' },
  { to: '/equipos', label: 'Equipos' },
  { to: '/revision', label: 'Revisión' },
  { to: '/ventaja-local', label: 'Ventaja de local' },
  { to: '/metodologia', label: 'Cómo funciona' },
]

type Theme = 'light' | 'dark' | null

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    try { return (localStorage.getItem('theme') as Theme) ?? null } catch { return null }
  })
  useEffect(() => {
    const root = document.documentElement
    if (theme) root.setAttribute('data-theme', theme)
    else root.removeAttribute('data-theme')
    try { if (theme) localStorage.setItem('theme', theme); else localStorage.removeItem('theme') } catch { /* sin storage */ }
  }, [theme])
  const isDark = theme === 'dark' || (theme === null && window.matchMedia('(prefers-color-scheme: dark)').matches)
  return { isDark, toggle: () => setTheme(isDark ? 'light' : 'dark') }
}

export function Layout() {
  const { isDark, toggle } = useTheme()
  const meta = useData<MetaFile>('meta.json')
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])

  return (
    <>
      <a href="#main" className="skip">Saltar al contenido</a>
      <header className="topbar">
        <div className="container topbar-inner">
          <NavLink to="/" className="brand" aria-label="Inicio">
            <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
              <rect x="1" y="1" width="24" height="24" rx="6" fill="var(--accent)" />
              <path d="M7 18V8h4.5a3.2 3.2 0 0 1 0 6.4H7" fill="none" stroke="var(--accent-ink)" strokeWidth="2.2" strokeLinecap="round" />
              <circle cx="18" cy="16.5" r="2.2" fill="var(--accent-ink)" />
            </svg>
            <span>Marcador Probable<span className="brand-dim"> · Premier</span></span>
          </NavLink>
          <button className="menu-btn" aria-expanded={open} aria-controls="nav" onClick={() => setOpen(!open)}>
            {open ? 'Cerrar' : 'Menú'}
          </button>
          <nav id="nav" className={`nav ${open ? 'open' : ''}`} aria-label="Principal">
            {LINKS.map((l) => (
              <NavLink key={l.to} to={l.to} onClick={() => setOpen(false)} className={({ isActive }) => (isActive ? 'active' : undefined)}>{l.label}</NavLink>
            ))}
            <button className="theme-btn" onClick={toggle} aria-label={isDark ? 'Usar modo claro' : 'Usar modo oscuro'} title="Cambiar tema">
              {isDark ? '☀' : '☾'}
            </button>
          </nav>
        </div>
      </header>
      <main id="main"><Outlet /></main>
      <footer className="footer">
        <div className="container footer-inner small">
          <div>
            <strong>Marcador Probable</strong> — proyecto de portfolio de Machine Learning. Probabilidades, no certezas:
            el modelo no conoce lesiones, alineaciones ni noticias.
          </div>
          <div className="muted">
            Datos: <a href="https://www.football-data.co.uk/" target="_blank" rel="noreferrer">Football-Data.co.uk</a>
            {meta.data && <> · actualizados al {formatDate(meta.data.last_match_in_data)}</>}
            {' '}· No es un servicio de apuestas.
          </div>
        </div>
      </footer>
    </>
  )
}
