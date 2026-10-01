"""Evaluación del modelo en producción a partir del registro inmutable de predicciones.

Cruza cada predicción registrada con el resultado real y calcula:
* métricas de la temporada (log loss, RPS, Brier, aciertos) contra el mercado, en
  los mismos partidos y con IC 95% pareado;
* los 4 indicadores del diseño sobre la ventana de los últimos WINDOW partidos, con
  su estado (ok / atención / alerta) según los umbrales calibrados por backtest;
* calibración, serie acumulada y últimos partidos, para la página de monitoreo.

Con menos de WINDOW partidos evaluados los indicadores se calculan igual, pero el
estado es "insuficiente": con pocos partidos, cualquier desvío es compatible con el azar.

Uso (lo corre el workflow diario):
    python -m src.monitoring.evaluate --ledger monitoring-branch/ledger/predictions.csv \\
        --out monitoring-branch/reports
"""

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PREMIER_LEAGUE
from src.metrics import OUTCOMES, reliability_table, summarize
from src.monitoring.ledger import DEFAULT_LEDGER, read_ledger
from src.monitoring.thresholds import INDICATORS, THRESHOLDS_PATH, per_match_frame, window_indicators
from src.serving.store import MatchStore

logger = logging.getLogger(__name__)

STATUS_ORDER = {"insuficiente": -1, "ok": 0, "atencion": 1, "alerta": 2}
LABELS = {"ok": "En rango", "atencion": "Atención", "alerta": "Alerta", "insuficiente": "Datos insuficientes"}


