"""Prueba histórica preregistrada de los candidatos A (xG) y B (fuerza de la alineación).

Protocolo completo en docs/preregistro_fpl.md (commit 6ae9c2d, anterior a este código). Resumen:
* Cada temporada S de 2023-24 a 2025-26 se predice con el modelo de producción entrenado con 2002-03..S-1
  más una corrección sin intercepto, log λ' = log λ + x·β, con β estimado (Poisson con penalización L2,
  α = 1e-4) en los partidos del archivo de Fantasy anteriores a S.
* Regla por candidato: diferencia media de log loss ≤ -0,005 e IC 95% pareado por debajo de 0.

Evaluación final (julio de 2027, docs/preregistro_xg.md): A con la temporada 2026-27 registrada en paralelo, y la
elección preregistrada entre A y el candidato de tiros.

Uso:
    python -m src.models.fpl_eval --out reports/challengers
    python -m src.models.fpl_eval --final --ledger monitoring-branch/ledger/predictions.csv \\
        --xg-ledger monitoring-branch/ledger/shadow_xg_predictions.csv \\
        --shots-ledger monitoring-branch/ledger/shadow_predictions.csv
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.config import season_label
from src.data.fpl_archive import PLAYER_MATCHES_PATH
from src.features.build import FEATURES_PATH
from src.features.fpl_features import A_COLUMNS, B_COLUMNS, B_CONTROL_COLUMNS, match_features
from src.metrics import OUTCOMES, summarize
from src.models.challenger import MIN_IMPROVEMENT, compare
from src.models.experiments import FIRST_TRAIN_SEASON, prepare
from src.models.feature_models import PoissonGLMModel
from src.models.scoreline import outcome_probabilities, score_matrix
from src.odds import shin_probabilities
from src.serving.production import ALPHA
from src.serving.production import FEATURES as ELO

logger = logging.getLogger(__name__)

EVAL_SEASONS = [2023, 2024, 2025]
FIRST_ARCHIVE_SEASON = 2022
CANDIDATES = {
    "A_xg": {"columns": A_COLUMNS, "impute": "median", "market": "b365", "horizon": "días antes"},
    "B_alineacion": {"columns": B_COLUMNS, "impute": "zero", "market": "psc", "horizon": "una hora antes"},
}
CONTROLS = {"B_control_alineacion_anterior": {"columns": B_CONTROL_COLUMNS, "impute": "zero", "market": "b365",
                                              "horizon": "días antes"}}


class OffsetPoisson:
    """Regresión de Poisson SIN intercepto sobre un offset: log E[y] = offset + z·β, z estandarizado.

    Objetivo idéntico al de sklearn.PoissonRegressor (deviance media / 2 + α/2·||β||²), sin el intercepto:
        (1/n) Σ [exp(offset + zβ) - y·(offset + zβ)] + α/2·||β||²   (+ constante)
    Con β = 0 reproduce exactamente el offset."""

    def __init__(self, alpha: float = ALPHA):
        self.alpha = alpha

    def fit(self, x: np.ndarray, y: np.ndarray, offset: np.ndarray) -> "OffsetPoisson":
        self.mean_, self.scale_ = x.mean(axis=0), x.std(axis=0)
        self.scale_[self.scale_ == 0] = 1.0
        z, n = (x - self.mean_) / self.scale_, len(y)

        def objective(beta):
            eta = offset + z @ beta
            mu = np.exp(eta)
            value = np.sum(mu - y * eta) / n + 0.5 * self.alpha * beta @ beta
            grad = z.T @ (mu - y) / n + self.alpha * beta
            return value, grad

        res = minimize(objective, np.zeros(z.shape[1]), jac=True, method="L-BFGS-B")
        if not res.success:
            raise RuntimeError(f"OffsetPoisson no convergió: {res.message}")
        self.coef_ = res.x
        return self

    def log_rate(self, x: np.ndarray, offset: np.ndarray) -> np.ndarray:
        return offset + ((x - self.mean_) / self.scale_) @ self.coef_


def per_match_ll(probs: np.ndarray, results: np.ndarray) -> np.ndarray:
    k = pd.Series(results).map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy()
    return -np.log(probs[np.arange(len(k)), k])


def per_match_rps(probs: np.ndarray, results: np.ndarray) -> np.ndarray:
    y = (results[:, None] == np.array(OUTCOMES)[None, :]).astype(float)
    return 0.5 * ((probs[:, 0] - y[:, 0]) ** 2 + (probs[:, 2] - y[:, 2]) ** 2)


def season_predictions(df: pd.DataFrame, season: int, spec: dict) -> tuple[pd.DataFrame, dict]:
    """Producción y candidato para la temporada `season` (df: features del proyecto + variables de Fantasy)."""
    base = PoissonGLMModel(ELO, alpha=ALPHA).fit(
        df[(df.season_start >= FIRST_TRAIN_SEASON) & (df.season_start < season) & df.played])
    train = df[(df.season_start >= FIRST_ARCHIVE_SEASON) & (df.season_start < season) & df.played]
    train = train.dropna(subset=spec["columns"])                   # solo partidos con la variable calculable
    target = df[(df.season_start == season) & df.played].copy()
    x_target = target[spec["columns"]]
    fill = train[spec["columns"]].median() if spec["impute"] == "median" else 0.0
    x_target = x_target.fillna(fill)

    lam_tr, mu_tr = base._rates(train)
    lam, mu = base._rates(target)
    x_tr = train[spec["columns"]].to_numpy(float)
    home = OffsetPoisson().fit(x_tr, train["home_goals"].to_numpy(float), np.log(lam_tr))
    away = OffsetPoisson().fit(x_tr, train["away_goals"].to_numpy(float), np.log(mu_tr))
    x = x_target.to_numpy(float)
    lam_c, mu_c = np.exp(home.log_rate(x, np.log(lam))), np.exp(away.log_rate(x, np.log(mu)))
    out = pd.DataFrame({"match_id": target["match_id"].to_numpy(), "season": target["season"].to_numpy(),
                        "result": target["result"].to_numpy()})
    for name, (home_rate, away_rate) in {"prod": (lam, mu), "cand": (lam_c, mu_c)}.items():
        p = outcome_probabilities(score_matrix(home_rate, away_rate))
        out[[f"{name}_h", f"{name}_d", f"{name}_a"]] = p
    params = {"train_matches": int(len(train)), "imputed_target_rows": int(target[spec["columns"]].isna().any(axis=1).sum()),
              "beta_home": dict(zip(spec["columns"], map(float, home.coef_))),
              "beta_away": dict(zip(spec["columns"], map(float, away.coef_)))}
    return out, params


def evaluate(df: pd.DataFrame, name: str, spec: dict) -> dict:
    preds, params = [], {}
    for season in EVAL_SEASONS:
        p, par = season_predictions(df, season, spec)
        preds.append(p)
        params[season_label(season)] = par
    d = pd.concat(preds, ignore_index=True).merge(
        df[["match_id", f"{spec['market']}_home", f"{spec['market']}_draw", f"{spec['market']}_away"]], on="match_id")
    res = d["result"].to_numpy()
    prod, cand = d[["prod_h", "prod_d", "prod_a"]].to_numpy(), d[["cand_h", "cand_d", "cand_a"]].to_numpy()
    ll_prod = pd.Series(per_match_ll(prod, res), index=d["match_id"])
    ll_cand = pd.Series(per_match_ll(cand, res), index=d["match_id"])
    decision = compare(ll_prod, ll_cand)
    delta = ll_cand - ll_prod
    odds = d[[f"{spec['market']}_home", f"{spec['market']}_draw", f"{spec['market']}_away"]].to_numpy(float)
    ok = ~np.isnan(odds).any(axis=1)
    market = shin_probabilities(odds[ok])
    ll_market = pd.Series(per_match_ll(market, res[ok]), index=d["match_id"][ok])
    report = {
        "candidate": name, "columns": spec["columns"], "horizon": spec["horizon"], "decision": decision,
        "by_season": {s: float(v) for s, v in delta.groupby(d["season"].to_numpy()).mean().items()},
        "seasons_improved": int((delta.groupby(d["season"].to_numpy()).mean() < 0).sum()),
        "production": summarize(prod, res), "candidate_metrics": summarize(cand, res),
        "rps": {"production": float(per_match_rps(prod, res).mean()), "candidate": float(per_match_rps(cand, res).mean())},
        "vs_market": {"market": {"b365": "Bet365 pre-cierre", "psc": "Pinnacle cierre"}[spec["market"]],
                      "n": int(ok.sum()), "candidate_minus_market": compare(ll_market, ll_cand[ok.tolist()]),
                      "production_minus_market": compare(ll_market, ll_prod[ok.tolist()])},
        "params": params,
    }
    logger.info("%-32s diff %+.4f IC95%% [%+.4f, %+.4f] · por temporada %s · %s", name, decision["diff"],
                decision["ci_low"], decision["ci_high"], {k: round(v, 4) for k, v in report["by_season"].items()},
                "PROMUEVE" if decision["promote"] else "no promueve")
    return report


def load_frame() -> pd.DataFrame:
    features = prepare(pd.read_parquet(FEATURES_PATH))
    fpl = match_features(pd.read_parquet(PLAYER_MATCHES_PATH), features[["match_id", "date"]])
    return features.merge(fpl, on="match_id", how="left", validate="one_to_one")


def run() -> dict:
    df = load_frame()
    return {
        "date": date.today().isoformat(), "preregistration": "docs/preregistro_fpl.md",
        "seasons": [season_label(s) for s in EVAL_SEASONS],
        "rule": {"min_improvement": MIN_IMPROVEMENT, "ci": "95% bootstrap pareado, debe quedar por debajo de 0"},
        "candidates": [evaluate(df, name, spec) for name, spec in CANDIDATES.items()],
        "controls": [evaluate(df, name, spec) for name, spec in CONTROLS.items()],
    }


# ------------------------------------------------------------------ evaluación final (docs/preregistro_xg.md)

def a_historical(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Log loss por partido de producción y de A en 2023-24..2025-26 (la prueba preregistrada)."""
    d = pd.concat([season_predictions(df, s, CANDIDATES["A_xg"])[0] for s in EVAL_SEASONS], ignore_index=True)
    res = d["result"].to_numpy()
    prod = pd.Series(per_match_ll(d[["prod_h", "prod_d", "prod_a"]].to_numpy(), res), index=d["match_id"])
    cand = pd.Series(per_match_ll(d[["cand_h", "cand_d", "cand_a"]].to_numpy(), res), index=d["match_id"])
    return prod, cand


