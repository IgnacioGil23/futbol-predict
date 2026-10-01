"""Reentrenamiento controlado (lo corre .github/workflows/retrain.yml).

Dos modos:

* anual: la MISMA configuración se reentrena sumando la temporada terminada. No hay
  competencia: es un control de sanidad antes de pasar a producción:
    - validación temporal de la configuración en las últimas 3 temporadas completas
      (cada una predicha con un modelo entrenado solo con las anteriores), contra el mercado;
    - calibración (ECE) y signo de los coeficientes;
    - cambio de los coeficientes respecto del modelo actual.
  Si pasa los controles, escribe el model.json nuevo; el workflow abre un PR que se
  aprueba a mano.

* candidatos: compara configuraciones alternativas contra la actual con la regla de
  src/models/challenger.py, en las últimas 3 temporadas completas + la actual. Solo
  produce un reporte: promover un modelo con otras variables requiere que la capa
  de servicio (API y web) las soporte, así que ese paso es manual.

Uso:
    python -m src.models.retrain --mode anual --report reports/retrain/reporte.md
    python -m src.models.retrain --mode candidatos --report reports/retrain/reporte.md
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import season_label, season_start_year
from src.features.build import FEATURES_PATH
from src.metrics import summarize
from src.models.challenger import CHAMPION_FEATURES, MIN_IMPROVEMENT
from src.models.challenger import run as run_challengers
from src.models.experiments import predict_feature_model, prepare
from src.models.feature_models import PoissonGLMModel
from src.odds import shin_probabilities
from src.serving.predictor import model_version
from src.serving.production import ALPHA, FIRST_TRAIN_SEASON, MODEL_PATH, train_production

logger = logging.getLogger(__name__)

MAX_ECE = 0.05   # sanidad: el backtest histórico ronda 0,02


def validation_block(features: pd.DataFrame, seasons: list[int]) -> dict:
    pred = predict_feature_model(lambda: PoissonGLMModel(CHAMPION_FEATURES, alpha=ALPHA), features, seasons,
                                 first_train=FIRST_TRAIN_SEASON)
    d = pred.merge(features[["match_id", "season", "result", "b365_home", "b365_draw", "b365_away"]], on="match_id")
    odds = d[["b365_home", "b365_draw", "b365_away"]].to_numpy(float)
    ok = ~np.isnan(odds).any(axis=1)
    model = summarize(d[["p_home", "p_draw", "p_away"]].to_numpy(), d.result.to_numpy())
    market = summarize(shin_probabilities(odds[ok]), d.result.to_numpy()[ok]) if ok.any() else None
    by_season = {s: summarize(g[["p_home", "p_draw", "p_away"]].to_numpy(), g.result.to_numpy())["log_loss"]
                 for s, g in d.groupby("season")}
    return {"model": model, "market": market, "by_season": by_season, "n": int(len(d))}


def annual(features: pd.DataFrame, today: date) -> tuple[dict | None, str, bool]:
    current = season_start_year(today)
    old = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    _, artifact = train_production(features, today, old["meta"])
    new_version = model_version(artifact["params"], artifact["meta"]["elo_params"])
    old_version = model_version(old["params"], old["meta"].get("elo_params"))
    val = validation_block(features, list(range(current - 3, current)))
    p = artifact["params"]
    checks = {
        "ECE de la validación temporal < 0,05": val["model"]["ece"] < MAX_ECE,
        "El Elo a favor aumenta los goles del local (coeficiente > 0)": p["home_goals"]["coef"] > 0,
        "El Elo a favor reduce los goles del visitante (coeficiente < 0)": p["away_goals"]["coef"] < 0,
        "Log loss de la validación finito": bool(np.isfinite(val["model"]["log_loss"])),
    }
    passed = all(checks.values())
    lines = [f"## Reentrenamiento anual · {today.isoformat()}", "",
             f"Modelo actual `{old_version}` ({old['meta']['trained_on']['seasons']}, "
             f"{old['meta']['trained_on']['matches']} partidos) → nuevo `{new_version}` "
             f"({artifact['meta']['trained_on']['seasons']}, {artifact['meta']['trained_on']['matches']} partidos).", "",
             "### Coeficientes", "", "| Regresión | Parámetro | Actual | Nuevo | Cambio |", "|---|---|---|---|---|"]
    for reg in ("home_goals", "away_goals"):
        for k in ("intercept", "coef"):
            a, b = old["params"][reg][k], p[reg][k]
            lines.append(f"| {reg} | {k} | {a:+.4f} | {b:+.4f} | {b - a:+.4f} |")
    lines += ["", f"### Validación temporal de la configuración ({', '.join(val['by_season'])})", "",
              "| | Log loss | RPS | Aciertos | ECE |", "|---|---|---|---|---|",
              f"| Modelo | {val['model']['log_loss']:.4f} | {val['model']['rps']:.4f} | {val['model']['accuracy']:.1%} | {val['model']['ece']:.4f} |"]
    if val["market"]:
        m = val["market"]
        lines.append(f"| Bet365 pre-cierre | {m['log_loss']:.4f} | {m['rps']:.4f} | {m['accuracy']:.1%} | {m['ece']:.4f} |")
    lines += ["", "### Controles de sanidad", ""] + [f"- {'✅' if v else '❌'} {k}" for k, v in checks.items()]
    verdict = ("pasa los controles; aprobar este PR lo lleva a producción" if passed
               else "NO pasa los controles; no se genera el modelo nuevo")
    lines += ["", f"Resultado: **{verdict}**."]
    return (artifact if passed else None), "\n".join(lines), passed


def candidates_report(features: pd.DataFrame, today: date) -> tuple[str, bool]:
    current = season_start_year(today)
    report = run_challengers(list(range(current - 3, current + 1)), features)
    lines = [f"## Evaluación de candidatos · {today.isoformat()}", "",
             f"Temporadas: {', '.join(report['seasons'])} (validación temporal, mismos partidos). "
             f"Regla: mejora ≥ {MIN_IMPROVEMENT} de log loss e IC 95% completamente por debajo de 0.", "",
             "| Candidato | Diferencia | IC 95% | ¿Promueve? |", "|---|---|---|---|"]
    for c in report["candidates"]:
        lines.append(f"| {c['candidate']} | {c['diff']:+.4f} | [{c['ci_low']:+.4f}; {c['ci_high']:+.4f}] | "
                     f"{'✅' if c['promote'] else '❌'} |")
    any_promote = any(c["promote"] for c in report["candidates"])
    lines += ["", ("**Hay un candidato que cumple la regla.** Para llevarlo a producción, la API y la web tienen que "
                   "soportar sus variables (hoy el servicio usa solo la diferencia de Elo): es un cambio de código "
                   "que se hace a mano, con su propio PR y tests.") if any_promote else
              "Ningún candidato cumple la regla: se mantiene el modelo actual."]
    return "\n".join(lines), any_promote


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["anual", "candidatos"], required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--today", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    today = date.fromisoformat(args.today) if args.today else date.today()
    features = prepare(pd.read_parquet(FEATURES_PATH))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "anual":
        artifact, text, passed = annual(features, today)
        args.report.write_text(text, encoding="utf-8")
        if not passed:
            logger.error("El modelo reentrenado no pasa los controles de sanidad")
            sys.exit(1)
        MODEL_PATH.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Modelo nuevo -> %s", MODEL_PATH)
    else:
        text, _ = candidates_report(features, today)
        args.report.write_text(text, encoding="utf-8")
    logger.info("Reporte -> %s (temporada %s)", args.report, season_label(season_start_year(today)))


if __name__ == "__main__":
    main()
