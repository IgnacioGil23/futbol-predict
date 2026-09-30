import { useLayoutEffect, useRef, useState } from 'react'

const clamp = (w: number) => Math.max(240, Math.floor(w))

/**
 * Ancho del contenedor, para que los SVG se adapten sin scroll horizontal.
 * Se mide de forma sincrónica antes del primer pintado (así nunca se dibuja con
 * un ancho inventado) y después se sigue con ResizeObserver.
 */
export function useWidth<T extends HTMLElement>(fallback = 600) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(fallback)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measured = el.getBoundingClientRect().width
    if (measured > 0) setWidth(clamp(measured))
    const ro = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(clamp(entry.contentRect.width))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}
