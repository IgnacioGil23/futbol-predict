"""Confirmación de los tiros en temporadas que no se usaron para elegirlos.

Protocolo (fijado antes de correr, 30/09/2026):
* Candidato ÚNICO, sin volver a elegir: Elo + tiros + tiros al arco con vida media 4
  (el mejor de reports/challengers/challengers_2026-09-30.json, elegido en 2015-16 .. 2022-23).
  Al haber un solo candidato no hay corrección por comparaciones múltiples.
* Temporadas 2023-24, 2024-25 y 2025-26 (1.140 partidos): nunca se usaron para elegir
  variables (solo para el test final del modelo de producción). Ventana expansiva desde
  2002-03, igual que en la selección.
* Regla: la misma de src/models/challenger.py (mejora >= MIN_IMPROVEMENT y IC 95% pareado
  completamente por debajo de 0).

Evaluación final (julio de 2027, ver docs/preregistro_tiros.md): suma a estas temporadas los partidos
de 2026-27 registrados por ambos modelos (registro de producción y registro en paralelo).

Uso:
    python -m src.models.confirm_shots --out reports/challengers
    python -m src.models.confirm_shots --final --ledger monitoring-branch/ledger/predictions.csv \\
        --shadow-ledger monitoring-branch/ledger/shadow_predictions.csv
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import season_label
from src.features.build import FEATURES_PATH
from src.metrics import OUTCOMES
from src.models.challenger import MIN_IMPROVEMENT, compare, per_match_log_loss, shot_features, walk_forward
from src.models.experiments import ELO, prepare

logger = logging.getLogger(__name__)

CONFIRM_SEASONS = [2023, 2024, 2025]
# La referencia preregistrada es el modelo de Elo de resultados (producción cuando se preregistró), aunque la
# producción haya pasado al rating de cuotas: así la pregunta del preregistro no cambia.
CHAMPION_FEATURES = ELO
CANDIDATE = CHAMPION_FEATURES + shot_features(4, with_shots=True)


def run(features: pd.DataFrame, seasons: list[int]) -> dict:
    champ = per_match_log_loss(walk_forward(features, CHAMPION_FEATURES, seasons), features)
    cand = per_match_log_loss(walk_forward(features, CANDIDATE, seasons), features)
    res = compare(champ, cand)
    delta = cand[champ.index] - champ
    season = features.set_index("match_id").loc[champ.index, "season"].to_numpy()
    by_season = {s: float(v) for s, v in delta.groupby(season).mean().items()}
    report = {
        "date": date.today().isoformat(), "seasons": [season_label(s) for s in seasons],
        "candidate": {"name": "elo+tiros+tiros_al_arco_hl4", "features": CANDIDATE},
        "rule": {"min_improvement": MIN_IMPROVEMENT, "ci": "95% bootstrap pareado, debe quedar por debajo de 0"},
        "champion_log_loss": float(champ.mean()), "candidate_log_loss": float(cand[champ.index].mean()),
        **res, "by_season": by_season,
        "seasons_improved": int(sum(v < 0 for v in by_season.values())),
    }
    logger.info("diff %+.4f  IC95%% [%+.4f, %+.4f]  por temporada %s  -> %s", res["diff"], res["ci_low"],
                res["ci_high"], {k: round(v, 4) for k, v in by_season.items()},
                "CONFIRMA" if res["promote"] else "no confirma")
    return report


def elo_baseline_ledger(main_ledger: pd.DataFrame, elo_ledger: pd.DataFrame | None, elo_version: str) -> pd.DataFrame:
    """Predicciones del modelo de Elo de resultados en la temporada del registro: las del registro de producción
    mientras fue el modelo de producción (versión `elo_version`) y, desde que el rating de cuotas pasó a producción
    (01/10/2026), las de su registro en paralelo. Ante un partido repetido, vale la primera."""
    from src.monitoring.ledger import KEY

    cols = ["season", "season_start", "home_team", "away_team", "source", "model_version", "p_home", "p_draw", "p_away"]
    parts = [main_ledger.loc[main_ledger["model_version"].astype(str) == elo_version, cols]]
    if elo_ledger is not None and len(elo_ledger):
        parts.append(elo_ledger[cols])
    out = pd.concat(parts, ignore_index=True)
    return out.drop_duplicates(subset=KEY, keep="first").reset_index(drop=True)


def ledger_log_loss(ledger: pd.DataFrame, store) -> pd.DataFrame:
    """Log loss por partido de un registro, contra el resultado real (probabilidades renormalizadas:
    en disco están redondeadas a 6 decimales). Índice: 'temporada|local|visitante'."""
    from src.monitoring.evaluate import join_results

    d = join_results(ledger, store)
    p = d[["p_home", "p_draw", "p_away"]].astype(float)
    p = p.div(p.sum(axis=1), axis=0).to_numpy()
    k = d["result"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy()
    return pd.DataFrame({"ll": -np.log(p[np.arange(len(d)), k]), "source": d["source"].to_numpy(),
                         "season": d["season"].to_numpy()}, index=d["match_id"].to_numpy())


def final(features: pd.DataFrame, main_ledger: pd.DataFrame, shadow_ledger: pd.DataFrame, store,
          season: int) -> dict:
    """Evaluación preregistrada (docs/preregistro_tiros.md): 2023-24..2025-26 + la temporada del registro."""
    champ = per_match_log_loss(walk_forward(features, CHAMPION_FEATURES, CONFIRM_SEASONS), features)
    cand = per_match_log_loss(walk_forward(features, CANDIDATE, CONFIRM_SEASONS), features)
    main_ll = ledger_log_loss(main_ledger[main_ledger.season_start.astype(int) == season], store)
    shadow_ll = ledger_log_loss(shadow_ledger[shadow_ledger.season_start.astype(int) == season], store)
    both = main_ll.index.intersection(shadow_ll.index)
    live = both[(main_ll.loc[both, "source"] == "vivo").to_numpy() & (shadow_ll.loc[both, "source"] == "vivo").to_numpy()]

    pooled_champ = pd.concat([champ, main_ll.loc[both, "ll"]])
    pooled_cand = pd.concat([cand[champ.index], shadow_ll.loc[both, "ll"]])
    season_of = np.concatenate([features.set_index("match_id").loc[champ.index, "season"].to_numpy(),
                                main_ll.loc[both, "season"].to_numpy()])
    report = {
        "date": date.today().isoformat(), "preregistration": "docs/preregistro_tiros.md",
        "candidate": {"name": "elo+tiros+tiros_al_arco_hl4", "features": CANDIDATE},
        "rule": {"min_improvement": MIN_IMPROVEMENT, "ci": "95% bootstrap pareado, debe quedar por debajo de 0"},
        "seasons": [season_label(s) for s in CONFIRM_SEASONS] + [season_label(season)],
        "decision": compare(pooled_champ, pooled_cand),
        "secondary": {
            "solo_" + season_label(season): compare(main_ll.loc[both, "ll"], shadow_ll.loc[both, "ll"]),
            "solo_en_vivo": compare(main_ll.loc[live, "ll"], shadow_ll.loc[live, "ll"]) if len(live) else None,
            "por_temporada": {s: float(v) for s, v in
                              (pooled_cand - pooled_champ).groupby(season_of).mean().items()},
        },
        "coverage": {"main_evaluated": int(len(main_ll)), "shadow_evaluated": int(len(shadow_ll)),
                     "paired": int(len(both)), "paired_live": int(len(live)),
                     "main_without_shadow": int(len(main_ll.index.difference(shadow_ll.index)))},
    }
    d = report["decision"]
    logger.info("Evaluación final: diff %+.4f IC95%% [%+.4f, %+.4f] (n = %d) -> %s", d["diff"], d["ci_low"],
                d["ci_high"], d["n"], "PROMUEVE" if d["promote"] else "no promueve")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/challengers"))
    parser.add_argument("--final", action="store_true", help="Evaluación preregistrada con el registro en paralelo")
    parser.add_argument("--ledger", type=Path, default=Path("monitoring/ledger/predictions.csv"))
    parser.add_argument("--shadow-ledger", type=Path, default=Path("monitoring/ledger/shadow_predictions.csv"))
    parser.add_argument("--elo-ledger", type=Path, default=Path("monitoring/ledger/shadow_elo_predictions.csv"),
                        help="Registro en paralelo del modelo de Elo (referencia desde el 01/10/2026)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    features = prepare(pd.read_parquet(FEATURES_PATH))
    if args.final:
        from src.monitoring.ledger import read_ledger
        from src.monitoring.shadow_ledger import SHADOW_COLUMNS, SHADOW_ELO_COLUMNS
        from src.serving.predictor import EloPoissonPredictor
        from src.serving.production import ELO_MODEL_PATH
        from src.serving.store import MatchStore

        shadow = read_ledger(args.shadow_ledger, SHADOW_COLUMNS)
        season = int(shadow.season_start.astype(int).max())
        played = int(features[features.season_start == season].played.sum())
        if played < 380:
            raise SystemExit(f"La temporada {season_label(season)} no terminó ({played}/380): el preregistro "
                             "fija la evaluación al final de la temporada")
        elo_ledger = read_ledger(args.elo_ledger, SHADOW_ELO_COLUMNS) if args.elo_ledger.exists() else None
        baseline = elo_baseline_ledger(read_ledger(args.ledger), elo_ledger, EloPoissonPredictor.load(ELO_MODEL_PATH).version)
        report = final(features, baseline, shadow, MatchStore.load(), season)
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"evaluacion_final_tiros_{report['date']}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Reporte -> %s", path)
        return
    complete = features[features.season_start.isin(CONFIRM_SEASONS)].groupby("season_start").played.sum()
    if not (complete == 380).all():
        raise SystemExit(f"Temporadas incompletas: {complete.to_dict()}")
    report = run(features, CONFIRM_SEASONS)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"confirmacion_tiros_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte -> %s", path)


if __name__ == "__main__":
    main()
