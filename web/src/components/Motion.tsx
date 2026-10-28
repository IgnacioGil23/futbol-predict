// Piezas visuales del sistema: band de cada pantalla, aparición al hacer scroll, odómetro, barra 1X2 y anillo del
// favorito. Ninguna cambia qué datos se muestran: solo cómo entran.
import { createElement, useContext, useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { HATCH, split } from '../lib/kits'
import { MotionContext, pctInt, reducedMotion, useSeen } from '../lib/motion'



/** Contenido del band de la pantalla (título, bajada y datos del hero), dentro del bloque del color de la liga. */
export function PageBand({ children, layout = '6', className = '' }: { children: ReactNode; layout?: '5' | '6' | '7' | '8' | 'full'; className?: string }) {
  const { slot } = useContext(MotionContext)
  if (!slot) return null
  return createPortal(<div className={`container hero hero-${layout} ${className}`}>{children}</div>, slot)
}

/** Título de pantalla con reveal por máscara, una línea por elemento. */
export function Title({ lines, id }: { lines: ReactNode[]; id?: string }) {
  return (
    <h1 id={id}>
      {lines.map((l, i) => <span key={i} className="m-title"><span style={{ '--d': `${i * 90}ms` } as CSSProperties}>{l}</span></span>)}
    </h1>
  )
}


type RevealProps = { as?: 'section' | 'div' | 'article' | 'aside'; className?: string; children: ReactNode; style?: CSSProperties } & Record<`aria-${string}`, string | undefined> & { id?: string }

/** Sección que aparece al verse; sus barras, contadores y filas esperan hasta entonces. */
export function Reveal({ as = 'section', className = '', children, ...rest }: RevealProps) {
  const [ref, seen] = useSeen<HTMLElement>()
  return createElement(as, { ref, className: `reveal ${seen ? 'seen' : ''} ${className}`, ...rest }, children)
}

/**
 * Odómetro: cada cifra es una columna 0-9 que se traslada. Arranca en 0 al verse y, cuando el valor cambia, rueda
 * desde el anterior. Los lectores de pantalla leen el valor entero.
 */
export function Odo({ value, base = 0, now = false }: { value: string | number; base?: number; now?: boolean }) {
  const text = String(value)
  const [ref, inView] = useSeen<HTMLSpanElement>()
  const seen = now || inView   // en el hero arranca con la entrada, sin esperar al scroll
  const [on, setOn] = useState(reducedMotion)
  useEffect(() => {
    if (!seen || on) return
    const r = requestAnimationFrame(() => requestAnimationFrame(() => setOn(true)))
    return () => cancelAnimationFrame(r)
  }, [seen, on])
  const chars = [...text]
  return (
    <span ref={ref} className="odo-v">
      <span className="sr-only">{text}</span>
      <span className="odo" aria-hidden="true">
        {chars.map((ch, i) => {
          const key = chars.length - i   // cifras alineadas desde la derecha: 9 → 10 rueda las unidades
          if (!/[0-9]/.test(ch)) return <span key={`c${key}`}>{ch}</span>
          return (
            <span key={key} className="odo-w">
              <span className="odo-c" style={{ transform: `translateY(${on ? -Number(ch) * 10 : 0}%)`, transitionDelay: `${base + i * 70}ms` }}>
                {DIGITS.map((d) => <span key={d}>{d}</span>)}
              </span>
            </span>
          )
        })}
      </span>
    </span>
  )
}
const DIGITS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]


interface SplitBarProps {
  probs: [number, number, number]
  colors: [string, string]        // local y visitante; el empate va rayado
  height: number
  font?: number
  base?: number
  label: string
  odometer?: boolean
}

/** Barra 1X2: tramos del color de cada club y empate rayado, con el número adentro. */
export function SplitBar({ probs, colors, height, font = 13, base = 0, label, odometer = true }: SplitBarProps) {
  const values = probs.map((p) => p * 100)
  const segs = split(values, [colors[0], HATCH, colors[1]], base)
  return (
    <span className="bar3" style={{ height }} role="img" aria-label={label} key={values.map((v) => v.toFixed(1)).join('-')}>
      {segs.map((s, i) => (
        <span key={`s${i}`} className="s" style={{
          left: `calc(${s.left}% + 1px)`, width: `calc(${s.width}% - 2px)`, background: s.bg, boxShadow: s.ring,
          '--from': s.from, '--d': `${s.delay}ms`,
        } as CSSProperties} />
      ))}
      {segs.map((s, i) => (
        <span key={`l${i}`} className="lab" aria-hidden="true" style={{
          left: `${s.left}%`, width: `${s.width}%`, color: s.fg, fontSize: font, '--d': `${s.delay}ms`,
        } as CSSProperties}>
          {odometer ? <Odo value={pctInt(probs[i])} base={s.delay + 200} /> : pctInt(probs[i])}
        </span>
      ))}
    </span>
  )
}

const RING_R = 66
const RING_C = 2 * Math.PI * RING_R

/** Anillo del favorito: el trazo se dibuja hasta su probabilidad (stroke-dashoffset, 1000 ms). */
export function FavRing({ p, size = 156, children }: { p: number; size?: number; children: ReactNode }) {
  const [on, setOn] = useState(reducedMotion)
  useEffect(() => {
    if (on) return
    const r = requestAnimationFrame(() => requestAnimationFrame(() => setOn(true)))
    return () => cancelAnimationFrame(r)
  }, [on])
  return (
    <div className="fav-ring rise" style={{ width: size, height: size, '--d': '420ms' } as CSSProperties}>
      <svg width={size} height={size} viewBox="0 0 156 156" aria-hidden="true">
        <circle cx="78" cy="78" r={RING_R} fill="none" stroke="var(--rule)" strokeWidth="6" />
        <circle cx="78" cy="78" r={RING_R} fill="none" stroke="var(--acc)" strokeWidth="6" strokeLinecap="round"
                strokeDasharray={RING_C.toFixed(2)} className="fav-arc"
                style={{ strokeDashoffset: (on ? RING_C * (1 - p) : RING_C).toFixed(1) }} />
      </svg>
      {children}
    </div>
  )
}
