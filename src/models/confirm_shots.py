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

Uso:
    python -m src.models.confirm_shots --out reports/challengers
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import season_label
from src.features.build import FEATURES_PATH
from src.models.challenger import (CHAMPION_FEATURES, MIN_IMPROVEMENT, compare, per_match_log_loss, shot_features,
                                   walk_forward)
from src.models.experiments import prepare

logger = logging.getLogger(__name__)

CONFIRM_SEASONS = [2023, 2024, 2025]
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/challengers"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    features = prepare(pd.read_parquet(FEATURES_PATH))
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
