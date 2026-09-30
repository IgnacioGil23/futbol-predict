import { CalibrationChart } from '../components/CalibrationChart'
import { formatDate, num, pct, useData } from '../lib/data'
import type { CalibrationFile, MetaFile, ReviewSeasonSummary } from '../lib/types'

const REPO_NOTE = 'Código, notebooks y tests en el repositorio del proyecto.'

export function Method() {
  const meta = useData<MetaFile>('meta.json')
  const calib = useData<CalibrationFile>('calibration.json')
  const review = useData<ReviewSeasonSummary[]>('review/index.json')
  const m = meta.data?.model
  const t = m?.test_metrics

  return (
    <div className="container section" style={{ maxWidth: 980 }}>
      <div className="section-head">
        <span className="eyebrow">Ficha del modelo</span>
        <h1 style={{ fontSize: 'clamp(2rem, 5vw, 3.2rem)' }}>Cómo funciona</h1>
        <p className="lede">Qué hace el modelo, con qué datos, cómo se evaluó y, sobre todo, qué no puede hacer.</p>
      </div>

      <div className="grid" style={{ gap: 16 }}>
        <div className="card">
          <h3>El modelo en una frase</h3>
          <p style={{ color: 'var(--ink-2)' }}>
            Dos regresiones de Poisson (una para los goles del local y otra para los del visitante, en la línea de
            Maher 1982) cuya única variable es la <strong>diferencia de Elo</strong> entre los equipos. Con los goles
            esperados de cada uno se calcula la probabilidad de cada marcador exacto, y sumando celdas, la de victoria
            local, empate y victoria visitante.
          </p>
          {m && <p className="small muted" style={{ marginTop: 8 }}>Entrenado con {num(m.trained_on.matches, 0)} partidos ({m.trained_on.seasons}). {REPO_NOTE}</p>}
        </div>

        <div className="card">
          <h3>El Elo, calculado desde cero</h3>
          <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
            <li>Partido a partido sobre Premier League <strong>y Championship</strong>, para que los ascendidos lleguen con historia.</li>
            <li>Cuanto más amplia la victoria, más se mueve el rating: k = k0·(1 + |diferencia de gol|)^λ (Hvattum y Arntzen, 2010).</li>
            <li>Parámetros ajustados solo con temporadas de entrenamiento{m && `: k0 = ${m.elo_params.k0}, λ = ${m.elo_params.lam}, ventaja de local = ${m.elo_params.home_advantage} puntos`}.</li>
            <li>Mejoró tanto a los parámetros originales del paper como al Elo de ClubElo en la misma muestra.</li>
          </ul>
        </div>

        <div className="card">
          <h3>Cómo se evaluó</h3>
          <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
            <li><strong>Split temporal, nunca aleatorio:</strong> entrenamiento 2002-03 a 2020-21, validación 2021-22 y 2022-23, test 2023-24 a 2025-26.</li>
            <li>Se compararon cinco familias de modelos (frecuencias, logit sobre Elo, Dixon-Coles, Poisson con más variables, XGBoost). <strong>Empataron:</strong> ninguna mejora estadísticamente al modelo simple, así que se eligió el más simple.</li>
            <li>El test se evaluó <strong>una sola vez</strong>, al final.</li>
            <li>Cada predicción de la sección Revisión es fuera de muestra: el modelo se reentrena al inicio de cada temporada con las anteriores.</li>
          </ul>
        </div>

        {t && (
          <div className="card">
            <h3>Resultados en test ({t.seasons})</h3>
            <p className="card-sub">Log loss: cuánto "se sorprende" el pronóstico con lo que pasó (menor es mejor). RPS: penaliza más errarle por mucho que por poco.</p>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Pronóstico</th><th className="num">Log loss</th><th className="num">RPS</th><th className="num">Aciertos 1X2</th></tr></thead>
                <tbody>
                  <tr><td><strong>Este modelo</strong></td><td className="num"><strong>{num(t.model.log_loss, 3)}</strong></td><td className="num">{num(t.model.rps, 3)}</td><td className="num">{pct(t.model.accuracy)}</td></tr>
                  <tr><td>Bet365 pre-cierre (días antes)</td><td className="num">{num(t.bet365_pre_closing.log_loss, 3)}</td><td className="num">{num(t.bet365_pre_closing.rps, 3)}</td><td className="num">{pct(t.bet365_pre_closing.accuracy)}</td></tr>
                  <tr><td>Pinnacle al cierre (minutos antes)*</td><td className="num">{num(t.pinnacle_closing.log_loss, 3)}</td><td className="num">{num(t.pinnacle_closing.rps, 3)}</td><td className="num">{pct(t.pinnacle_closing.accuracy)}</td></tr>
                </tbody>
              </table>
            </div>
            <p className="callout" style={{ marginTop: 12 }}>
              <strong>El modelo no le gana al mercado.</strong> Queda unas 0,02 de log loss por detrás de Bet365 y la
              diferencia es estadísticamente significativa. Es lo esperable: las cuotas incorporan lesiones, alineaciones y
              noticias que el modelo no ve. Sus probabilidades, en cambio, están bien calibradas (abajo).
            </p>
            <p className="small muted" style={{ marginTop: 8 }}>
              * Pinnacle solo tiene cuotas para {t.pinnacle_closing.n} de los {t.model.n} partidos de test. Probabilidades de
              mercado con el margen de la casa quitado por el método de Shin.
            </p>
          </div>
        )}

        {calib.data && (
          <div className="card">
            <h3>¿Sus probabilidades son confiables?</h3>
            <p className="card-sub">Si el modelo dice 40%, ¿pasa 4 de cada 10 veces? Test {calib.data.seasons}, {calib.data.matches} partidos.</p>
            <CalibrationChart model={calib.data.model} market={calib.data.market} />
          </div>
        )}

        {review.data && (
          <div className="card">
            <h3>Temporada por temporada</h3>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Temporada</th><th className="num">Modelo</th><th className="num">Mercado</th><th className="num">Diferencia</th></tr></thead>
                <tbody>
                  {[...review.data].reverse().map((s) => (
                    <tr key={s.season}>
                      <td>{s.season}{s.matches < 380 ? <span className="muted"> ({s.matches} partidos)</span> : ''}</td>
                      <td className="num">{num(s.model.log_loss, 3)}</td>
                      <td className="num">{num(s.market.log_loss, 3)}</td>
                      <td className="num" style={{ color: s.model.log_loss <= s.market.log_loss ? 'var(--good)' : 'var(--ink-2)' }}>
                        {s.model.log_loss - s.market.log_loss > 0 ? '+' : ''}{num(s.model.log_loss - s.market.log_loss, 3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted" style={{ marginTop: 8 }}>Log loss (menor es mejor). Mercado: Bet365 pre-cierre. Temporadas en curso con pocos partidos: cifras muy ruidosas.</p>
          </div>
        )}

        <div className="card">
          <h3>Limitaciones (sin letra chica)</h3>
          <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
            <li>No conoce lesiones, suspensiones, alineaciones, fichajes ni cambios de entrenador.</li>
            <li>Solo ve partidos de liga (Premier y Championship): no FA Cup, League Cup ni competiciones europeas. El descanso y la congestión que muestra la web son solo de liga.</li>
            <li>La ventaja de local cambió con el tiempo (ver "Ventaja de local"); el modelo la estima con los datos hasta cada temporada.</li>
            <li>Los datos se actualizan una vez por semana; los partidos de la fecha se publican pocos días antes.</li>
            <li>Es un proyecto educativo de portfolio: <strong>no es una recomendación de apuestas</strong>.</li>
          </ul>
        </div>

        {meta.data && (
          <div className="card">
            <h3>Datos</h3>
            <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
              {meta.data.sources.map((s) => <li key={s.name}><a href={s.url} target="_blank" rel="noreferrer">{s.name}</a>: {s.use}.</li>)}
            </ul>
            <p className="small muted" style={{ marginTop: 8 }}>
              Último partido en los datos: {formatDate(meta.data.last_match_in_data)} · generado el {formatDate(meta.data.generated_at)}.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
