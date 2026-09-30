import { HashRouter, Link, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Home } from './pages/Home'
import { HomeAdvantagePage } from './pages/HomeAdvantage'
import { Method } from './pages/Method'
import { Preview } from './pages/Preview'
import { Review } from './pages/Review'
import { TeamDetail, Teams } from './pages/Teams'
import { Upcoming } from './pages/Upcoming'

function NotFound() {
  return (
    <div className="container section">
      <h1>Fuera de juego</h1>
      <p className="lede" style={{ margin: '12px 0 20px' }}>Esta página no existe.</p>
      <Link className="btn btn-primary" to="/">Volver al inicio</Link>
    </div>
  )
}

// HashRouter: GitHub Pages sirve archivos estáticos y no reescribe rutas.
export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="proximos" element={<Upcoming />} />
          <Route path="previa" element={<Preview />} />
          <Route path="equipos" element={<Teams />} />
          <Route path="equipos/:slug" element={<TeamDetail />} />
          <Route path="revision" element={<Review />} />
          <Route path="ventaja-local" element={<HomeAdvantagePage />} />
          <Route path="metodologia" element={<Method />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}
