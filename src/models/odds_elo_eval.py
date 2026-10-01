"""Evaluación preregistrada del rating basado en cuotas (candidatos O1 y O2).

Protocolo en docs/preregistro_cuotas.md (commit c5dcf30, anterior a este código):
* ELO-Odds (src/features/odds_elo.py) ajustado solo con partidos de Premier de 2004-05 a 2014-15; en las otras ligas,
  los mismos parámetros.
* B0 = producción (Poisson sobre elo_diff); O1 = ELO-Odds en lugar de elo_diff; O2 = elo_diff + ELO-Odds.
* Cada temporada 2015-16..2025-26 predicha con ventana expansiva (Inglaterra desde 2004-05; las otras ligas, desde la
  temporada de la replicación).
* Principal: las cinco ligas juntas, candidato − B0 en log loss; señal = IC 95% < 0; regla = media ≤ −0,005 e
  IC 97,5% < 0 (Bonferroni por dos candidatos). Secundarios y descriptivos según el preregistro.

Uso:
    python -m src.models.odds_elo_eval --out reports/challengers
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis.error_analysis import promoted_teams
from src.config import PREMIER_LEAGUE, season_label
from src.data.leagues import LEAGUES, LEAGUES_DIR, matches_path
from src.data.load import load_matches
from src.features.build import load_elo_params
from src.features.odds_elo import ODDS_ELO_PARAMS_PATH, TUNE_SEASONS, compute_odds_elo, tune
from src.models.challenger import MIN_IMPROVEMENT
from src.models.confirm_shots import CANDIDATE as SHOTS
from src.models.experiments import ELO
from src.models.replication import EVAL_SEASONS, TRAIN_START, league_features, log_loss_per_match, stratified_ci, walk_forward
from src.odds import shin_probabilities

logger = logging.getLogger(__name__)

PARAMS_PATH = ODDS_ELO_PARAMS_PATH
ODDS = ["odds_elo_diff"]
MODELS = {"B0": ELO, "O1": ODDS, "O2": [*ELO, *ODDS], "S": SHOTS, "S+O": [*SHOTS, *ODDS]}
CANDIDATES = ("O1", "O2")
FIRST_TRAIN = TRAIN_START | {"ENG": 2004}           # Inglaterra: desde el fin del arranque del ELO-Odds
RULE_LEVEL = 1 - 0.05 / len(CANDIDATES)             # IC 97,5%


def league_frames(params) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    """(variables de la primera división con odds_elo_diff, partidos de ambas divisiones) por liga."""
    out = {}
    for code in ("ENG", *LEAGUES):
        if code == "ENG":
            matches, top, feats = load_matches(), PREMIER_LEAGUE, league_features("ENG")
        else:
            matches, top = pd.read_parquet(matches_path(code)), LEAGUES[code]["top"]
            cached = LEAGUES_DIR / f"{code}_features.parquet"
            if not cached.exists():
                league_features(code).to_parquet(cached, index=False)
            feats = pd.read_parquet(cached)
        ratings = compute_odds_elo(matches, params, top_division=top)
        feats = feats.drop(columns=["odds_elo_home", "odds_elo_away", "odds_elo_diff"], errors="ignore")
        feats = feats.merge(ratings, on="match_id", how="left")
        feats["odds_elo_diff"] = feats["odds_elo_home"] - feats["odds_elo_away"]
        out[code] = (feats, matches)
    return out


def predictions(df: pd.DataFrame, code: str) -> dict[str, pd.Series]:
    """Log loss por partido de cada modelo (índice: match_id)."""
    return {name: log_loss_per_match(walk_forward(df, feats, EVAL_SEASONS, FIRST_TRAIN[code]))
            for name, feats in MODELS.items()}


def market(df: pd.DataFrame, ids: pd.Index) -> tuple[pd.Series, pd.DataFrame]:
    """Log loss de Bet365 (Shin) y sus probabilidades, en los partidos con cuotas."""
    d = df.set_index("match_id").loc[ids]
    odds = d[["b365_home", "b365_draw", "b365_away"]].to_numpy(float)
    ok = ~np.isnan(odds).any(axis=1) & (odds > 1).all(axis=1)
    probs = pd.DataFrame(shin_probabilities(odds[ok]), index=ids[ok], columns=["m_home", "m_draw", "m_away"])
    k = d.loc[ids[ok], "result"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    return pd.Series(-np.log(probs.to_numpy()[np.arange(len(k)), k]), index=ids[ok]), probs


def compare(ll: dict[str, pd.Series], cand: str, base: str = "B0") -> np.ndarray:
    return (ll[cand] - ll[base].loc[ll[cand].index]).to_numpy()


def summary(deltas: dict[str, np.ndarray]) -> dict:
    mean, ci95 = stratified_ci(deltas)
    _, ci_rule = stratified_ci(deltas, level=RULE_LEVEL)
    return {"n": int(sum(len(d) for d in deltas.values())), "diff": mean, "ci95": ci95,
            "ci_rule": ci_rule, "rule_level": RULE_LEVEL,
            "signal": bool(ci95[1] < 0), "meets_rule": bool(mean <= -MIN_IMPROVEMENT and ci_rule[1] < 0)}


def premier_cuts(feats: pd.DataFrame, matches: pd.DataFrame, ll: dict[str, pd.Series]) -> dict:
    """Cortes del análisis de errores en la Premier: diferencia candidato − B0 y brecha con Bet365."""
    ids = ll["B0"].index
    ll_m, probs = market(feats, ids)
    d = feats.set_index("match_id").loc[ids]
    promoted = promoted_teams(matches)
    base_p = walk_forward(feats, ELO, EVAL_SEASONS, FIRST_TRAIN["ENG"]).set_index("match_id")["p_home"]
    groups = {
        "fechas_1_a_5": d["games_played_home"] <= 4,
        "con_ascendido": pd.Series([(s, h) in promoted or (s, a) in promoted for s, h, a in
                                    zip(d.season_start, d.home_team, d.away_team)], index=ids),
    }
    gap = (base_p.loc[probs.index] - probs["m_home"]).abs()
    for name, lo, hi in (("desacuerdo_menos_5", 0, 0.05), ("desacuerdo_5_a_10", 0.05, 0.10), ("desacuerdo_10_o_mas", 0.10, 1.01)):
        groups[name] = pd.Series(False, index=ids)
        groups[name].loc[gap.index[(gap >= lo) & (gap < hi)]] = True
    out = {}
    for name, mask in groups.items():
        sel = mask[mask].index
        with_m = sel.intersection(ll_m.index)
        out[name] = {"n": int(len(sel)), "share": float(len(sel) / len(ids)),
                     **{f"{c}_minus_B0": float((ll[c].loc[sel] - ll["B0"].loc[sel]).mean()) for c in CANDIDATES},
                     **{f"{c}_minus_bet365": float((ll[c].loc[with_m] - ll_m.loc[with_m]).mean()) for c in ("B0", *CANDIDATES)}}
    return out


def run(params) -> dict:
    frames = league_frames(params)
    leagues, deltas, descriptive = {}, {c: {} for c in CANDIDATES}, {}
    for code, (feats, matches) in frames.items():
        ll = predictions(feats, code)
        ll_m, _ = market(feats, ll["B0"].index)
        name = "Inglaterra" if code == "ENG" else LEAGUES[code]["name"]
        season = feats.set_index("match_id").loc[ll["B0"].index, "season"].to_numpy()
        entry = {"name": name, "n": int(len(ll["B0"])), "bet365_n": int(len(ll_m)),
                 "log_loss": {m: float(v.mean()) for m, v in ll.items()},
                 "minus_bet365": {m: float((ll[m].loc[ll_m.index] - ll_m).mean()) for m in ("B0", *CANDIDATES)}}
        for c in CANDIDATES:
            delta = compare(ll, c)
            deltas[c][code] = delta
            mean, ci = stratified_ci({code: delta})
            by_season = pd.Series(delta).groupby(season).mean()
            entry[c] = {"diff": mean, "ci95": ci, "seasons_improved": int((by_season < 0).sum()),
                        "seasons": int(len(by_season)), "by_season": {s: float(v) for s, v in by_season.items()}}
        descriptive[code] = compare(ll, "S+O", base="S")
        if code == "ENG":
            entry["cuts"] = premier_cuts(feats, matches, ll)
        leagues[code] = entry
        logger.info("%-10s O1 %+.4f · O2 %+.4f · B0−Bet365 %+.4f · O2−Bet365 %+.4f", name, entry["O1"]["diff"],
                    entry["O2"]["diff"], entry["minus_bet365"]["B0"], entry["minus_bet365"]["O2"])
    principal = {c: summary(deltas[c]) for c in CANDIDATES}
    meeting = [c for c in CANDIDATES if principal[c]["meets_rule"]]
    s_mean, s_ci = stratified_ci(descriptive)
    return {
        "date": date.today().isoformat(), "preregistration": "docs/preregistro_cuotas.md",
        "odds_elo_params": params.to_dict(), "tune_seasons": f"{season_label(TUNE_SEASONS[0])} a {season_label(TUNE_SEASONS[-1])}",
        "seasons": [season_label(s) for s in EVAL_SEASONS], "principal": principal,
        "decision": {"meets_rule": meeting, "chosen": min(meeting, key=lambda c: principal[c]["diff"]) if meeting else None},
        "premier": {c: leagues["ENG"][c] for c in CANDIDATES},
        "descriptive_shots_plus_odds_minus_shots": {"n": int(sum(len(d) for d in descriptive.values())), "diff": s_mean, "ci95": s_ci},
        "leagues": leagues,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/challengers"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    elo = load_elo_params()
    params, score, trace = tune(load_matches(), start=elo)
    PARAMS_PATH.write_text(json.dumps({
        "params": params.to_dict(), "tune_log_loss": score, "trace": trace,
        "criterion": "log loss de logit multinomial resultado ~ diferencia de ELO-Odds, Premier 2004-05 a 2014-15",
        "preregistration": "docs/preregistro_cuotas.md"}, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("ELO-Odds ajustado: %s (log loss %.5f)", params, score)
    report = run(params)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"cuotas_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for c, r in report["principal"].items():
        logger.info("%s (cinco ligas, n=%d): %+.4f IC95%% [%+.4f, %+.4f] IC%.1f%% [%+.4f, %+.4f] señal %s regla %s", c, r["n"],
                    r["diff"], *r["ci95"], 100 * r["rule_level"], *r["ci_rule"], r["signal"], r["meets_rule"])
    logger.info("Decisión: %s -> %s", report["decision"], path)


if __name__ == "__main__":
    main()