def load_thresholds(path: Path = THRESHOLDS_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def indicator_status(name: str, value: float | None, th: dict, n: int, window: int) -> str:
    if value is None or n < window:
        return "insuficiente"
    t = th["indicators"][name]
    if t["one_sided"]:
        return "alerta" if value > t["p99.5"] else "atencion" if value > t["p97.5"] else "ok"
    if value < t["p0.5"] or value > t["p99.5"]:
        return "alerta"
    if value < t["p2.5"] or value > t["p97.5"]:
        return "atencion"
    return "ok"


def paired_ci(delta: np.ndarray, n_boot: int = 5000, seed: int = 0) -> list[float] | None:
    if len(delta) < 20:
        return None
    rng = np.random.default_rng(seed)
    boots = delta[rng.integers(0, len(delta), size=(n_boot, len(delta)))].mean(axis=1)
    return [float(x) for x in np.percentile(boots, [2.5, 97.5])]


def join_results(ledger: pd.DataFrame, store: MatchStore) -> pd.DataFrame:
    """Predicciones registradas + resultado real (solo partidos ya jugados)."""
    res = store.matches[(store.matches.division == PREMIER_LEAGUE) & store.matches.home_goals.notna()]
    res = res[["season_start", "home_team", "away_team", "date", "home_goals", "away_goals", "result"]].copy()
    res["result"] = res["result"].astype(str)
    led = ledger.copy()
    led["season_start"] = led["season_start"].astype(int)
    merged = led.merge(res, on=["season_start", "home_team", "away_team"], how="inner")
    merged["match_id"] = merged["season"] + "|" + merged["home_team"] + "|" + merged["away_team"]
    return merged


SHADOW_MODELS = {
    "tiros": {"candidate": "Elo + tiros y tiros al arco (vida media 4)", "ledger": "shadow_predictions.csv",
              "preregistration": "docs/preregistro_tiros.md"},
    "elo": {"candidate": "Modelo anterior: Poisson sobre el Elo de resultados (comparación en vivo)",
            "ledger": "shadow_elo_predictions.csv", "preregistration": "docs/preregistro_cuotas.md"},
}


def shadow_summary(name: str, shadow: pd.DataFrame) -> dict:
    """Solo cuántos partidos registró un modelo en evaluación: los preregistros prohíben mirar resultados
    parciales."""
    return {
        "name": name, **SHADOW_MODELS[name],
        "model_versions": sorted(shadow.model_version.dropna().unique().tolist()),
        "logged": int(len(shadow)),
        "logged_live": int((shadow.source == "vivo").sum()),
        "logged_reconstructed": int((shadow.source == "reconstruido").sum()),
        "evaluation": "al terminar la temporada 2026-27 (julio de 2027)",
    }


def evaluate(ledger: pd.DataFrame, store: MatchStore, thresholds: dict, now: datetime | None = None,
             shadows: dict[str, pd.DataFrame] | None = None) -> dict:
    now = now or datetime.now(UTC)
    window = thresholds["window"]
    joined = join_results(ledger, store)
    pending = len(ledger) - len(joined)
    report: dict = {
        "generated_at": now.isoformat(timespec="seconds"),
        "window": window,
        "counts": {
            "logged": int(len(ledger)),
            "logged_live": int((ledger.source == "vivo").sum()),
            "logged_reconstructed": int((ledger.source == "reconstruido").sum()),
            "evaluated": int(len(joined)),
            "evaluated_live": int((joined.source == "vivo").sum()) if len(joined) else 0,
            "pending": int(pending),
        },
        "model_versions": sorted(ledger.model_version.dropna().unique().tolist()),
        "thresholds": {"computed_on": thresholds["computed_on"], "backtest": thresholds["backtest"]},
        "shadows": [shadow_summary(name, df) for name, df in (shadows or {}).items()],
    }
    if joined.empty:
        report.update({"status": "insuficiente", "status_label": LABELS["insuficiente"], "indicators": {},
                       "season": None, "calibration": [], "cumulative": [], "recent": []})
        return report

    pred = joined[["match_id", "p_home", "p_draw", "p_away", "lam", "mu"]]
    info = joined[["match_id", "date", "result", "home_goals", "away_goals", "market_home", "market_draw", "market_away"]]
    d = per_match_frame(pred, info).merge(
        joined[["match_id", "source", "home_team", "away_team", "season", "model_version"]], on="match_id")

    # Indicadores en la ventana más reciente
    recent = d.tail(window)
    values = window_indicators(recent)
    indicators = {}
    for name, value in values.items():
        n = int(recent.ll_market.notna().sum()) if name == "gap_vs_market" else len(recent)
        status = indicator_status(name, value, thresholds, n, window)
        t = thresholds["indicators"][name]
        indicators[name] = {"description": INDICATORS[name], "value": value, "n": n, "status": status,
                            "status_label": LABELS[status],
                            "normal_range": [t["p2.5"], t["p97.5"]], "alert_range": [t["p0.5"], t["p99.5"]],
                            "backtest_median": t["median"], "one_sided": t["one_sided"]}
    worst = max((i["status"] for i in indicators.values()), key=STATUS_ORDER.get)
    report.update({"status": worst, "status_label": LABELS[worst], "indicators": indicators})

    # Temporada en curso: modelo contra mercado en los mismos partidos
    season = d[d.season == d.season.max()]
    both = season.dropna(subset=["ll_market"])
    probs = season[["p_home", "p_draw", "p_away"]].to_numpy()
    model_metrics = summarize(probs, season.result.to_numpy())
    market_metrics = (summarize(both[["market_home", "market_draw", "market_away"]].to_numpy(), both.result.to_numpy())
                      if len(both) else None)
    report["season"] = {
        "season": season.season.iloc[0], "matches": int(len(season)), "with_market": int(len(both)),
        "live": int((season.source == "vivo").sum()),
        "model": {k: model_metrics[k] for k in ("log_loss", "rps", "brier", "accuracy")},
        "market": {k: market_metrics[k] for k in ("log_loss", "rps", "brier", "accuracy")} if market_metrics else None,
        "gap_vs_market": float((both.ll_model - both.ll_market).mean()) if len(both) else None,
        "gap_ci": paired_ci((both.ll_model - both.ll_market).to_numpy()) if len(both) else None,
        "goals": {"expected": float(season.xg.sum()), "actual": float(season.goals.sum())},
        "draws": {"expected": float(season.p_draw.sum()), "actual": float(season.draw.sum())},
    }
    table = reliability_table(probs, season.result.to_numpy(), n_bins=5)
    report["calibration"] = table[table.n >= 10].round(4).to_dict("records")

    # Serie acumulada de la brecha (para el gráfico) y últimos partidos
    gap = (d.ll_model - d.ll_market)
    cum = gap.expanding().mean()
    report["cumulative"] = [{"date": dt.date().isoformat(), "n": i + 1, "gap": (None if np.isnan(c) else float(c)),
                             "source": s}
                            for i, (dt, c, s) in enumerate(zip(d.date, cum, d.source))]
    k = d.result.map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy()
    d["p_actual"] = d[["p_home", "p_draw", "p_away"]].to_numpy()[np.arange(len(d)), k]
    report["recent"] = [{
        "date": r.date.date().isoformat(), "home_team": r.home_team, "away_team": r.away_team,
        "score": [int(r.home_goals), int(r.away_goals)], "result": r.result,
        "p": [round(r.p_home, 4), round(r.p_draw, 4), round(r.p_away, 4)],
        "market": None if np.isnan(r.market_home) else [round(r.market_home, 4), round(r.market_draw, 4), round(r.market_away, 4)],
        "p_actual": round(float(r.p_actual), 4), "source": r.source, "model_version": r.model_version,
    } for r in d.tail(30).iloc[::-1].itertuples()]
    return report


def history_row(report: dict) -> dict:
    row = {"generated_at": report["generated_at"], "status": report["status"],
           "evaluated": report["counts"]["evaluated"], "evaluated_live": report["counts"]["evaluated_live"]}
    for name, ind in report.get("indicators", {}).items():
        row[name] = ind["value"]
    return row


def issue_markdown(report: dict, repo_url: str = "") -> str:
    """Cuerpo del issue de alerta (en castellano, con los números y el criterio)."""
    lines = [f"**Estado del monitoreo: {report['status_label']}** · {report['generated_at']}", "",
             f"Ventana: últimos {report['window']} partidos evaluados. Umbrales calibrados con backtest "
             f"({report['thresholds']['backtest']['seasons']}).", "",
             "| Indicador | Valor | Rango normal | Estado |", "|---|---|---|---|"]
    for ind in report["indicators"].values():
        lo, hi = ind["normal_range"]
        val = "—" if ind["value"] is None else f"{ind['value']:+.4f}"
        lines.append(f"| {ind['description']} | {val} | {lo:+.4f} a {hi:+.4f} | {ind['status_label']} |")
    lines += ["", "Qué hacer: revisar el reporte y, si el desvío persiste, evaluar candidatos con "
                  "`python -m src.models.challenger` (regla: mejora ≥ 0,005 e IC 95% por debajo de 0).",
              "", "_Issue generado automáticamente por el workflow de monitoreo._"]
    return "\n".join(lines)


def report_changed(path: Path, report: dict) -> bool:
    """¿Cambió algo más que la hora de generación? (Evita un commit y una publicación por día sin novedades.)"""
    if not path.exists():
        return True
    previous = json.loads(path.read_text(encoding="utf-8"))
    current = json.loads(json.dumps(report))   # mismos tipos que al leer el JSON
    previous.pop("generated_at", None)
    current.pop("generated_at", None)
    return previous != current


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--out", type=Path, default=Path("monitoring/reports"))
    parser.add_argument("--issue-body", type=Path, default=None, help="Escribe el cuerpo del issue si hay alerta")
    parser.add_argument("--shadow-ledger", type=Path, default=None, help="Registro del modelo con tiros")
    parser.add_argument("--shadow-elo-ledger", type=Path, default=None, help="Registro del modelo anterior (Elo)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from src.monitoring.shadow_ledger import SHADOW_COLUMNS, SHADOW_ELO_COLUMNS
    shadows = {name: read_ledger(path, columns)
               for name, path, columns in (("tiros", args.shadow_ledger, SHADOW_COLUMNS),
                                           ("elo", args.shadow_elo_ledger, SHADOW_ELO_COLUMNS))
               if path is not None and path.exists()}
    report = evaluate(read_ledger(args.ledger), MatchStore.load(), load_thresholds(), shadows=shadows)
    args.out.mkdir(parents=True, exist_ok=True)
    latest = args.out / "latest.json"
    if report_changed(latest, report):
        latest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        hist = args.out / "history.csv"
        pd.DataFrame([history_row(report)]).to_csv(hist, mode="a", header=not hist.exists(), index=False,
                                                   float_format="%.6f", lineterminator="\n")
    else:
        logger.info("Sin cambios en la evaluación: no se reescribe el reporte.")
    if args.issue_body and report["status"] == "alerta":
        args.issue_body.write_text(issue_markdown(report), encoding="utf-8")
    logger.info("Estado: %s · evaluados %d (en vivo %d) · pendientes %d", report["status_label"],
                report["counts"]["evaluated"], report["counts"]["evaluated_live"], report["counts"]["pending"])


if __name__ == "__main__":
    main()
