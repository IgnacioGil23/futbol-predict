"""Ajuste de los parámetros del rating en otra liga (docs/preregistro_ligas.md)."""

from test_features import make_league
from test_odds_elo import with_odds

from src.features import odds_elo, tune_elo


def spanish(df):
    return df.replace({"division": {"E0": "SP1", "E1": "SP2"}})


def test_results_elo_tune_uses_the_given_division_and_seasons():
    league = spanish(make_league(seasons=(2000, 2001, 2002)))
    params, score, trace = tune_elo.tune(league, division="SP1", seasons=[2001, 2002], max_passes=1)
    assert score > 0 and trace[0]["pass"] == 0
    # la ventaja de local se calibra con esa liga y esas temporadas
    sp1 = league[(league.division == "SP1") & league.season_start.isin([2001, 2002])]
    assert params.home_advantage == tune_elo.calibrated_home_advantage(sp1.result.to_numpy())


def test_odds_elo_tune_uses_the_given_division_and_seasons():
    league = with_odds(spanish(make_league(seasons=(2000, 2001, 2002))))
    params, score, _ = odds_elo.tune(league, start=tune_elo.EloParams(), division="SP1", seasons=[2001, 2002],
                                     max_passes=1)
    sp1 = league[(league.division == "SP1") & league.season_start.isin([2001, 2002])]
    assert score > 0
    assert params.home_advantage == odds_elo.calibrated_home_advantage(odds_elo.market_score(sp1))


def test_decision_rule_needs_size_and_a_clear_interval():
    import numpy as np

    from src.models.league_params import decide
    rng = np.random.default_rng(0)
    clear = rng.normal(-0.01, 0.05, size=4000)          # mejora grande y estable
    small = rng.normal(-0.001, 0.001, size=4000)        # estable pero menor que 0,002
    noisy = rng.normal(-0.003, 0.5, size=4000)          # tamaño suficiente pero el IC cruza 0
    assert decide(clear)["adopt"] is True
    assert decide(small)["adopt"] is False
    assert decide(noisy)["adopt"] is False
    assert decide(clear)["level"] == 1 - 0.05 / 8