def choose(a_decision: dict, shots_decision: dict, head_to_head: dict | None) -> dict:
    """Regla de elección preregistrada entre A y el candidato de tiros."""
    a, s = a_decision["promote"], shots_decision["promote"]
    if a and not s:
        return {"chosen": "xg", "reason": "solo A cumple su regla"}
    if s and not a:
        return {"chosen": "tiros", "reason": "solo el candidato de tiros cumple su regla"}
    if not a and not s:
        return {"chosen": None, "reason": "ninguno cumple su regla: se mantiene el modelo de producción"}
    if head_to_head["ci_high"] < 0:
        return {"chosen": "xg", "reason": "cumplen los dos y A es mejor (IC 95% de A − tiros por debajo de 0)"}
    if head_to_head["ci_low"] > 0:
        return {"chosen": "tiros", "reason": "cumplen los dos y tiros es mejor (IC 95% de A − tiros por encima de 0)"}
    return {"chosen": "tiros", "reason": "cumplen los dos sin diferencia concluyente: desempate a favor de tiros"}


def final(df: pd.DataFrame, main_ledger: pd.DataFrame, xg_ledger: pd.DataFrame, shots_ledger: pd.DataFrame,
          store, season: int) -> dict:
    from src.models import confirm_shots

    main_ll = confirm_shots.ledger_log_loss(main_ledger[main_ledger.season_start.astype(int) == season], store)
    xg_ll = confirm_shots.ledger_log_loss(xg_ledger[xg_ledger.season_start.astype(int) == season], store)
    both = main_ll.index.intersection(xg_ll.index)
    live = both[(main_ll.loc[both, "source"] == "vivo").to_numpy() & (xg_ll.loc[both, "source"] == "vivo").to_numpy()]
    prod_hist, a_hist = a_historical(df)
    a_prod = pd.concat([prod_hist, main_ll.loc[both, "ll"]])
    a_cand = pd.concat([a_hist, xg_ll.loc[both, "ll"]])
    a_decision = compare(a_prod, a_cand)

    shots_report = confirm_shots.final(df, main_ledger, shots_ledger, store, season)
    shots_hist = confirm_shots.per_match_log_loss(
        confirm_shots.walk_forward(df, confirm_shots.CANDIDATE, confirm_shots.CONFIRM_SEASONS), df)
    shots_ll = confirm_shots.ledger_log_loss(shots_ledger[shots_ledger.season_start.astype(int) == season], store)
    shots_all = pd.concat([shots_hist, shots_ll["ll"]])
    head = None
    if a_decision["promote"] and shots_report["decision"]["promote"]:
        common = a_cand.index.intersection(shots_all.index)
        # compare(x, y) mide y − x: acá, A − tiros
        head = compare(shots_all[common], a_cand[common])
    return {
        "date": date.today().isoformat(), "preregistration": "docs/preregistro_xg.md",
        "seasons": [season_label(s) for s in EVAL_SEASONS] + [season_label(season)],
        "a_decision": a_decision,
        "a_secondary": {"solo_" + season_label(season): compare(main_ll.loc[both, "ll"], xg_ll.loc[both, "ll"]),
                        "solo_en_vivo": compare(main_ll.loc[live, "ll"], xg_ll.loc[live, "ll"]) if len(live) else None},
        "a_coverage": {"main_evaluated": int(len(main_ll)), "xg_evaluated": int(len(xg_ll)), "paired": int(len(both)),
                       "paired_live": int(len(live)), "main_without_xg": int(len(main_ll.index.difference(xg_ll.index)))},
        "shots": shots_report,
        "head_to_head_a_minus_shots": head,
        "choice": choose(a_decision, shots_report["decision"], head),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/challengers"))
    parser.add_argument("--final", action="store_true", help="Evaluación final preregistrada (julio de 2027)")
    parser.add_argument("--ledger", type=Path, default=Path("monitoring/ledger/predictions.csv"))
    parser.add_argument("--xg-ledger", type=Path, default=Path("monitoring/ledger/shadow_xg_predictions.csv"))
    parser.add_argument("--shots-ledger", type=Path, default=Path("monitoring/ledger/shadow_predictions.csv"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.final:
        from src.monitoring.ledger import read_ledger
        from src.monitoring.shadow_ledger import SHADOW_COLUMNS, SHADOW_XG_COLUMNS
        from src.serving.store import MatchStore

        df = load_frame()
        xg = read_ledger(args.xg_ledger, SHADOW_XG_COLUMNS)
        season = int(xg.season_start.astype(int).max())
        played = int(df[df.season_start == season].played.sum())
        if played < 380:
            raise SystemExit(f"La temporada {season_label(season)} no terminó ({played}/380): el preregistro "
                             "fija la evaluación al final de la temporada")
        report = final(df, read_ledger(args.ledger), xg, read_ledger(args.shots_ledger, SHADOW_COLUMNS),
                       MatchStore.load(), season)
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"evaluacion_final_xg_y_tiros_{report['date']}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Elección: %s (%s) -> %s", report["choice"]["chosen"], report["choice"]["reason"], path)
        return
    report = run()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"fpl_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte -> %s", path)


if __name__ == "__main__":
    main()
