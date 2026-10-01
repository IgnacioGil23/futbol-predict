"""Replicación del candidato de tiros en otras ligas y análisis de la relación Elo → goles entre ligas.

Protocolo en docs/preregistro_replicacion.md (commiteado antes de correr la evaluación). Resumen:
* Mismo candidato que en la Premier (Elo + tiros + tiros al arco, vida media 4; src/models/confirm_shots.py) y
  mismo modelo de base (Poisson sobre la diferencia de Elo, α = 1e-4), en España, Italia, Alemania y Francia.
* El Elo de cada liga usa los parámetros ajustados en Inglaterra, sin reajustar (configs/elo_params.json).
* Cada temporada 2015-16..2025-26 se predice con modelos entrenados desde la primera temporada con tiros
  completos en la primera división de esa liga hasta la anterior (ventana expansiva).
* Principal: las cuatro ligas juntas, IC 95% por bootstrap pareado estratificado por liga.

Análisis entre ligas (descriptivo, no decide nada):
* pendiente e intercepto de la regresión de goles sobre la diferencia de Elo en cada liga;
* transferencia: modelo entrenado en una liga prediciendo otra, contra el modelo de la propia liga.

Uso:
    python -m src.models.replication --out reports/replication
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import season_label
from src.data.leagues import LEAGUES, matches_path
from src.features.build import FEATURES_PATH, build_features, load_elo_params
from src.metrics import OUTCOMES
from src.models.challenger import MIN_IMPROVEMENT
from src.models.confirm_shots import CANDIDATE
from src.models.experiments import prepare
from src.models.feature_models import PoissonGLMModel
from src.odds import shin_probabilities
from src.serving.production import ALPHA
from src.serving.production import FEATURES as ELO

logger = logging.getLogger(__name__)

EVAL_SEASONS = list(range(2015, 2026))                       # 2015-16 .. 2025-26
TRAIN_START = {"ESP": 2005, "ITA": 2006, "GER": 2006, "FRA": 2005, "ENG": 2002}
TRANSFER_SEASONS = [2023, 2024, 2025]
N_BOOT = 10_000


def league_features(code: str) -> pd.DataFrame:
    """Tabla de variables de la primera división de `code` (ENG = la del proyecto)."""
    if code == "ENG":
        return prepare(pd.read_parquet(FEATURES_PATH))
    matches = pd.read_parquet(matches_path(code))
    feats, _ = build_features(matches, load_elo_params(), division=LEAGUES[code]["top"])
    return prepare(feats)


def walk_forward(df: pd.DataFrame, features: list[str], seasons: list[int], train_start: int,
                 train_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Probabilidades por partido; cada temporada con un modelo entrenado en [train_start, S-1] de `train_df`
    (por defecto, la misma liga)."""
    train_df = df if train_df is None else train_df
    out = []
    for s in seasons:
        train = train_df[(train_df.season_start >= train_start) & (train_df.season_start < s) & train_df.played]
        target = df[(df.season_start == s) & df.played]
        fc = PoissonGLMModel(features, alpha=ALPHA).fit(train).predict(target)
        out.append(pd.DataFrame({"match_id": target["match_id"].to_numpy(), "season": target["season"].to_numpy(),
                                 "result": target["result"].to_numpy(), "p_home": fc.probs[:, 0],
                                 "p_draw": fc.probs[:, 1], "p_away": fc.probs[:, 2]}))
    return pd.concat(out, ignore_index=True)


