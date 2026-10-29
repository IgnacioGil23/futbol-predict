// Presentación de los clubes: cómo se pinta el medallón y qué color usa cada lado de una barra.
// Los colores salen de teams.json (`colors`); acá solo vive el diseño de la camiseta, que es una tabla visual.
import type { TeamColors } from './types'

export type KitPattern = 'stripes' | 'sleeves' | 'halves' | 'sash' | 'band' | 'center' | 'diag' | 'solid'

/** Diseño de la camiseta por nombre del club (el `name` de teams.json). Los que faltan: lisa con cuello. */
export const K: Record<string, KitPattern> = {
  'Chelsea': 'solid', 'Manchester United': 'solid', 'AFC Bournemouth': 'stripes', 'Leeds United': 'solid', 'Brentford': 'stripes',
  'Nottingham Forest': 'solid', 'Coventry City': 'solid', 'Sunderland': 'stripes', 'Hull City': 'stripes', 'Ipswich Town': 'solid',
  'Manchester City': 'solid', 'Brighton & Hove Albion': 'stripes', 'Tottenham Hotspur': 'solid', 'Crystal Palace': 'stripes',
  'Aston Villa': 'sleeves', 'Fulham': 'solid', 'Liverpool': 'solid', 'Arsenal': 'sleeves', 'Newcastle United': 'stripes', 'Everton': 'solid',
  'West Ham United': 'sleeves', 'Wolverhampton Wanderers': 'solid', 'Burnley': 'sleeves',
  'Athletic Club': 'stripes', 'Real Sociedad': 'stripes', 'Barcelona': 'stripes', 'Alavés': 'stripes', 'Real Betis': 'stripes',
  'Málaga': 'stripes', 'Elche': 'band', 'Valencia': 'solid', 'Getafe': 'solid', 'Sevilla': 'solid', 'Deportivo La Coruña': 'stripes',
  'Osasuna': 'solid', 'Levante': 'stripes', 'Atlético de Madrid': 'stripes', 'Racing de Santander': 'solid', 'Real Madrid': 'solid',
  'Rayo Vallecano': 'sash', 'Celta de Vigo': 'solid', 'Villarreal': 'solid', 'Espanyol': 'stripes',
  'Milan': 'stripes', 'Bologna': 'stripes', 'Parma': 'solid', 'Udinese': 'stripes', 'Venezia': 'solid', 'Inter de Milán': 'stripes',
  'Genoa': 'halves', 'Juventus': 'stripes', 'Monza': 'solid', 'Napoli': 'solid', 'Frosinone': 'solid', 'Lecce': 'stripes',
  'Fiorentina': 'solid', 'Atalanta': 'stripes',
  'Elversberg': 'solid', 'Mainz 05': 'solid', 'Augsburgo': 'solid', 'Friburgo': 'solid', 'Bayer Leverkusen': 'solid', 'Stuttgart': 'band',
  'Borussia Mönchengladbach': 'solid', 'Paderborn': 'solid', 'Schalke 04': 'solid', 'RB Leipzig': 'solid', 'Werder Bremen': 'solid',
  'Hoffenheim': 'solid', 'Bayern Múnich': 'solid', 'Borussia Dortmund': 'solid', 'Union Berlín': 'solid', 'Colonia': 'solid',
  'Eintracht Frankfurt': 'solid', 'Hamburgo': 'solid',
  'Le Havre': 'halves', 'Paris Saint-Germain': 'center', 'Lille': 'solid', 'Lens': 'sleeves', 'Niza': 'stripes', 'Rennes': 'solid',
  'Lorient': 'solid', 'Brest': 'solid', 'Olympique de Lyon': 'solid', 'Angers': 'stripes', 'Troyes': 'solid', 'Le Mans': 'solid',
  'Estrasburgo': 'solid', 'Auxerre': 'solid', 'Paris FC': 'solid', 'Mónaco': 'diag', 'Olympique de Marsella': 'solid', 'Toulouse': 'solid',
}

export const HATCH = 'repeating-linear-gradient(135deg, var(--hatch) 0 1px, transparent 1px 5px)'

