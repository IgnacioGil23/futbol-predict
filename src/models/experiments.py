"""Experimentos: selección en validación y evaluación final en test.

Protocolo (sin fuga temporal):
* Para evaluar la temporada s, los modelos con features se entrenan con todas las
  temporadas de entrenamiento disponibles hasta s-1 (ventana expansiva, desde
  2002-03) y predicen la temporada s entera. Las features se actualizan partido a
  partido (Elo, tabla, forma), así que el modelo "ve" la temporada avanzar aunque
  sus coeficientes queden fijos durante la temporada: exactamente lo que pasaría
  en producción con un reentrenamiento anual.
* Dixon-Coles clásico no usa features: se reajusta cada semana con los partidos
  anteriores.
* Todos los modelos se comparan en los MISMOS partidos que el mercado.

Uso:
    python -m src.models.experiments --stage validation   # elige configuraciones
    python -m src.models.experiments --stage test         # una sola vez, al final
"""

import argparse
import hashlib
import itertools
import json
import logging
import time

import mlflow
import numpy as np
import pandas as pd

from src.config import PROCESSED_DIR, PROJECT_ROOT, TEST_SEASONS, TRAIN_SEASONS, VALIDATION_SEASONS
from src.data.load import load_matches
from src.features.build import FEATURES_PATH
from src.metrics import OUTCOMES, summarize
from src.models.dixon_coles import DixonColesParams, walk_forward
from src.models.feature_models import EloLogitModel, FrequencyModel, PoissonGLMModel, XGBPoissonModel
from src.models.scoreline import exact_score_log_loss, score_matrix
from src.odds import shin_probabilities

logger = logging.getLogger(__name__)

MLFLOW_URI = f"sqlite:///{(PROJECT_ROOT / 'mlflow.db').as_posix()}"
EXPERIMENT = "premier-league-goals"
SELECTED_PATH = PROJECT_ROOT / "configs" / "selected_models.json"
PREDICTIONS_DIR = PROCESSED_DIR / "predictions"
FIRST_TRAIN_SEASON = min(TRAIN_SEASONS)

ELO = ["elo_diff"]
GOALS = ["gf_ewm_home", "ga_ewm_home", "gf_ewm_away", "ga_ewm_away"]
TABLE = ["ppg_home", "ppg_away", "gdpg_home", "gdpg_away", "ppg_last5_home", "ppg_last5_away",
         "season_opener_home", "season_opener_away"]
OTHER = ["rest_days_c_home", "rest_days_c_away", "matches_last21_home", "matches_last21_away", "h2h_residual"]
FEATURE_SETS = {
    "elo": ELO,
    "elo+goles": ELO + GOALS,
    "elo+goles+sin_publico": ELO + GOALS + ["no_crowds"],
    "elo+goles+tabla+sin_publico": ELO + GOALS + TABLE + ["no_crowds"],
    "todas": ELO + GOALS + TABLE + ["no_crowds"] + OTHER,
}


