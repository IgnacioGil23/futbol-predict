"""Evaluación histórica preregistrada de la simulación de la temporada (docs/preregistro_temporada.md, commit 02aff79).

Temporadas 2015-16 a 2025-26, cortes antes de la fecha 1 y tras 100, 200 y 300 partidos; producto (Elo que se actualiza
dentro de la simulación), variante con Elo fijo y línea base con todos los equipos iguales.

Uso:
    python -m src.models.season_eval --out reports/season
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import season_label
from src.features.build import FEATURES_PATH, load_elo_params
from src.models.experiments import ELO, prepare
from src.models.feature_models import PoissonGLMModel
from src.models.season_sim import N_SIMS, RELEGATED, TOP4, final_table, simulate, state_from_matches
from src.serving.predictor import EloPoissonPredictor
from src.serving.production import ALPHA, export_params

logger = logging.getLogger(__name__)

SEASONS = list(range(2015, 2026))
CUTOFFS = [0, 100, 200, 300]
VARIANTS = ("producto", "elo_fijo", "base_iguales")
CALIBRATION_BINS = [0, 0.05, 0.20, 0.50, 0.80, 0.95, 1.0000001]
N_BOOT = 10_000


def run_variant(state, predictor, elo_params, variant: str) -> np.ndarray:
    if variant == "base_iguales":
        state = type(state)(**{**state.__dict__, "elo": np.full(len(state.teams), 1500.0)})
    sim = simulate(state, predictor.rates, elo_params, update_elo=variant == "producto")
    return sim["positions"]


def scores(positions: np.ndarray, teams: list[str], final: pd.DataFrame) -> dict:
    n = len(teams)
    real = final.set_index("team").loc[teams, "position"].to_numpy()
    out = {}
    events = {"campeon": (positions == 1, real == 1),
              "top4": (positions <= TOP4, real <= TOP4),
              "descenso": (positions > n - RELEGATED, real > n - RELEGATED)}
    for name, (sim_event, y) in events.items():
        counts = sim_event.sum(axis=0)
        p = counts / N_SIMS
        y = y.astype(float)
        if name == "campeon":
            brier = float(((p - y) ** 2).sum())
            smooth = (counts + 0.5) / (N_SIMS + 0.5 * n)
            ll = float(-np.log(smooth[y == 1][0]))
        else:
            brier = float(((p - y) ** 2).mean())
            ps = (counts + 0.5) / (N_SIMS + 1.0)
            ll = float(-np.mean(y * np.log(ps) + (1 - y) * np.log(1 - ps)))
        out[name] = {"brier": brier, "log_loss": ll, "p": p.tolist(), "y": y.tolist()}
    return out


def cutoff_date(season: pd.DataFrame, k: int) -> pd.Timestamp:
    ordered = season.sort_values(["date", "match_id"])
    return ordered["date"].iloc[k]


def evaluate(features: pd.DataFrame) -> dict:
    elo_params = load_elo_params()
    rows = []
    for s in SEASONS:
        train = features[(features.season_start >= 2002) & (features.season_start < s) & features.played]
        model = PoissonGLMModel(ELO, alpha=ALPHA).fit(train)
        predictor = EloPoissonPredictor({"params": export_params(model), "meta": {}})
        season = features[(features.season_start == s) & features.played]
        final = final_table(season)
        for k in CUTOFFS:
            state = state_from_matches(season, cutoff_date(season, k))
            for variant in VARIANTS:
                sc = scores(run_variant(state, predictor, elo_params, variant), state.teams, final)
                rows.append({"season": season_label(s), "cutoff": k, "variant": variant, **{
                    f"{e}_{m}": v[m] for e, v in sc.items() for m in ("brier", "log_loss")}, "detail": sc})
        logger.info("%s evaluada", season_label(s))
    return aggregate(pd.DataFrame(rows))


def bootstrap_mean(values: np.ndarray, rng: np.random.Generator) -> list[float]:
    boots = values[rng.integers(0, len(values), size=(N_BOOT, len(values)))].mean(axis=1)
    return [float(v) for v in np.percentile(boots, [2.5, 97.5])]


def aggregate(df: pd.DataFrame) -> dict:
    rng = np.random.default_rng(0)
    summary = {}
    for event in ("campeon", "top4", "descenso"):
        for k in CUTOFFS:
            sub = df[df.cutoff == k].set_index(["variant", "season"])
            entry = {}
            base = sub.loc["base_iguales", f"{event}_brier"].to_numpy()
            for v in VARIANTS:
                b = sub.loc[v, f"{event}_brier"].to_numpy()
                ll = sub.loc[v, f"{event}_log_loss"].to_numpy()
                idx = rng.integers(0, len(b), size=(N_BOOT, len(b)))
                skill = 1 - b[idx].mean(axis=1) / base[idx].mean(axis=1)
                entry[v] = {"brier": float(b.mean()), "brier_ci": bootstrap_mean(b, rng),
                            "log_loss": float(ll.mean()), "log_loss_ci": bootstrap_mean(ll, rng),
                            "skill_vs_base": float(1 - b.mean() / base.mean()),
                            "skill_ci": [float(x) for x in np.percentile(skill, [2.5, 97.5])]}
            summary[f"{event}@{k}"] = entry
    calibration = {}
    prod = df[df.variant == "producto"]
    for event in ("top4", "descenso"):
        p = np.concatenate([r[event]["p"] for r in prod["detail"]])
        y = np.concatenate([r[event]["y"] for r in prod["detail"]])
        bins = pd.cut(p, CALIBRATION_BINS, right=False)
        table = pd.DataFrame({"p": p, "y": y, "bin": bins}).groupby("bin", observed=True).agg(
            n=("y", "size"), predicted=("p", "mean"), observed=("y", "mean"))
        calibration[event] = [{"bin": str(b), **{c: float(v) for c, v in r.items()}} for b, r in table.iterrows()]
    champions = []
    for (season, k), g in prod.groupby(["season", "cutoff"]):
        d = g["detail"].iloc[0]["campeon"]
        champions.append({"season": season, "cutoff": int(k), "p_real_champion": float(np.dot(d["p"], d["y"]))})
    return {"date": date.today().isoformat(), "preregistration": "docs/preregistro_temporada.md",
            "seasons": [season_label(s) for s in SEASONS], "cutoffs": CUTOFFS, "n_sims": N_SIMS,
            "summary": summary, "calibration": calibration, "champion_probability": champions}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/season"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = evaluate(prepare(pd.read_parquet(FEATURES_PATH)))
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"evaluacion_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for key, entry in report["summary"].items():
        logger.info("%-12s producto Brier %.4f · Elo fijo %.4f · base %.4f · habilidad %.0f%% [%.0f%%, %.0f%%]", key,
                    entry["producto"]["brier"], entry["elo_fijo"]["brier"], entry["base_iguales"]["brier"],
                    100 * entry["producto"]["skill_vs_base"], *[100 * x for x in entry["producto"]["skill_ci"]])
    logger.info("Reporte -> %s", path)


if __name__ == "__main__":
    main()