// Campo de cada liga (el color de la cortina al cambiar de liga). Las clases lg-* repiten estos valores en el CSS.
export const LEAGUE_CLASS: Record<string, string> = {
  premier: 'lg-premier', laliga: 'lg-laliga', 'serie-a': 'lg-seriea', bundesliga: 'lg-bundesliga', 'ligue-1': 'lg-ligue1',
}
export const LEAGUE_FIELD: Record<string, string> = {
  premier: '#4A0E6E', laliga: '#C42B21', 'serie-a': '#1A35D6', bundesliga: '#C8102E', 'ligue-1': '#0B47D6',
}

const isHex = (c: string) => /^#[0-9a-f]{6}$/i.test(c)
const rgbOf = (hex: string) => { const n = parseInt(hex.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255] }
export const lum = (hex: string) => rgbOf(hex)
  .map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) })
  .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0)
export const dist = (a: string, b: string) => { const p = rgbOf(a), q = rgbOf(b); return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) }
/** Texto legible sobre un color de club. */
export const onColor = (hex: string) => (isHex(hex) && lum(hex) > 0.3 ? '#1A1814' : '#FFFFFF')
/** Filete para camisetas casi blancas, que si no se pierden en el fondo. */
export const ring = (hex: string) => (isHex(hex) && lum(hex) > 0.75 ? 'inset 0 0 0 1px var(--ink)' : 'none')

export interface Kit { primary: string; secondary: string; pattern: KitPattern | null }

/** Camiseta de un club: colores de teams.json (gris neutro si no tiene) y diseño de la tabla `K`. */
export function kitOf(name: string, colors: TeamColors | null | undefined, fallback = '#888888'): Kit {
  const primary = colors?.primary && isHex(colors.primary) ? colors.primary : fallback
  const secondary = colors?.secondary && isHex(colors.secondary) ? colors.secondary : '#FFFFFF'
  return { primary, secondary, pattern: K[name] ?? null }
}

export function kitBackground({ primary: p, secondary: s, pattern }: Kit) {
  switch (pattern) {
    case 'stripes': return `repeating-linear-gradient(90deg, ${p} 0 3px, ${s} 3px 6px)`
    case 'sleeves': return `linear-gradient(90deg, ${s} 0 24%, ${p} 24% 76%, ${s} 76%)`
    case 'halves': return `linear-gradient(90deg, ${p} 0 50%, ${s} 50%)`
    case 'sash': return `linear-gradient(135deg, ${p} 0 38%, ${s} 38% 58%, ${p} 58%)`
    case 'band': return `linear-gradient(180deg, ${p} 0 40%, ${s} 40% 58%, ${p} 58%)`
    case 'center': return `linear-gradient(90deg, ${p} 0 38%, ${s} 38% 62%, ${p} 62%)`
    case 'diag': return `linear-gradient(135deg, ${p} 0 50%, ${s} 50%)`
    default: return `linear-gradient(180deg, ${s} 0 14%, ${p} 14%)`   // lisa con cuello
  }
}

/** Colores de los dos lados de un partido: si las camisetas se parecen, el visitante usa su segundo color. */
export function sideColors(home: Kit, away: Kit) {
  const hc = home.primary
  let ac = away.primary
  if (dist(hc, ac) < 110) ac = dist(hc, away.secondary) >= 110 ? away.secondary : '#8A8275'
  return { hc, ac }
}

/** Un tramo de la barra 1X2: arranca como un tercio y se acomoda a su valor (solo transform). */
export interface Segment { left: number; width: number; bg: string; fg: string; ring: string; from: string; delay: number }

export function split(values: number[], colors: string[], base = 0): Segment[] {
  const eq = 100 / values.length
  let left = 0
  return values.map((w, i) => {
    const hex = colors[i].startsWith('#')
    const seg = {
      left, width: w, bg: colors[i],
      fg: hex ? onColor(colors[i]) : 'var(--ink)',
      ring: hex ? ring(colors[i]) : 'inset 0 0 0 1px var(--hatch)',
      from: `translateX(${(i * eq - left).toFixed(2)}cqw) scaleX(${(eq / Math.max(w, 1)).toFixed(3)})`,
      delay: base + i * 70,
    }
    left += w
    return seg
  })
}