def prepare(features: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    for side in ("home", "away"):
        # Descanso > 14 días (inicio de temporada, parates) no aporta: se recorta.
        df[f"rest_days_c_{side}"] = df[f"rest_days_{side}"].clip(upper=14)
        df[f"season_opener_{side}"] = df[f"season_opener_{side}"].astype(float)
    df["result"] = df["result"].astype(str)
    return df


# ---------------------------------------------------------------- predicciones

def predict_feature_model(make_model, df: pd.DataFrame, seasons) -> pd.DataFrame:
    rows = []
    for season in seasons:
        train = df[(df.season_start >= FIRST_TRAIN_SEASON) & (df.season_start < season) & df.played]
        target = df[(df.season_start == season) & df.played]
        model = make_model().fit(train)
        fc = model.predict(target)
        out = pd.DataFrame({"match_id": target.match_id.to_numpy(),
                            "p_home": fc.probs[:, 0], "p_draw": fc.probs[:, 1], "p_away": fc.probs[:, 2]})
        if fc.lam is not None:
            out["lam"], out["mu"], out["rho"] = fc.lam, fc.mu, fc.rho
        rows.append(out)
    return pd.concat(rows, ignore_index=True)


def predict_dixon_coles(params: DixonColesParams, matches: pd.DataFrame, df: pd.DataFrame, seasons) -> pd.DataFrame:
    targets = df[df.season_start.isin(seasons) & df.played]
    return walk_forward(matches, targets, params)


def market_predictions(df: pd.DataFrame, seasons) -> dict[str, pd.DataFrame]:
    out = {}
    target = df[df.season_start.isin(seasons) & df.played]
    for name, book in [("mercado_bet365_precierre", "b365"), ("mercado_pinnacle_cierre", "psc")]:
        odds = target[[f"{book}_home", f"{book}_draw", f"{book}_away"]].to_numpy()
        p = shin_probabilities(odds)
        ok = ~np.isnan(p).any(axis=1)
        out[name] = pd.DataFrame({"match_id": target.match_id.to_numpy()[ok],
                                  "p_home": p[ok, 0], "p_draw": p[ok, 1], "p_away": p[ok, 2]})
    return out


# -------------------------------------------------------------------- métricas

def score(pred: pd.DataFrame, df: pd.DataFrame, match_ids=None) -> dict:
    data = pred.merge(df[["match_id", "result", "home_goals", "away_goals"]], on="match_id")
    if match_ids is not None:
        data = data[data.match_id.isin(match_ids)]
    probs = data[["p_home", "p_draw", "p_away"]].to_numpy()
    metrics = summarize(probs, data["result"].to_numpy())
    if "lam" in data:
        if data["rho"].nunique() == 1:
            m = score_matrix(data["lam"].to_numpy(), data["mu"].to_numpy(), float(data["rho"].iloc[0]))
        else:  # Dixon-Coles se reajusta cada semana: rho distinto por grupo
            m = np.concatenate([score_matrix(g["lam"].to_numpy(), g["mu"].to_numpy(), rho)
                                for rho, g in data.groupby("rho", sort=False)])
            order = np.concatenate([g.index.to_numpy() for _, g in data.groupby("rho", sort=False)])
            data = data.loc[order]
        metrics["exact_score_log_loss"] = exact_score_log_loss(m, data.home_goals.astype(int), data.away_goals.astype(int))
    return metrics


def paired_bootstrap(pred_a: pd.DataFrame, pred_b: pd.DataFrame, df: pd.DataFrame, n_boot: int = 5000, seed: int = 0):
    """Diferencia de log loss (a - b) en los partidos comunes, con IC 95% por bootstrap pareado."""
    idx = {o: i for i, o in enumerate(OUTCOMES)}
    data = pred_a.merge(pred_b, on="match_id", suffixes=("_a", "_b")).merge(df[["match_id", "result"]], on="match_id")
    k = data["result"].map(idx).to_numpy()
    pa = data[["p_home_a", "p_draw_a", "p_away_a"]].to_numpy()[np.arange(len(k)), k]
    pb = data[["p_home_b", "p_draw_b", "p_away_b"]].to_numpy()[np.arange(len(k)), k]
    delta = -np.log(pa) + np.log(pb)
    rng = np.random.default_rng(seed)
    boots = delta[rng.integers(0, len(delta), size=(n_boot, len(delta)))].mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"n": int(len(delta)), "diff": float(delta.mean()), "ci_low": float(lo), "ci_high": float(hi)}


# ----------------------------------------------------------------- candidatos

def candidates(stage: str, selected: dict | None = None) -> list[dict]:
    """Configuraciones a evaluar. En test, solo las elegidas en validación."""
    if stage == "test":
        return list(selected.values())
    grid = [{"family": "frecuencias"}, {"family": "logit_elo"}]
    for xi in (0.001, 0.0019, 0.003, 0.004, 0.006, 0.009):
        grid.append({"family": "dixon_coles", "xi": xi, "l2": 1.0})
    for fs, alpha, hl, dc in itertools.product(FEATURE_SETS, (1e-4, 1e-2, 1e-1), (None, 1460, 730), (False, True)):
        grid.append({"family": "poisson_glm", "features": fs, "alpha": alpha, "halflife_days": hl, "dixon_coles": dc})
    for depth, n_est, hl in itertools.product((2, 3), (200, 500), (None, 1460)):
        grid.append({"family": "xgb_poisson", "features": "todas", "max_depth": depth, "n_estimators": n_est,
                     "halflife_days": hl, "dixon_coles": True})
    return grid


def run_config(cfg: dict, df: pd.DataFrame, matches: pd.DataFrame, seasons) -> pd.DataFrame:
    fam = cfg["family"]
    if fam == "frecuencias":
        return predict_feature_model(FrequencyModel, df, seasons)
    if fam == "logit_elo":
        return predict_feature_model(EloLogitModel, df, seasons)
    if fam == "dixon_coles":
        return predict_dixon_coles(DixonColesParams(xi=cfg["xi"], l2=cfg["l2"]), matches, df, seasons)
    feats = FEATURE_SETS[cfg["features"]]
    if fam == "poisson_glm":
        return predict_feature_model(lambda: PoissonGLMModel(feats, alpha=cfg["alpha"], dixon_coles=cfg["dixon_coles"],
                                                             halflife_days=cfg["halflife_days"]), df, seasons)
    if fam == "xgb_poisson":
        return predict_feature_model(lambda: XGBPoissonModel(feats, dixon_coles=cfg["dixon_coles"],
                                                             halflife_days=cfg["halflife_days"],
                                                             max_depth=cfg["max_depth"],
                                                             n_estimators=cfg["n_estimators"]), df, seasons)
    raise ValueError(fam)


