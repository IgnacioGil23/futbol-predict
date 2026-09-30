import numpy as np
import pandas as pd
import pytest

from src.features.build import POST_MATCH_COLUMNS, build_features
from src.features.elo import EloParams, compute_elo, expected_home
from src.features.h2h import h2h_features
from src.features.team_state import form_rest_features, table_features

PARAMS = EloParams(k0=20, lam=1.0, home_advantage=80, season_regression=0.2, initial_gap=100, newcomer_offset=-50)


def round_robin(teams: list[str]) -> list[list[tuple[str, str]]]:
    """Jornadas de ida y vuelta (método del círculo): nadie juega dos veces por jornada."""
    teams = list(teams)
    rounds = []
    for _ in range(len(teams) - 1):
        half = len(teams) // 2
        rounds.append([(teams[i], teams[-1 - i]) for i in range(half)])
        teams = [teams[0], teams[-1], *teams[1:-1]]
    return rounds + [[(a, h) for h, a in r] for r in rounds]


def make_league(seed: int = 0, seasons=(2000, 2001, 2002)) -> pd.DataFrame:
    """Liga sintética: E0 de 4 equipos y E1 de 4, ida y vuelta, con ascensos y descensos."""
    rng = np.random.default_rng(seed)
    e0, e1 = ["A", "B", "C", "D"], ["E", "F", "G", "H"]
    rows = []
    for season in seasons:
        start = pd.Timestamp(f"{season}-08-10")
        for division, teams in (("E0", e0), ("E1", e1)):
            for r, matchday in enumerate(round_robin(teams)):
                for h, a in matchday:
                    date = start + pd.Timedelta(days=7 * r + (0 if division == "E0" else 1))
                    hg, ag = rng.poisson(1.5), rng.poisson(1.1)
                    rows.append(dict(division=division, season_start=season,
                                     season=f"{season}-{(season + 1) % 100:02d}", date=date, home_team=h,
                                     away_team=a, home_goals=float(hg), away_goals=float(ag)))
        # Ascenso/descenso: el último de E0 baja, el primero de E1 sube; entra un equipo nuevo a E1.
        e0, e1 = e0[:-1] + [e1[0]], [e0[-1]] + e1[1:-1] + [f"N{season}"]
    df = pd.DataFrame(rows)
    df["match_id"] = [f"m{i:04d}" for i in range(len(df))]
    df["result"] = np.select([df.home_goals > df.away_goals, df.home_goals < df.away_goals], ["H", "A"], "D")
    return df


def full_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Completa las columnas que build_features espera de matches.parquet."""
    df = df.copy()
    for col in POST_MATCH_COLUMNS:
        if col not in df:
            df[col] = 0.0
    for col in ["time", "b365_home", "b365_draw", "b365_away", "psc_home", "psc_draw", "psc_away",
                "clubelo_home", "clubelo_away"]:
        df[col] = np.nan
    df["clubelo_provisional"] = False
    # Mismos tipos que data/processed/matches.parquet (enteros con NA de pandas).
    for col in ("home_goals", "away_goals"):
        df[col] = df[col].astype("Int64")
    return df


def blank_from(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Simula conocer solo el calendario desde `cutoff`: borra resultados y estadísticas."""
    out = df.copy()
    future = out["date"] >= cutoff
    for col in POST_MATCH_COLUMNS:
        out.loc[future, col] = np.nan
    return out


@pytest.mark.parametrize("cutoff_index", [2, 7, 12, 17])
def test_features_do_not_depend_on_results_from_the_same_day_or_later(cutoff_index):
    matches = full_frame(make_league())
    dates = np.sort(matches.loc[matches.division == "E0", "date"].unique())
    cutoff = pd.Timestamp(dates[cutoff_index])
    full, _ = build_features(matches, PARAMS)
    partial, _ = build_features(blank_from(matches, cutoff), PARAMS)
    feature_cols = [c for c in full.columns if c not in POST_MATCH_COLUMNS and c != "played"]
    a = full.loc[full.date == cutoff, feature_cols].reset_index(drop=True)
    b = partial.loc[partial.date == cutoff, feature_cols].reset_index(drop=True)
    assert len(a) > 0
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_no_post_match_column_is_used_as_feature_input():
    # Cambiar las estadísticas del propio partido no puede cambiar ninguna feature de ese partido.
    matches = full_frame(make_league())
    tampered = matches.copy()
    for col in POST_MATCH_COLUMNS:
        if col not in ("home_goals", "away_goals", "result"):
            tampered[col] = 99
    a, _ = build_features(matches, PARAMS)
    b, _ = build_features(tampered, PARAMS)
    cols = [c for c in a.columns if c not in POST_MATCH_COLUMNS]
    pd.testing.assert_frame_equal(a[cols], b[cols])


