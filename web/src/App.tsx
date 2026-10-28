import type { CSSProperties } from 'react'
import { HashRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Icon } from './components/Icon'
import { PageBand, Title } from './components/Motion'
import { Layout } from './components/Layout'
import { LeagueProvider } from './components/LeagueProvider'
import { Estadisticas } from './pages/Estadisticas'
import { Home } from './pages/Home'
import { Method } from './pages/Method'
import { Monitoring } from './pages/Monitoring'
import { Preview } from './pages/Preview'
import { Review } from './pages/Review'
import { Season } from './pages/Season'
import { TeamDetail, Teams } from './pages/Teams'
import { Upcoming } from './pages/Upcoming'

function NotFound() {
  return (
    <PageBand layout="8">
      <div className="hero-main">
        <Title lines={['Fuera', 'de juego']} />
        <p className="lede rise" style={{ '--d': '260ms' } as CSSProperties}>Esta página no existe (o se adelantó a la última línea).</p>
        <span className="not-found-code data-label rise" style={{ '--d': '300ms' } as CSSProperties}>404 · Bandera levantada</span>
        <div className="rise" style={{ '--d': '340ms' } as CSSProperties}>
          <Link className="btn btn-primary" to="/">Volver al inicio <span className="arrow"><Icon name="arrow" size={16} /></span></Link>
        </div>
      </div>
    </PageBand>
  )
}

function RedirectTo({ to }: { to: string }) {
  const location = useLocation()
  return <Navigate replace to={{ pathname: to, search: location.search }} />
}

// HashRouter: GitHub Pages sirve archivos estáticos y no reescribe rutas.
export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<LeagueProvider><Layout /></LeagueProvider>}>
          <Route index element={<Home />} />
          <Route path="partidos" element={<Upcoming />} />
          <Route path="partidos/previa" element={<Preview />} />
          <Route path="proximos" element={<RedirectTo to="/partidos" />} />
          <Route path="previa" element={<RedirectTo to="/partidos/previa" />} />
          <Route path="temporada" element={<Season />} />
          <Route path="estadisticas" element={<Estadisticas />} />
          <Route path="equipos" element={<Teams />} />
          <Route path="equipos/:slug" element={<TeamDetail />} />
          <Route path="revision" element={<Review />} />
          <Route path="metodologia" element={<Method />} />
          <Route path="monitoreo" element={<Monitoring />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}