def config_name(cfg: dict) -> str:
    return "|".join(f"{k}={v}" for k, v in cfg.items())


# ------------------------------------------------------------------------ main

def run(stage: str) -> pd.DataFrame:
    seasons = list(VALIDATION_SEASONS if stage == "validation" else TEST_SEASONS)
    df = prepare(pd.read_parquet(FEATURES_PATH))
    matches = load_matches()
    for col in ("home_goals", "away_goals"):
        matches[col] = matches[col].astype(float)
    selected = json.loads(SELECTED_PATH.read_text(encoding="utf-8")) if stage == "test" else None

    market = market_predictions(df, seasons)
    # Muestra común de evaluación: partidos con cuotas de Bet365 pre-cierre (todas las temporadas evaluadas las tienen).
    common = set(market["mercado_bet365_precierre"].match_id)
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(EXPERIMENT)

    rows, preds = [], {}
    for name, pred in market.items():
        preds[name] = pred
        rows.append({"config": name, "family": "mercado", **score(pred, df, common)})

    for cfg in candidates(stage, selected):
        start = time.time()
        pred = run_config(cfg, df, matches, seasons)
        metrics = score(pred, df, common)
        metrics["seconds"] = time.time() - start
        name = config_name(cfg)
        preds[name] = pred
        with mlflow.start_run(run_name=f"{stage}:{cfg['family']}"):
            mlflow.set_tags({"stage": stage, "family": cfg["family"], "seasons": ",".join(map(str, seasons))})
            mlflow.log_params({k: str(v) for k, v in cfg.items()})
            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
        rows.append({"config": name, **cfg, **metrics})
        logger.info("%-90s log_loss=%.4f", name[:90], metrics["log_loss"])

    results = pd.DataFrame(rows).sort_values("log_loss").reset_index(drop=True)
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(PREDICTIONS_DIR / f"{stage}_results.csv", index=False)

    if stage == "validation":
        best = (results[results.family != "mercado"].sort_values("log_loss").groupby("family").head(1))
        selected = {}
        for _, r in best.iterrows():
            cfg = {k: r[k] for k in ("family", "features", "alpha", "halflife_days", "dixon_coles", "xi", "l2",
                                     "max_depth", "n_estimators") if k in r and not (isinstance(r[k], float) and np.isnan(r[k]))}
            for k in ("max_depth", "n_estimators"):
                if k in cfg:
                    cfg[k] = int(cfg[k])
            if "halflife_days" in r and cfg["family"] in ("poisson_glm", "xgb_poisson"):
                cfg["halflife_days"] = None if pd.isna(r["halflife_days"]) else float(r["halflife_days"])
            if "dixon_coles" in cfg:
                cfg["dixon_coles"] = bool(cfg["dixon_coles"])
            selected[cfg["family"]] = cfg
        SELECTED_PATH.write_text(json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8")

    # Guardar predicciones de las configuraciones elegidas/evaluadas en test (base del "modo revisión" de la web)
    keep = preds if stage == "test" else {k: v for k, v in preds.items() if k in set(results.config.head(15))}
    for name, pred in keep.items():
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
        pred.assign(config=name).to_parquet(PREDICTIONS_DIR / f"{stage}_{digest}.parquet", index=False)

    # Comparaciones pareadas contra el mercado
    comparisons = []
    top = results[results.family != "mercado"].groupby("family").head(1)
    for _, r in top.iterrows():
        for mk in market:
            comparisons.append({"config": r["config"], "vs": mk, **paired_bootstrap(preds[r["config"]], preds[mk], df)})
    pd.DataFrame(comparisons).to_csv(PREDICTIONS_DIR / f"{stage}_vs_market.csv", index=False)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["validation", "test"], required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.stage == "test" and not SELECTED_PATH.exists():
        raise SystemExit("Primero correr --stage validation")
    results = run(args.stage)
    cols = ["config", "log_loss", "rps", "brier", "accuracy", "ece", "exact_score_log_loss", "n"]
    print(results[[c for c in cols if c in results]].head(25).to_string())


if __name__ == "__main__":
    main()
