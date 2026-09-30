import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { MatchAnalysis, type MatchView } from '../components/MatchAnalysis'
import { API_URL, fetchPrediction, formatDate, loadData, twoSeasonsBefore, useData } from '../lib/data'
import { forecast } from '../lib/model'
import type { H2H, MetaFile, ModelFile, StateFile, TeamFile, TeamIndexItem, UpcomingFile } from '../lib/types'

interface View extends MatchView {
  date: string
  mode: 'hoy' | 'historico'
  warnings: string[]
}

export function Preview() {
  const [params, setParams] = useSearchParams()
  const meta = useData<MetaFile>('meta.json')
  const state = useData<StateFile>('state.json')
  const index = useData<TeamIndexItem[]>('teams.json')
  const upcoming = useData<UpcomingFile>('upcoming.json')

  const today = meta.data?.as_of ?? ''
  const date = params.get('date') || today
  const isToday = !!today && date >= today
  const current = state.data?.teams ?? []
  const byElo = [...current].sort((a, b) => b.elo - a.elo)
  const firstUpcoming = upcoming.data?.matchdays[0]?.matches[0]
  const home = params.get('home') || firstUpcoming?.home_team || byElo[0]?.team || ''
  const away = params.get('away') || firstUpcoming?.away_team || byElo[1]?.team || ''
  const names = useMemo(() => new Map((index.data ?? []).map((t) => [t.team, t.name])), [index.data])
  const nameOf = (t: string) => names.get(t) ?? t
  const slugOf = (t: string) => index.data?.find((x) => x.team === t)?.slug
  const options = isToday
    ? current.map((t) => ({ team: t.team, name: t.name }))
    : (index.data ?? []).map((t) => ({ team: t.team, name: t.name }))

  // Resultado del último cálculo, con la clave que lo produjo: 'cargando' se deriva comparando claves.
  const key = `${home}|${away}|${date}`
  const [result, setResult] = useState<{ key: string; view: View | null; error: string | null } | null>(null)

  useEffect(() => {
    if (!home || !away || !today || !state.data) return
    if (home === away) return
    let alive = true
    const ctrl = new AbortController()
    const k = `${home}|${away}|${date}`
    const run = async (): Promise<View> => {
      if (isToday) {
        const [model, h2hAll, up] = await Promise.all([
          loadData<ModelFile>('model.json'), loadData<Record<string, H2H>>('h2h.json'), loadData<UpcomingFile>('upcoming.json'),
        ])
        const hs = state.data!.teams.find((t) => t.team === home)
        const as = state.data!.teams.find((t) => t.team === away)
        if (!hs || !as) throw new Error('Para la fecha de hoy solo están disponibles los equipos de la Premier de esta temporada.')
        const f = forecast(model.params, hs.elo, as.elo, model.max_goals)
        const [hf, af] = await Promise.all([
          loadData<TeamFile>(`teams/${hs.slug}.json`), loadData<TeamFile>(`teams/${as.slug}.json`),
        ])
        const since = twoSeasonsBefore(today)
        // Si el cruce está en las próximas jornadas, se muestra el mercado (cuando ya hay cuotas publicadas).
        const scheduled = up.matchdays.flatMap((m) => m.matches).find((m) => m.home_team === home && m.away_team === away)
        return {
          date: scheduled?.date ?? today, mode: 'hoy', elo: { home: hs.elo, away: as.elo },
          lam: f.lam, mu: f.mu, probabilities: f.probabilities, grid: f.grid, market: scheduled?.market ?? null,
          form: { home: hs.form, away: as.form }, rest: { home: hs.rest, away: as.rest },
          h2h: h2hAll[`${home}|${away}`] ?? { matches: 0, home_team_wins: 0, draws: 0, away_team_wins: 0, last: [] },
          eloHistory: { home: hf.elo.filter((p) => p.date >= since), away: af.elo.filter((p) => p.date >= since) },
          warnings: [],
        }
      }
      const r = await fetchPrediction(home, away, date, ctrl.signal)
      return {
        date, mode: 'historico', elo: r.elo, lam: r.expected_goals.home, mu: r.expected_goals.away,
        probabilities: r.probabilities, grid: r.score_grid, market: null,
        form: { home: r.context.form_home, away: r.context.form_away }, rest: { home: r.context.rest_home, away: r.context.rest_away },
        h2h: r.context.head_to_head, eloHistory: { home: r.context.elo_history_home, away: r.context.elo_history_away },
        warnings: r.warnings,
      }
    }
    run().then((v) => alive && setResult({ key: k, view: v, error: null }))
      .catch((e: Error) => { if (alive && e.name !== 'AbortError') setResult({ key: k, view: null, error: e.message }) })
    return () => { alive = false; ctrl.abort() }
  }, [home, away, date, isToday, today, state.data])

  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params)
    Object.entries(patch).forEach(([k, v]) => next.set(k, v))
    if (!next.get('home')) next.set('home', home)
    if (!next.get('away')) next.set('away', away)
    setParams(next, { replace: true })
  }

  const sameTeam = !!home && home === away
  const loading = !sameTeam && result?.key !== key
  const view = result?.view ?? null   // mientras carga, se muestra atenuado el cálculo anterior
  const error = result?.key === key ? result.error : null
  const shownError = sameTeam ? 'Elegí dos equipos distintos.' : error
  const homeName = nameOf(home)
  const awayName = nameOf(away)

  return (
    <div className="container section">
      <div className="section-head">
        <span className="eyebrow">Previa de partido</span>
        <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3.2rem)' }}>
          {homeName || '…'} <span className="muted" style={{ fontWeight: 600 }}>vs</span> {awayName || '…'}
        </h1>
        <p className="lede">
          Elegí dos equipos y una fecha. El modelo convierte la diferencia de Elo en goles esperados y, de ahí, en la
          probabilidad de cada marcador. ¿Querés ver la próxima jornada completa? <Link to="/proximos">Próximos partidos →</Link>
        </p>
      </div>

      <div className="card" style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', alignItems: 'end' }}>
        <div className="field">
          <label htmlFor="home">Local</label>
          <select id="home" value={home} onChange={(e) => update({ home: e.target.value })}>
            {options.map((o) => <option key={o.team} value={o.team}>{o.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="away">Visitante</label>
          <select id="away" value={away} onChange={(e) => update({ away: e.target.value })}>
            {options.map((o) => <option key={o.team} value={o.team}>{o.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="date">Fecha</label>
          <input id="date" type="date" value={date} min="2005-08-01" max={today}
                 onChange={(e) => update({ date: e.target.value || today })} />
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn" onClick={() => update({ home: away, away: home })} title="Invertir localía">⇄ Invertir</button>
          {!isToday && <button className="btn" onClick={() => update({ date: today })}>Hoy</button>}
        </div>
      </div>

      {!isToday && !API_URL && (
        <p className="callout" style={{ marginTop: 16 }}>
          Las fechas pasadas se calculan con la API del modelo, que no está configurada en esta versión del sitio. Podés
          ver lo que predijo el modelo para cualquier partido ya jugado en <Link to="/revision">Revisión histórica</Link>.
        </p>
      )}
      {shownError && <p className="callout" style={{ marginTop: 16 }} role="alert"><strong>No se pudo calcular:</strong> {shownError}</p>}
      {loading && !view && (
        <div className="grid grid-main" style={{ marginTop: 16 }}>
          <div className="skeleton" style={{ minHeight: 420 }} />
          <div className="skeleton" style={{ minHeight: 420 }} />
          {!isToday && <p className="small muted">Consultando la API… si el servicio estaba en reposo (escala a cero cuando no hay tráfico), el primer pedido tarda unos segundos más.</p>}
        </div>
      )}

      {view && !sameTeam && (
        <div style={{ opacity: loading ? 0.55 : 1, transition: 'opacity .2s' }}>
          <p className="small muted" style={{ margin: '16px 0 0' }}>
            {view.mode === 'hoy'
              ? `Estado de los equipos al ${formatDate(today)} (último partido en los datos: ${formatDate(meta.data!.last_match_in_data)}).`
              : `Como si el partido se jugara el ${formatDate(view.date)}: solo usa partidos anteriores a esa fecha.`}
          </p>
          {view.warnings.map((w) => <p key={w} className="callout" style={{ marginTop: 8 }}>{w}</p>)}
          <MatchAnalysis view={view} home={home} away={away} homeName={homeName} awayName={awayName}
                         homeSlug={slugOf(home)} awaySlug={slugOf(away)} />
        </div>
      )}
    </div>
  )
}
