"""Candidato L: nivel de goles (y con él la ventaja de local) estimado con las temporadas recientes.

Protocolo en docs/preregistro_local.md (commit 0c3ad85, anterior a este código). El modelo de producción se entrena
igual que siempre; después, con la pendiente del Elo fija, los interceptos de las dos regresiones se reestiman con
las 3 temporadas completas anteriores a la predicha. Con la pendiente fija, el intercepto de máxima verosimilitud
de Poisson es exacto:

    b0 = log( Σ y / Σ exp(pendiente · z) )      (z = variable estandarizada como en el modelo)

Uso:
    python -m src.models.home_level --out reports/challengers
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import season_label
from src.data.leagues import LEAGUES
from src.models.experiments import ELO
from src.models.feature_models import Forecast, PoissonGLMModel
from src.models.replication import EVAL_SEASONS, TRAIN_START, log_loss_per_match, stratified_ci
from src.models.scoreline import outcome_probabilities, score_matrix
from src.serving.production import ALPHA

logger = logging.getLogger(__name__)

RECENT_SEASONS = 3


def recent_intercepts(model: PoissonGLMModel, recent: pd.DataFrame) -> tuple[float, float]:
    """Interceptos de máxima verosimilitud en `recent`, con las pendientes del modelo fijas."""
    out = []
    for pipe, target in ((model.home_, "home_goals"), (model.away_, "away_goals")):
        imputer, scaler, glm = pipe.named_steps.values()
        z = scaler.transform(imputer.transform(recent[model.features].astype(float)))
        out.append(float(np.log(recent[target].astype(float).sum() / np.exp(z @ glm.coef_).sum())))
    return out[0], out[1]


def predict_with_intercepts(model: PoissonGLMModel, df: pd.DataFrame, intercepts: tuple[float, float]) -> Forecast:
    rates = []
    for pipe, b0 in zip((model.home_, model.away_), intercepts):
        imputer, scaler, glm = pipe.named_steps.values()
        z = scaler.transform(imputer.transform(df[model.features].astype(float)))
        rates.append(np.exp(b0 + z @ glm.coef_))
    matrix = score_matrix(rates[0], rates[1])
    return Forecast(probs=outcome_probabilities(matrix), lam=rates[0], mu=rates[1], matrix=matrix)


def walk_forward(df: pd.DataFrame, train_start: int, seasons: list[int] = EVAL_SEASONS) -> pd.DataFrame:
    """Probabilidades del modelo base y del candidato L para cada temporada de `seasons`."""
    out = []
    for s in seasons:
        train = df[(df.season_start >= train_start) & (df.season_start < s) & df.played]
        recent = df[(df.season_start >= s - RECENT_SEASONS) & (df.season_start < s) & df.played]
        target = df[(df.season_start == s) & df.played]
        model = PoissonGLMModel(ELO, alpha=ALPHA).fit(train)
        base = model.predict(target).probs
        cand = predict_with_intercepts(model, target, recent_intercepts(model, recent)).probs
        frame = pd.DataFrame({"match_id": target["match_id"].to_numpy(), "season": target["season"].to_numpy(),
                              "result": target["result"].to_numpy()})
        for name, p in (("base", base), ("cand", cand)):
            frame[[f"{name}_h", f"{name}_d", f"{name}_a"]] = p
        out.append(frame)
    return pd.concat(out, ignore_index=True)


def league_result(pred: pd.DataFrame) -> tuple[dict, np.ndarray]:
    ll = {n: log_loss_per_match(pred.rename(columns={f"{n}_h": "p_home", f"{n}_d": "p_draw", f"{n}_a": "p_away"}))
          for n in ("base", "cand")}
    delta = (ll["cand"] - ll["base"]).to_numpy()
    mean, ci = stratified_ci({"x": delta})
    by_season = pd.Series(delta).groupby(pred["season"].to_numpy()).mean()
    return {
        "n": int(len(delta)), "diff": mean, "ci": ci, "seasons_improved": int((by_season < 0).sum()),
        "seasons": int(len(by_season)), "by_season": {s: float(v) for s, v in by_season.items()},
        "home_win": {"actual": float((pred["result"] == "H").mean()), "base": float(pred["base_h"].mean()),
                     "candidate": float(pred["cand_h"].mean())},
        "away_win": {"actual": float((pred["result"] == "A").mean()), "base": float(pred["base_a"].mean()),
                     "candidate": float(pred["cand_a"].mean())},
    }, delta


def load_frames() -> dict[str, pd.DataFrame]:
    from src.data.leagues import LEAGUES_DIR
    from src.models.replication import league_features
    frames = {"ENG": league_features("ENG")}
    for code in LEAGUES:
        cached = LEAGUES_DIR / f"{code}_features.parquet"      # variables de la liga (data/, no versionado)
        if not cached.exists():
            league_features(code).to_parquet(cached, index=False)
        frames[code] = pd.read_parquet(cached)
    return frames


def run() -> dict:
    frames, leagues, deltas = load_frames(), {}, {}
    for code, df in frames.items():
        res, delta = league_result(walk_forward(df, TRAIN_START[code]))
        leagues[code] = {"name": LEAGUES.get(code, {"name": "Inglaterra"})["name"], **res}
        if code != "ENG":
            deltas[code] = delta
        logger.info("%-10s diff %+.4f IC95%% [%+.4f, %+.4f] · P(local) base %.3f cand %.3f real %.3f", leagues[code]["name"],
                    res["diff"], *res["ci"], res["home_win"]["base"], res["home_win"]["candidate"], res["home_win"]["actual"])
    mean, ci = stratified_ci(deltas)
    return {
        "date": date.today().isoformat(), "preregistration": "docs/preregistro_local.md",
        "recent_seasons": RECENT_SEASONS, "seasons": [season_label(s) for s in EVAL_SEASONS],
        "pooled": {"n": int(sum(len(d) for d in deltas.values())), "diff": mean, "ci": ci, "signal": bool(ci[1] < 0),
                   "meets_rule": bool(ci[1] < 0 and mean <= -0.005)},
        "leagues": leagues,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/challengers"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"ventaja_local_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    p = report["pooled"]
    logger.info("Conjunto: diff %+.4f IC95%% [%+.4f, %+.4f] · señal %s · regla %s -> %s", p["diff"], *p["ci"],
                p["signal"], p["meets_rule"], path)


if __name__ == "__main__":
    main()
