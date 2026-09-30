import { HomeAdvantageChart } from '../components/HomeAdvantageChart'
import { formatDate, num, pct, useData } from '../lib/data'
import type { HomeAdvantageFile } from '../lib/types'

const ERA_COLORS = ['var(--era-1)', 'var(--era-2)', 'var(--era-3)']

export function HomeAdvantagePage() {
  const ha = useData<HomeAdvantageFile>('home_advantage.json')
  const d = ha.data
  return (
    <div className="container section">
      <div className="section-head">
        <span className="eyebrow">Dato curioso con rigor</span>
        <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3.2rem)' }}>¿Cuánto vale jugar de local?</h1>
        <p className="lede">
          La pandemia hizo un experimento que ninguna liga habría aprobado: casi una temporada entera con estadios vacíos.
          ¿Qué pasó con la ventaja de local?
        </p>
      </div>
      {!d ? <div className="skeleton" style={{ minHeight: 400 }} /> : (
        <>
          <div className="grid grid-3" style={{ marginBottom: 16 }}>
            {d.eras.map((e, i) => (
              <div key={e.era} className="card" style={{ borderTop: `4px solid ${ERA_COLORS[i]}` }}>
                <div className="small muted">{e.era}</div>
                <div style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: '2.6rem', lineHeight: 1.1 }} className="tabular">
                  {e.goal_diff > 0 ? '+' : ''}{num(e.goal_diff)}
                </div>
                <div className="small" style={{ color: 'var(--ink-2)' }}>goles de diferencia a favor del local por partido</div>
                <div className="small muted tabular" style={{ marginTop: 8 }}>
                  IC 95%: {num(e.goal_diff_ci[0])} a {num(e.goal_diff_ci[1])} · {num(e.matches, 0)} partidos<br />
                  Local {pct(e.home_win)} · empate {pct(e.draw)} · visitante {pct(e.away_win)}<br />
                  {formatDate(e.from)} – {formatDate(e.to)}
                </div>
              </div>
            ))}
          </div>
          <div className="card">
            <h3>Temporada por temporada</h3>
            <p className="card-sub">Diferencia de gol media del local (gris, con IC 95% por bootstrap) y media de cada era (color).</p>
            <HomeAdvantageChart data={d} />
          </div>
          <div className="grid grid-2" style={{ marginTop: 16 }}>
            <div className="card">
              <h3>Qué dicen los datos</h3>
              <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
                <li>Sin público la ventaja cae de {num(d.eras[0].goal_diff)} a {num(d.eras[1].goal_diff)} goles, y su intervalo de confianza incluye el cero.</li>
                <li>La caída es estadísticamente clara (test de permutación, p &lt; 0,001 en el análisis exploratorio, con datos hasta septiembre de 2026), y se mantiene al excluir las semanas con público parcial.</li>
                <li>Con el público de vuelta la ventaja regresó, pero más chica que antes de la pandemia ({num(d.eras[2].goal_diff)} vs {num(d.eras[0].goal_diff)}; p ≈ 0,007 en ese mismo análisis).</li>
              </ul>
            </div>
            <div className="card">
              <h3>Qué no dicen</h3>
              <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
                <li>La era sin público tiene solo {d.eras[1].matches} partidos: de ahí el intervalo ancho.</li>
                <li>Es un estudio observacional: esa época también tuvo calendario comprimido, cinco cambios y sin pretemporada. No se puede atribuir todo al público.</li>
                <li>En diciembre de 2020 y en mayo de 2021 algunos estadios admitieron público limitado; los datos no traen la asistencia de cada partido.</li>
              </ul>
            </div>
          </div>
          <p className="small muted" style={{ marginTop: 16 }}>
            Fechas de las eras: suspensión el 13/03/2020, reanudación a puerta cerrada el 17/06/2020, fin de 2020-21 el
            23/05/2021 y regreso con aforo completo el 13/08/2021 (fuentes en el repositorio, <code>src/eras.py</code>).
            Implicancia para el modelo: la ventaja de local cambia con el tiempo, y el modelo la estima con los datos disponibles hasta cada temporada.
          </p>
        </>
      )}
    </div>
  )
}
