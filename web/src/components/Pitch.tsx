/** Líneas de una cancha reglamentaria (105 × 68 m) vistas desde arriba; el CSS le da perspectiva. */
export function Pitch({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="-2 -2 109 72" preserveAspectRatio="xMidYMid slice" aria-hidden="true"
         fill="none" stroke="currentColor" strokeWidth="0.35" vectorEffect="non-scaling-stroke">
      <rect x="0" y="0" width="105" height="68" />
      <path d="M52.5 0v68" />
      <circle cx="52.5" cy="34" r="9.15" />
      <circle cx="52.5" cy="34" r="0.5" fill="currentColor" />
      <path d="M0 13.84h16.5v40.32H0M0 24.84h5.5v18.32H0" />
      <path d="M105 13.84h-16.5v40.32H105M105 24.84h-5.5v18.32H105" />
      <circle cx="11" cy="34" r="0.5" fill="currentColor" />
      <circle cx="94" cy="34" r="0.5" fill="currentColor" />
      <path d="M16.5 26.7a9.15 9.15 0 0 1 0 14.6M88.5 26.7a9.15 9.15 0 0 0 0 14.6" />
    </svg>
  )
}
