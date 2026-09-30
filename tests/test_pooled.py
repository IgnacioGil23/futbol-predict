"""Modelos combinados: el armado de la tabla con las cinco ligas."""

import pandas as pd

from src.models.pooled import CODES, FEATURES, LEAGUE_DUMMIES, pooled_frame


def test_pooled_frame_keeps_common_columns_and_marks_each_league():
    frames = {code: pd.DataFrame({"match_id": [f"{code}-1"], "elo_diff": [10.0], "only_here": [1]}) for code in CODES}
    frames["ENG"]["no_crowds"] = 0                        # columna exclusiva de una liga: no pasa a la tabla combinada
    d = pooled_frame(frames)
    assert len(d) == len(CODES) and "no_crowds" not in d.columns
    assert (d[LEAGUE_DUMMIES].sum(axis=1) == 1).all()
    assert d.set_index("league").loc["ITA", "league_ITA"] == 1.0


def test_feature_set_matches_the_preregistration():
    assert "no_crowds" not in FEATURES and FEATURES[0] == "elo_diff"
    assert sum(c.startswith(("sot_", "sh_")) for c in FEATURES) == 8
    assert all(d in FEATURES for d in LEAGUE_DUMMIES) and len(FEATURES) == len(set(FEATURES))