def test_elo_update_is_zero_sum_and_follows_formula():
    matches = make_league().query("season_start == 2000")
    per_match, history = compute_elo(matches, PARAMS)
    first = matches.sort_values(["date", "match_id"]).iloc[0]
    row = per_match.set_index("match_id").loc[first.match_id]
    gamma = expected_home(row.elo_home, row.elo_away, PARAMS.home_advantage)
    alpha = 1.0 if first.home_goals > first.away_goals else 0.5 if first.home_goals == first.away_goals else 0.0
    k = PARAMS.k0 * (1 + abs(first.home_goals - first.away_goals)) ** PARAMS.lam
    after = history[history.match_id == first.match_id].set_index("team").elo_after
    assert after[first.home_team] == pytest.approx(row.elo_home + k * (alpha - gamma))
    assert after[first.home_team] + after[first.away_team] == pytest.approx(row.elo_home + row.elo_away)


def test_elo_initial_gap_and_expected_score():
    matches = make_league()
    per_match, _ = compute_elo(matches, PARAMS)
    first_day = matches[matches.date == matches.date.min()].merge(per_match, on="match_id")
    assert (first_day.elo_home == 1600).all()  # E0 arranca en 1500 + initial_gap
    assert expected_home(1500, 1500, 0) == pytest.approx(0.5)
    assert expected_home(1500, 1500, 100) == pytest.approx(1 / (1 + 10 ** (-0.25)))


def test_unplayed_fixtures_get_ratings_but_do_not_update():
    matches = make_league()
    blanked = matches.copy()
    last_day = blanked.date == blanked.date.max()
    blanked.loc[last_day, ["home_goals", "away_goals"]] = np.nan
    per_match, history = compute_elo(blanked, PARAMS)
    assert per_match.set_index("match_id").loc[blanked[last_day].match_id, "elo_home"].notna().all()
    assert not history.match_id.isin(blanked[last_day].match_id).any()


def test_table_features_known_values():
    df = pd.DataFrame({
        "match_id": ["m1", "m2", "m3"],
        "date": pd.to_datetime(["2020-08-10", "2020-08-17", "2020-08-24"]),
        "season_start": 2020, "division": "E0",
        "home_team": ["A", "B", "A"], "away_team": ["B", "A", "B"],
        "home_goals": [2.0, 1.0, np.nan], "away_goals": [0.0, 1.0, np.nan],
    })
    t = table_features(df).set_index(["match_id", "team"])
    assert np.isnan(t.loc[("m1", "A"), "position"])            # sin partidos: sin posición
    assert t.loc[("m2", "A"), ["points", "goal_diff", "position"]].tolist() == [3, 2, 1]
    assert t.loc[("m3", "A"), ["games_played", "points", "ppg"]].tolist() == [2, 4, 2.0]
    assert t.loc[("m3", "B"), ["points", "goal_diff", "position"]].tolist() == [1, -2, 2]


def test_form_rest_features_known_values():
    df = pd.DataFrame({
        "match_id": ["m1", "m2", "m3", "m4"],
        "date": pd.to_datetime(["2020-08-01", "2020-08-10", "2020-08-20", "2020-08-25"]),
        "season_start": 2020, "division": "E0",
        "home_team": ["A", "A", "A", "A"], "away_team": ["B", "C", "B", "C"],
        "home_goals": [1.0, 0.0, 2.0, np.nan], "away_goals": [0.0, 0.0, 3.0, np.nan],
    })
    f = form_rest_features(df, form_window=2).set_index(["match_id", "team"])
    assert f.loc[("m1", "A"), "season_opener"] and np.isnan(f.loc[("m1", "A"), "rest_days"])
    assert f.loc[("m4", "A"), "rest_days"] == 5
    assert f.loc[("m4", "A"), "ppg_last2"] == pytest.approx((1 + 0) / 2)   # empate y derrota
    assert f.loc[("m4", "A"), "matches_last21"] == 2                    # 10/08 y 20/08 (el 01/08 queda fuera)


def test_h2h_residual_perspective_and_shrinkage():
    df = pd.DataFrame({
        "match_id": ["m1", "m2", "m3"],
        "date": pd.to_datetime(["2020-08-01", "2021-01-01", "2021-08-01"]),
        "home_team": ["A", "B", "A"], "away_team": ["B", "A", "B"],
        "home_goals": [3.0, 0.0, np.nan], "away_goals": [0.0, 1.0, np.nan],
    })
    elo = pd.DataFrame({"match_id": ["m1", "m2", "m3"], "elo_expected_home": [0.6, 0.5, 0.55]})
    h = h2h_features(df, elo, shrinkage=2.0).set_index("match_id")
    assert h.loc["m1", "h2h_n"] == 0 and h.loc["m1", "h2h_residual"] == 0
    # m3 (local A): residuos de A = (1 - 0.6) + (1 - 0.5) = 0.9, dividido (2 + 2)
    assert h.loc["m3", "h2h_residual"] == pytest.approx(0.9 / 4)
    # m2 (local B): perspectiva de B = -(1 - 0.6) / (1 + 2)
    assert h.loc["m2", "h2h_residual"] == pytest.approx(-0.4 / 3)
