// Estado compartido del movimiento: movimiento reducido, contexto del band y la cortina, y aparición al hacer scroll.
import { createContext, useContext, useEffect, useRef, useState } from 'react'

export const reducedMotion = () =>
  typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

interface MotionState {
  /** Hueco del band (debajo del encabezado) donde cada pantalla pone su título. */
  slot: HTMLElement | null
  /** Cortina del color de destino: aplica el cambio a los 360 ms (al instante con movimiento reducido). */
  curtain: (color: string, apply: () => void) => void
}
export const MotionContext = createContext<MotionState>({ slot: null, curtain: (_c, apply) => apply() })
export const useCurtain = () => useContext(MotionContext).curtain

/** Marca `seen` cuando el 16% del elemento entra en pantalla. */
export function useSeen<T extends Element>() {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(() => typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    const el = ref.current
    if (!el || seen) return
    // 16% visible; en secciones más altas que la pantalla, cuando ocupan el 16% de la vista.
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && (e.intersectionRatio >= 0.16 || e.intersectionRect.height >= window.innerHeight * 0.16)) { setSeen(true); io.disconnect() }
    }, { threshold: [0, 0.02, 0.05, 0.1, 0.16] })
    io.observe(el)
    return () => io.disconnect()
  }, [seen])
  return [ref, seen] as const
}

/** Porcentaje entero, como `pct()` pero sin el signo (para dentro de la barra). */
export const pctInt = (p: number) => Math.round(p * 100)
