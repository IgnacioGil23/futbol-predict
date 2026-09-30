import { useEffect, useRef, useState } from 'react'

interface Props { value: number; format: (x: number) => string; duration?: number; className?: string }

const reduced = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * Número que cuenta hasta su valor la primera vez que entra en pantalla. El valor final
 * siempre está en el DOM para lectores de pantalla (el conteo es solo visual).
 */
export function CountUp({ value, format, duration = 1100, className }: Props) {
  const ref = useRef<HTMLSpanElement>(null)
  const [still] = useState(reduced)
  const [shown, setShown] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el || still) return
    let raf = 0
    const io = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return
      io.disconnect()
      const t0 = performance.now()
      const tick = (t: number) => {
        const k = Math.min(1, (t - t0) / duration)
        setShown(value * (1 - Math.pow(2, -10 * k)) / (1 - Math.pow(2, -10)))   // easeOutExpo normalizado
        if (k < 1) raf = requestAnimationFrame(tick)
        else setShown(value)
      }
      raf = requestAnimationFrame(tick)
    }, { threshold: 0.4 })
    io.observe(el)
    return () => { io.disconnect(); cancelAnimationFrame(raf) }
  }, [value, duration, still])
  return (
    <span ref={ref} className={className}>
      <span aria-hidden="true">{format(still ? value : shown)}</span>
      <span className="sr-only">{format(value)}</span>
    </span>
  )
}
