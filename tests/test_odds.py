import numpy as np
import pytest

from src.odds import booksum, proportional_probabilities, shin_probabilities

ODDS = np.array([
    [1.40, 4.50, 8.00],   # favorito local claro
    [2.60, 3.20, 2.80],   # partido parejo
    [8.50, 5.00, 1.36],   # favorito visitante claro
])


def test_booksum_is_above_one_for_real_markets():
    assert np.all(booksum(ODDS) > 1)


@pytest.mark.parametrize("method", [proportional_probabilities, shin_probabilities])
def test_probabilities_sum_to_one_and_are_valid(method):
    p = method(ODDS)
    np.testing.assert_allclose(p.sum(axis=1), 1.0, atol=1e-9)
    assert np.all((p > 0) & (p < 1))


def test_shin_corrects_favourite_longshot_bias():
    # Shin asigna más margen a los "longshots": frente a la normalización
    # proporcional, el favorito sube y la opción menos probable baja.
    prop = proportional_probabilities(ODDS)
    shin = shin_probabilities(ODDS)
    assert shin[0, 0] > prop[0, 0] and shin[0, 2] < prop[0, 2]
    assert shin[2, 2] > prop[2, 2] and shin[2, 0] < prop[2, 0]


def test_shin_without_margin_equals_proportional():
    fair = 1 / np.array([[0.5, 0.3, 0.2]])
    p, z = shin_probabilities(fair, return_z=True)
    np.testing.assert_allclose(p, [[0.5, 0.3, 0.2]], atol=1e-12)
    assert z[0] == 0.0


def test_shin_z_is_small_and_positive_for_typical_margin():
    _, z = shin_probabilities(ODDS, return_z=True)
    assert np.all((z > 0) & (z < 0.1))


def test_rows_with_nan_propagate_nan():
    odds = np.vstack([ODDS[:1], [[np.nan, 3.0, 3.0]]])
    for method in (proportional_probabilities, shin_probabilities):
        p = method(odds)
        assert not np.isnan(p[0]).any() and np.isnan(p[1]).all()


def test_invalid_odds_raise():
    with pytest.raises(ValueError):
        proportional_probabilities([[1.0, 3.0, 3.0]])