def log_loss_per_match(pred: pd.DataFrame) -> pd.Series:
    k = pred["result"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy()
    p = pred[["p_home", "p_draw", "p_away"]].to_numpy()[np.arange(len(pred)), k]
    return pd.Series(-np.log(p), index=pred["match_id"].to_numpy())


def stratified_ci(deltas: dict[str, np.ndarray], n_boot: int = N_BOOT, seed: int = 0,
                  level: float = 0.95) -> tuple[float, list[float]]:
    """Media de todas las diferencias y su IC (95% por defecto) remuestreando partidos dentro de cada liga."""
    rng = np.random.default_rng(seed)
    total = sum(len(d) for d in deltas.values())
    boots = np.zeros(n_boot)
    for d in deltas.values():
        boots += d[rng.integers(0, len(d), size=(n_boot, len(d)))].sum(axis=1)
    boots /= total
    mean = float(np.concatenate(list(deltas.values())).mean())
    tail = 100 * (1 - level) / 2
    return mean, [float(v) for v in np.percentile(boots, [tail, 100 - tail])]


def replication(frames: dict[str, pd.DataFrame]) -> dict:
    per_league, deltas = {}, {}
    for code, df in frames.items():
        if code == "ENG":
            continue
        base = walk_forward(df, ELO, EVAL_SEASONS, TRAIN_START[code])
        cand = walk_forward(df, CANDIDATE, EVAL_SEASONS, TRAIN_START[code])
        ll_b, ll_c = log_loss_per_match(base), log_loss_per_match(cand)
        delta = (ll_c - ll_b[ll_c.index]).to_numpy()
        deltas[code] = delta
        mean, ci = stratified_ci({code: delta})
        by_season = pd.Series(delta).groupby(base["season"].to_numpy()).mean()
        odds = df.set_index("match_id").loc[base["match_id"], ["b365_home", "b365_draw", "b365_away"]].to_numpy(float)
        ok = ~np.isnan(odds).any(axis=1)
        ll_m = log_loss_per_match(base[ok].assign(**dict(zip(["p_home", "p_draw", "p_away"],
                                                                 shin_probabilities(odds[ok]).T))))
        per_league[code] = {
            "name": LEAGUES[code]["name"], "n": int(len(delta)), "diff": mean, "ci": ci,
            "seasons_improved": int((by_season < 0).sum()), "seasons": int(len(by_season)),
            "by_season": {s: float(v) for s, v in by_season.items()},
            "base_log_loss": float(ll_b.mean()), "candidate_log_loss": float(ll_c.mean()),
            "bet365_log_loss": float(ll_m.mean()), "bet365_n": int(ok.sum()),
            "base_minus_bet365": float((ll_b[ll_m.index] - ll_m).mean()),
        }
        logger.info("%-9s diff %+.4f IC95%% [%+.4f, %+.4f] · temporadas que mejora %d/%d", LEAGUES[code]["name"], mean,
                    *ci, per_league[code]["seasons_improved"], per_league[code]["seasons"])
    mean, ci = stratified_ci(deltas)
    return {
        "pooled": {"n": int(sum(len(d) for d in deltas.values())), "diff": mean, "ci": ci,
                   "signal_replicated": bool(ci[1] < 0),
                   "relevant_magnitude": bool(ci[1] < 0 and mean <= -MIN_IMPROVEMENT),
                   "leagues_improved": int(sum(v["diff"] < 0 for v in per_league.values()))},
        "per_league": per_league,
    }


def elo_relationship(frames: dict[str, pd.DataFrame], seasons: range = range(2005, 2026),
                     n_boot: int = 500, seed: int = 0) -> dict:
    """Por liga: goles esperados con Elo parejo y cuánto cambian cada 100 puntos de diferencia (IC 95% por
    bootstrap de partidos)."""
    rng, out = np.random.default_rng(seed), {}

    def fit(d: pd.DataFrame) -> list[float]:
        m = PoissonGLMModel(ELO, alpha=ALPHA).fit(d)
        vals = []
        for pipe in (m.home_, m.away_):
            _, scaler, glm = pipe.named_steps.values()
            slope = glm.coef_[0] / scaler.scale_[0]
            vals += [float(np.exp(glm.intercept_ - slope * scaler.mean_[0])), float(np.exp(100 * slope))]
        return vals                                  # [goles local Elo parejo, factor local, goles visit., factor visit.]

    names = ["home_goals_even", "home_factor_per_100", "away_goals_even", "away_factor_per_100"]
    for code, df in frames.items():
        d = df[df.season_start.isin(seasons) & df.played].reset_index(drop=True)
        point = fit(d)
        boots = np.array([fit(d.iloc[rng.integers(0, len(d), len(d))]) for _ in range(n_boot)])
        lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
        out[code] = {"name": LEAGUES.get(code, {"name": "Inglaterra"})["name"], "n": int(len(d)),
                     "draw_rate": float((d["result"] == "D").mean()),
                     "elo_diff_sd": float(d["elo_diff"].std()),
                     **{n: {"value": p, "ci": [float(a), float(b)]} for n, p, a, b in zip(names, point, lo, hi)}}
    return out


def transfer(frames: dict[str, pd.DataFrame]) -> dict:
    """Log loss en 2023-24..2025-26 de cada liga destino, con el modelo (Elo) entrenado en cada liga origen;
    diferencia contra el modelo de la propia liga."""
    out = {}
    for target, tdf in frames.items():
        own = log_loss_per_match(walk_forward(tdf, ELO, TRANSFER_SEASONS, TRAIN_START[target]))
        row = {}
        for source, sdf in frames.items():
            ll = log_loss_per_match(walk_forward(tdf, ELO, TRANSFER_SEASONS, TRAIN_START[source], train_df=sdf))
            mean, ci = stratified_ci({source: (ll - own[ll.index]).to_numpy()})
            row[source] = {"log_loss": float(ll.mean()), "diff_vs_own": mean, "ci": ci}
        out[target] = row
    return out


def run() -> dict:
    frames = {code: league_features(code) for code in ["ENG", *LEAGUES]}
    return {
        "date": date.today().isoformat(), "preregistration": "docs/preregistro_replicacion.md",
        "candidate": CANDIDATE, "eval_seasons": [season_label(s) for s in EVAL_SEASONS], "train_start": TRAIN_START,
        "rule": {"signal": "IC 95% del conjunto por debajo de 0",
                 "relevant_magnitude": f"además, diferencia media ≤ -{MIN_IMPROVEMENT}"},
        "replication": replication(frames),
        "elo_relationship": elo_relationship(frames),
        "transfer": transfer(frames),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/replication"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"replicacion_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte -> %s", path)


if __name__ == "__main__":
    main()
