import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Primero los estilos globales, para que los de cada página (importados por la app) los refinen.
import './styles/global.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
