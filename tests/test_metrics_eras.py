import numpy as np
import pandas as pd
import pytest

from src import eras
from src.metrics import accuracy, brier_score, log_loss, reliability_table, summarize, wilson_interval

RESULTS = np.array(["H", "D", "A", "H"])
UNIFORM = np.full((4, 3), 1 / 3)


def test_uniform_forecast_has_log_loss_log3():
    assert log_loss(UNIFORM, RESULTS) == pytest.approx(np.log(3))
    assert brier_score(UNIFORM, RESULTS) == pytest.approx(2 / 3)


def test_perfect_forecast():
    perfect = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0]], dtype=float)
    assert log_loss(perfect, RESULTS) == pytest.approx(0, abs=1e-12)
    assert brier_score(perfect, RESULTS) == 0
    assert accuracy(perfect, RESULTS) == 1


def test_metrics_reject_invalid_input():
    with pytest.raises(ValueError):
        log_loss(np.full((4, 3), 0.5), RESULTS)
    with pytest.raises(ValueError):
        log_loss(UNIFORM, np.array(["H", "D", "A", "X"]))
    with pytest.raises(ValueError):
        log_loss(np.array([[np.nan, 0.5, 0.5]]), np.array(["H"]))


def test_reliability_table_of_calibrated_forecast():
    rng = np.random.default_rng(0)
    p = rng.dirichlet([4, 2, 3], size=20000)
    results = np.array([rng.choice(["H", "D", "A"], p=row) for row in p])
    table = reliability_table(p, results)
    big = table[table.n > 500]
    assert np.all(np.abs(big.mean_predicted - big.observed) < 0.03)
    assert summarize(p, results)["ece"] < 0.02


def test_wilson_interval_contains_p():
    low, high = wilson_interval(0.3, 100)
    assert low < 0.3 < high and 0 <= low and high <= 1


def test_eras():
    dates = pd.Series(pd.to_datetime([
        "2020-03-09", "2020-06-17", "2020-12-05", "2021-05-23", "2021-08-13", "2020-07-26",
    ]))
    era = eras.assign_era(dates)
    assert list(era) == [eras.PRE_PANDEMIC, eras.NO_CROWDS, eras.NO_CROWDS,
                         eras.NO_CROWDS, eras.FULL_CROWDS, eras.NO_CROWDS]
    assert list(eras.in_partial_crowd_window(dates)) == [False, False, True, True, False, False]
