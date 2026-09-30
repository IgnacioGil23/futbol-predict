import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { num, pct, pct1 } from '../lib/data'
import type { SeasonTeam, TeamIndexItem, TeamState } from '../lib/types'
import { Icon } from './Icon'
import { TeamBadge } from './TeamBadge'
import './team-preview.css'

export interface TeamSeasonSummary {
  team: TeamIndexItem
  state: TeamState
  eloRank: number
  teamsInLeague: number
  sim: SeasonTeam | null
  nSims: number | null
  season: string
}

const signed = (x: number) => `${x > 0 ? '+' : ''}${x}`
const prob = (p: number) => (p === 0 ? '—' : p < 0.001 ? '<0,1%' : p < 0.1 ? pct1(p) : pct(p))
const OUTCOME = { G: 'ganó', E: 'empató', P: 'perdió' } as const

/** Foto del estadio que aparece suavemente cuando termina de cargar. */
function StadiumImage({ src }: { src: string }) {
  const [loaded, setLoaded] = useState(false)
  return <img className={`tp-img ${loaded ? 'loaded' : ''}`} src={src} alt="" decoding="async" onLoad={() => setLoaded(true)} />
}

/** Resumen de la temporada de un club sobre la foto de su estadio. */
export function TeamPreviewCard({ s, onClose }: { s: TeamSeasonSummary; onClose?: () => void }) {
  const { team, state, sim } = s
  const t = state.table
  const stadium = team.stadium
  return (
    <div className="tp-card">
      <div className="tp-media">
        {stadium ? <StadiumImage src={stadium.image} /> : null}
        <div className="tp-shade" />
        {t && t.played > 0 && (
          <div className="tp-pos" aria-label={`${t.position}º en la tabla`}>
            <span className="tabular">{t.position}</span><small>º</small>
          </div>
        )}
        {onClose && (
          <button className="icon-btn tp-close" onClick={onClose} aria-label="Cerrar"><Icon name="close" size={16} /></button>
        )}
        <div className="tp-id">
          <TeamBadge badge={team.badge} short={team.short} name={team.name} size={54} decorative />
          <div>
            <strong>{team.name}</strong>
            {stadium && <span><Icon name="pin" size={13} /> {stadium.name}</span>}
          </div>
        </div>
      </div>

      <div className="tp-body">
        <div className="tp-label">Temporada {s.season}{t && t.played < 10 && t.played > 0 ? ` · ${t.played} partidos jugados` : ''}</div>
        {t && t.played > 0 ? (
          <>
            <div className="tp-stats">
              <div><strong className="tabular">{t.points}</strong><span>Puntos</span></div>
              <div><strong className="tabular">{t.won}-{t.drawn}-{t.lost}</strong><span>G-E-P</span></div>
              <div><strong className="tabular">{t.gf}:{t.ga}</strong><span>Goles</span></div>
              <div><strong className="tabular">{signed(t.gd)}</strong><span>Dif.</span></div>
            </div>
          </>
        ) : <p className="small muted">Todavía no jugó partidos de liga esta temporada.</p>}

        <div className="tp-line">
          <span>Elo</span>
          <span className="tabular"><strong>{num(state.elo, 0)}</strong> <span className="muted">· {s.eloRank}º de {s.teamsInLeague}</span></span>
        </div>
        {state.form.length > 0 && (
          <div className="tp-line">
            <span>Forma</span>
            <span className="tp-form" aria-label="Últimos partidos, del más viejo al más reciente">
              {[...state.form].reverse().map((m) => (
                <span key={m.date} className={`chip chip-sm chip-${m.outcome}`}
                      title={`${OUTCOME[m.outcome]} ${m.goals_for}-${m.goals_against} ${m.home ? 'vs' : 'en'} ${m.opponent}`}>
                  {m.outcome}
                </span>
              ))}
            </span>
          </div>
        )}

        {sim && (
          <div className="tp-proj">
            <div className="tp-proj-head">
              <span>Proyección{s.nSims ? ` · ${num(s.nSims, 0)} simulaciones` : ''}</span>
              <span className="tabular"><strong>{num(sim.expected_points, 1)}</strong> pts esperados</span>
            </div>
            {[
              { k: 'Campeón', p: sim.p_champion, c: 'var(--accent)' },
              { k: 'Top 4', p: sim.p_top4, c: 'var(--home)' },
              { k: 'Descenso', p: sim.p_relegation, c: 'var(--away)' },
            ].map((r) => (
              <div key={r.k} className="tp-bar">
                <span>{r.k}</span>
                <span className="tp-bar-track"><span style={{ width: `${Math.max(r.p > 0 ? 2 : 0, r.p * 100)}%`, background: r.c }} /></span>
                <span className="tabular">{prob(r.p)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {stadium && (
        <div className="tp-credit">
          <Icon name="camera" size={12} />
          <span>
            <a href={stadium.credit.source} target="_blank" rel="noreferrer">{stadium.credit.author}</a>
            {' · '}
            <a href={stadium.credit.license_url} target="_blank" rel="noreferrer">{stadium.credit.license}</a>
            {' · Wikimedia Commons'}
          </span>
        </div>
      )}
    </div>
  )
}

const WIDTH = 360
const GAP = 14
const MARGIN = 12

/**
 * Vista previa flotante junto a la tarjeta que la abrió (escritorio: hover o foco) o como
 * ventana centrada (pantallas táctiles, con el botón de información).
 */
export function TeamPreviewPopover({ s, anchor, modal, onClose, onPointerEnter, onPointerLeave }: {
  s: TeamSeasonSummary; anchor: DOMRect | null; modal: boolean; onClose: () => void
  onPointerEnter?: () => void; onPointerLeave?: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number; side: 'left' | 'right' } | null>(null)

  useLayoutEffect(() => {
    if (modal || !anchor || !ref.current) return
    const h = ref.current.offsetHeight
    const vw = document.documentElement.clientWidth
    const vh = window.innerHeight
    const right = anchor.right + GAP + WIDTH <= vw - MARGIN
    const left = right ? anchor.right + GAP : Math.max(MARGIN, anchor.left - GAP - WIDTH)
    const top = Math.min(Math.max(anchor.top + anchor.height / 2 - h / 2, 76), vh - h - MARGIN)
    setPos({ left, top: Math.max(MARGIN, top), side: right ? 'right' : 'left' })
  }, [anchor, modal, s.team.slug])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    if (!modal) {
      window.addEventListener('scroll', onClose, { passive: true })
      window.addEventListener('resize', onClose)
    }
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', onClose)
      window.removeEventListener('resize', onClose)
    }
  }, [modal, onClose])

  if (modal) {
    return createPortal(
      <div className="tp-modal" onClick={onClose}>
        <div className="tp-pop tp-pop-modal" role="dialog" aria-modal="true" aria-label={`Resumen de ${s.team.name}`}
             onClick={(e) => e.stopPropagation()}>
          <TeamPreviewCard s={s} onClose={onClose} />
        </div>
      </div>,
      document.body,
    )
  }
  const style: CSSProperties = pos
    ? { left: pos.left, top: pos.top, width: WIDTH, transformOrigin: pos.side === 'right' ? 'left center' : 'right center' }
    : { left: -9999, top: 0, width: WIDTH, visibility: 'hidden' }
  return createPortal(
    <div ref={ref} className={`tp-pop ${pos ? 'shown' : ''}`} style={style} role="tooltip" id={`tp-${s.team.slug}`}
         onPointerEnter={onPointerEnter} onPointerLeave={onPointerLeave}>
      <TeamPreviewCard s={s} />
    </div>,
    document.body,
  )
}
