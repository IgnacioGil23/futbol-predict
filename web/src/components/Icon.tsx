// Íconos de trazo (24×24, heredan el color del texto). Decorativos: aria-hidden.
const PATHS = {
  sun: 'M12 4V2M12 22v-2M4.93 4.93 3.52 3.52M20.48 20.48l-1.41-1.41M4 12H2M22 12h-2M4.93 19.07l-1.41 1.41M20.48 3.52l-1.41 1.41M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z',
  moon: 'M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7Z',
  menu: 'M4 7h16M4 12h16M4 17h16',
  close: 'M6 6l12 12M18 6 6 18',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM20 20l-4-4',
  pin: 'M12 21s-7-6.1-7-11.5a7 7 0 1 1 14 0C19 14.9 12 21 12 21ZM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM12 16v-4.5M12 8h.01',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  back: 'M19 12H5M11 18l-6-6 6-6',
  swap: 'M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7',
  github: 'M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  ball: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM12 7l4.2 3.1-1.6 4.9H9.4l-1.6-4.9L12 7ZM12 2v5M16.2 10.1l4.9-1.6M14.6 15l3 4.1M9.4 15l-3 4.1M7.8 10.1 2.9 8.5',
  camera: 'M4 8h3l2-3h6l2 3h3v11H4V8ZM12 16.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z',
} as const

export type IconName = keyof typeof PATHS

export function Icon({ name, size = 18, stroke = 1.8 }: { name: IconName; size?: number; stroke?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke}
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  )
}

/** Marca: un "%" dentro de una pelota, sobre el degradado del acento. */
export function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="bm-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2fe691" />
          <stop offset="1" stopColor="#c8ff5a" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="9" fill="url(#bm-g)" />
      <circle cx="16" cy="16" r="9.5" fill="none" stroke="#02140a" strokeWidth="2" />
      <circle cx="12.4" cy="12.4" r="2.1" fill="#02140a" />
      <circle cx="19.6" cy="19.6" r="2.1" fill="#02140a" />
      <path d="M20.2 11.8 11.8 20.2" stroke="#02140a" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}
