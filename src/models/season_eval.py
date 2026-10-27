"""Evaluación histórica preregistrada de la simulación de la temporada (docs/preregistro_temporada.md, commit 02aff79;
otras ligas: docs/preregistro_ligas.md).

Temporadas 2015-16 a 2025-26, cortes antes de la fecha 1 y tras 100, 200 y 300 partidos (en otras ligas, la misma
proporción de la temporada: 26%, 53% y 79%); producto (Elo que se actualiza dentro de la simulación), variante con Elo
fijo y línea base con todos los equipos iguales.

Uso:
    python -m src.models.season_eval --out reports/season                 # Premier
    python -m src.models.season_eval --out reports/season --league ESP    # otra liga
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
from src.league_registry import LEAGUES
from src.models.experiments import ELO, prepare
from src.models.feature_models import PoissonGLMModel
from src.models.season_sim import N_SIMS, RELEGATED, TOP4, final_table, simulate, state_from_matches
from src.serving.league_state import load_league_params
from src.serving.predictor import EloPoissonPredictor
from src.serving.production import ALPHA, export_params

logger = logging.getLogger(__name__)

SEASONS = list(range(2015, 2026))
CUTOFFS = [0, 100, 200, 300]
VARIANTS = ("producto", "elo_fijo", "base_iguales")
CALIBRATION_BINS = [0, 0.05, 0.20, 0.50, 0.80, 0.95, 1.0000001]
N_BOOT = 10_000
PREMIER_SEASON_MATCHES = 380
# Temporadas que no se simulan (incompletas en los datos): Francia 2019-20, suspendida.
SKIP = {"FRA": {2019}}


def cutoff_points(n_matches: int) -> list[int]:
    """Cortes de una temporada de `n_matches` partidos: la misma proporción que 0/100/200/300 de 380."""
    return [k * n_matches // PREMIER_SEASON_MATCHES for k in CUTOFFS]


def relegation_spots(code: str, season: int) -> int:
    """Puestos de descenso directo (docs/preregistro_ligas.md); la promoción no cuenta."""
    if code == "FRA":
        return 3 if season <= 2015 else 4 if season == 2022 else 2
    return RELEGATED if code in ("ENG", "ESP", "ITA") else 2


def run_variant(state, predictor, elo_params, variant: str) -> np.ndarray:
    if variant == "base_iguales":
        state = type(state)(**{**state.__dict__, "elo": np.full(len(state.teams), 1500.0)})
    sim = simulate(state, predictor.rates, elo_params, update_elo=variant == "producto")
    return sim["positions"]


def scores(positions: np.ndarray, teams: list[str], final: pd.DataFrame, relegated: int = RELEGATED) -> dict:
    n = len(teams)
    real = final.set_index("team").loc[teams, "position"].to_numpy()
    out = {}
    events = {"campeon": (positions == 1, real == 1),
              "top4": (positions <= TOP4, real <= TOP4),
              "descenso": (positions > n - relegated, real > n - relegated)}
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


def evaluate(features: pd.DataFrame, code: str = "ENG") -> dict:
    """`features`: la tabla de variables de la primera división de la liga `code` (elo_diff con su Elo de resultados)."""
    elo_params = load_elo_params() if code == "ENG" else load_league_params(code)[1]
    rows = []
    for s in SEASONS:
        if s in SKIP.get(code, ()):
            continue
        train = features[(features.season_start >= 2002) & (features.season_start < s) & features.played]
        model = PoissonGLMModel(ELO, alpha=ALPHA).fit(train)
        predictor = EloPoissonPredictor({"params": export_params(model), "meta": {}})
        season = features[(features.season_start == s) & features.played]
        final = final_table(season)
        for k, point in zip(CUTOFFS, cutoff_points(len(season))):
            state = state_from_matches(season, cutoff_date(season, point))
            for variant in VARIANTS:
                sc = scores(run_variant(state, predictor, elo_params, variant), state.teams, final,
                            relegated=relegation_spots(code, s))
                rows.append({"season": season_label(s), "cutoff": k, "variant": variant, **{
                    f"{e}_{m}": v[m] for e, v in sc.items() for m in ("brier", "log_loss")}, "detail": sc})
        logger.info("%s evaluada", season_label(s))
    report = aggregate(pd.DataFrame(rows))
    report["league"] = code
    report["seasons"] = sorted(set(r["season"] for r in rows))
    if code != "ENG":
        report["preregistration"] = "docs/preregistro_ligas.md"
        report["cutoffs_label"] = "antes de la fecha 1 y tras el 26%, el 53% y el 79% de los partidos"
    return report


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
    parser.add_argument("--league", default="ENG", choices=["ENG", *LEAGUES])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.league == "ENG":
        features = prepare(pd.read_parquet(FEATURES_PATH))
    else:
        from src.serving.league_models import features_path, league_features
        path = features_path(args.league)
        features = prepare(pd.read_parquet(path)) if path.exists() else league_features(args.league)
    report = evaluate(features, args.league)
    args.out.mkdir(parents=True, exist_ok=True)
    prefix = "" if args.league == "ENG" else f"{args.league}_"
    path = args.out / f"{prefix}evaluacion_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for key, entry in report["summary"].items():
        logger.info("%-12s producto Brier %.4f · Elo fijo %.4f · base %.4f · habilidad %.0f%% [%.0f%%, %.0f%%]", key,
                    entry["producto"]["brier"], entry["elo_fijo"]["brier"], entry["base_iguales"]["brier"],
                    100 * entry["producto"]["skill_vs_base"], *[100 * x for x in entry["producto"]["skill_ci"]])
    logger.info("Reporte -> %s", path)


if __name__ == "__main__":
    main()
