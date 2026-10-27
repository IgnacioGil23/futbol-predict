import { HashRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Icon } from './components/Icon'
import { Layout } from './components/Layout'
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
    <div className="container section not-found">
      <div className="not-found-code" aria-hidden="true">404</div>
      <span className="eyebrow">Bandera levantada</span>
      <h1>Fuera de juego</h1>
      <p className="lede">Esta página no existe (o se adelantó a la última línea).</p>
      <Link className="btn btn-primary" to="/">Volver al inicio <span className="arrow"><Icon name="arrow" size={16} /></span></Link>
    </div>
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
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="partidos" element={<Upcoming />} />
          <Route path="partidos/previa" element={<Preview />} />
          <Route path="proximos" element={<RedirectTo to="/partidos" />} />
          <Route path="previa" element={<RedirectTo to="/partidos/previa" />} />
          <Route path="temporada" element={<Season />} />
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
