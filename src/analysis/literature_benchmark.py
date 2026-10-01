"""Comparación con un resultado publicado: Ley, Van de Wiele y Van Eetvelde (2019).

Ley et al. (Statistical Modelling 19(1), tabla 1) comparan 10 modelos en la Premier League, temporadas
2008-09 a 2017-18, fechas 6 a 38 (3.300 partidos). El mejor, un Poisson bivariado con un parámetro de
fuerza por equipo y ponderación temporal con vida media de 390 días, obtiene RPS = 0,1953; el Poisson
independiente, 0,1954. Su RPS, (1/2M) sum[(P_H - y_H)^2 + (P_A - y_A)^2], es el mismo que calcula
src.metrics.ranked_probability_score para tres resultados.

Acá se calcula el RPS de nuestro modelo de producción (Poisson sobre la diferencia de Elo) en esos
partidos. Solo mide: no se elige ni se ajusta nada con este resultado. Cada temporada se predice con el
modelo entrenado con las temporadas anteriores desde 2002-03 (ventana expansiva, reentrenamiento
anual); el Elo se actualiza partido a partido.

Diferencias de protocolo que hay que declarar:
* Ellos reajustan el modelo después de cada fecha con los dos años previos; nosotros, una vez por
  temporada con toda la historia (y el Elo, partido a partido).
* Nuestros datos no tienen número de fecha. "Fechas 6 a 38" se aproxima quitando los primeros 50
  partidos de cada temporada por fecha y hora (10 partidos por fecha: da exactamente 3.300). Como
  control, también se reporta quitando los partidos en que alguno de los dos equipos jugaba su
  partido de liga número 5 o anterior.
* Su RPS no tiene intervalo publicado ni predicciones por partido: no se puede hacer una prueba
  pareada. Se reporta el IC 95% del nuestro por bootstrap de partidos.

Uso:
    python -m src.analysis.literature_benchmark --out reports/benchmarks/ley2019.json
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import season_label
from src.features.build import FEATURES_PATH
from src.metrics import OUTCOMES, summarize
from src.models.experiments import ELO as FEATURES
from src.models.experiments import predict_feature_model, prepare
from src.models.feature_models import PoissonGLMModel
from src.odds import shin_probabilities
from src.serving.production import ALPHA

logger = logging.getLogger(__name__)

SEASONS = list(range(2008, 2018))          # 2008-09 .. 2017-18
SKIPPED_PER_SEASON = 50                    # 5 fechas de 10 partidos
PUBLISHED = {
    "source": "Ley, Van de Wiele y Van Eetvelde (2019), Statistical Modelling 19(1):55-77, tabla 1",
    "matches": 3300,
    "rps": {"Poisson bivariado, 1 parámetro por equipo (vida media 390 días)": 0.1953,
            "Poisson independiente, 1 parámetro por equipo (vida media 360 días)": 0.1954,
            "Poisson independiente, ataque y defensa (vida media 390 días)": 0.1961},
}
N_BOOT = 10_000


def per_match_rps(probs: np.ndarray, results: np.ndarray) -> np.ndarray:
    y = (results[:, None] == np.array(OUTCOMES)[None, :]).astype(float)
    return 0.5 * ((probs[:, 0] - y[:, 0]) ** 2 + (probs[:, 2] - y[:, 2]) ** 2)


def bootstrap_ci(values: np.ndarray, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    boots = values[rng.integers(0, len(values), size=(N_BOOT, len(values)))].mean(axis=1)
    return [float(v) for v in np.percentile(boots, [2.5, 97.5])]


def select_matches(df: pd.DataFrame, rule: str) -> pd.Series:
    """Máscara de los partidos evaluados ("fechas 6 a 38")."""
    order = df.assign(_t=df["time"].fillna("")).sort_values(["date", "_t", "match_id"])
    if rule == "primeros_50_por_fecha":
        rank = order.groupby("season_start").cumcount()
        return (rank >= SKIPPED_PER_SEASON).reindex(df.index)
    if rule == "ambos_equipos_con_5_partidos":
        return (df["games_played_home"] >= 5) & (df["games_played_away"] >= 5)
    raise ValueError(rule)


def block(name: str, probs: np.ndarray, results: np.ndarray) -> dict:
    rps = per_match_rps(probs, results)
    s = summarize(probs, results)
    return {"name": name, "n": int(len(rps)), "rps": float(rps.mean()), "rps_ci": bootstrap_ci(rps),
            "log_loss": s["log_loss"], "accuracy": s["accuracy"]}


def run(features: pd.DataFrame) -> dict:
    target = features[features.season_start.isin(SEASONS) & features.played].copy()
    pred = predict_feature_model(lambda: PoissonGLMModel(FEATURES, alpha=ALPHA), features, SEASONS)
    target = target.merge(pred, on="match_id")
    out = {"published": PUBLISHED, "seasons": [season_label(s) for s in SEASONS],
           "model": f"Poisson sobre {FEATURES} (producción), ventana expansiva desde 2002-03", "selections": {}}
    for rule in ("primeros_50_por_fecha", "ambos_equipos_con_5_partidos"):
        d = target[select_matches(target, rule).to_numpy()]
        results = d["result"].to_numpy()
        entries = [block("Nuestro modelo", d[["p_home", "p_draw", "p_away"]].to_numpy(), results)]
        for label, book in (("Bet365 pre-cierre", "b365"), ("Pinnacle cierre", "psc")):
            odds = d[[f"{book}_home", f"{book}_draw", f"{book}_away"]].to_numpy(float)
            ok = ~np.isnan(odds).any(axis=1)
            entries.append(block(f"Mercado: {label}", shin_probabilities(odds[ok]), results[ok]))
        out["selections"][rule] = entries
        for e in entries:
            logger.info("%-30s %-28s n %4d  RPS %.4f  IC95%% [%.4f, %.4f]", rule, e["name"], e["n"], e["rps"],
                        *e["rps_ci"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/benchmarks/ley2019.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run(prepare(pd.read_parquet(FEATURES_PATH)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte -> %s", args.out)


if __name__ == "__main__":
    main()
