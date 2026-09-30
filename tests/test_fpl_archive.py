"""Archivo histórico de Fantasy: limpieza, vinculación con Football-Data y controles de calidad."""

import numpy as np
import pandas as pd
import pytest

from src.data.fpl_archive import (ArchiveQualityError, assert_quality, clean_player_rows, link_fixtures, map_teams,
                                  mask_missing_lineups, player_matches, start_price_agreement)

TEAMS = pd.DataFrame({"id": [1, 2, 3, 4], "code": [3, 6, 1, 43], "name": ["Arsenal", "Spurs", "Man Utd", "Man City"]})
CANON = {1: "Arsenal", 2: "Tottenham", 3: "Man United", 4: "Man City"}


ROUNDS = [[(1, 2), (3, 4)], [(2, 1), (4, 3)], [(1, 3), (2, 4)]]   # cada cruce local-visitante, una sola vez


def season(gameweeks=(1, 2), lineups_from=1, score_offset=0):
    """Temporada mínima de 4 equipos (hasta 3 fechas); 11 titulares por equipo desde la fecha `lineups_from`."""
    fixtures, gw, matches = [], [], []
    for n, g in enumerate(gameweeks):
        for k, (h, a) in enumerate(ROUNDS[n]):
            fid = 10 * n + k + 1
            kickoff = pd.Timestamp("2023-08-12") + pd.Timedelta(days=7 * n)
            fixtures.append({"id": fid, "event": g, "finished": True, "kickoff_time": kickoff.strftime("%Y-%m-%dT15:00:00Z"),
                             "team_h": h, "team_a": a, "team_h_score": 2, "team_a_score": 1})
            matches.append({"division": "E0", "season_start": 2023, "match_id": f"m{fid}", "home_team": CANON[h],
                            "away_team": CANON[a], "date": kickoff, "home_goals": 2 + score_offset, "away_goals": 1})
            for team, home in ((h, True), (a, False)):
                for p in range(12):                       # 11 titulares + 1 suplente
                    starts = int(p < 11 and g >= lineups_from)
                    gw.append({"element": 100 * team + p, "name": f"J{team}-{p}", "position": "MID",
                               "team": TEAMS.set_index("id").loc[team, "name"], "fixture": fid, "was_home": home,
                               "minutes": 90 if p < 11 else 0, "starts": starts, "value": 50 + p + n,
                               "expected_goals": 0.1 * starts, "expected_goals_conceded": 0.1 * starts, "GW": g})
    gw = pd.DataFrame(gw)
    players = pd.DataFrame({"id": gw.element.unique(), "code": gw.element.unique() + 5000})
    players["now_cost"] = players["id"] % 100 + 50 + len(gameweeks) - 1       # precio final
    players["cost_change_start"] = len(gameweeks) - 1                          # subió 1 por fecha
    return {"gw": gw, "fixtures": pd.DataFrame(fixtures), "teams": TEAMS, "players": players}, pd.DataFrame(matches)


def test_team_codes_map_to_canonical_names_and_unknown_codes_fail():
    assert map_teams(TEAMS) == CANON
    with pytest.raises(ArchiveQualityError):
        map_teams(pd.DataFrame({"id": [1], "code": [999], "name": ["Nuevo"]}))


def test_cleaning_removes_managers_and_identical_duplicates():
    raw, _ = season()
    gw = pd.concat([raw["gw"], raw["gw"].head(3),
                    raw["gw"].head(1).assign(element=9999, position="AM", minutes=0, starts=0, value=10)])
    clean, report = clean_player_rows(gw)
    assert report == {"managers_removed": 1, "exact_duplicates_removed": 3}
    assert len(clean) == len(raw["gw"]) and "AM" not in set(clean.position)


def test_cleaning_rejects_conflicting_rows_and_managers_that_played():
    raw, _ = season()
    with pytest.raises(ArchiveQualityError):
        clean_player_rows(pd.concat([raw["gw"], raw["gw"].head(1).assign(minutes=45)]))
    with pytest.raises(ArchiveQualityError):
        clean_player_rows(pd.concat([raw["gw"], raw["gw"].head(1).assign(element=9999, position="AM")]))


def test_gameweeks_without_recorded_lineups_become_missing_not_zero():
    raw, matches = season(gameweeks=(1, 2, 3), lineups_from=2)
    out, report = player_matches(2023, raw, matches)
    assert report["gameweeks_without_lineups"] == [1]
    assert out.loc[out.gameweek == 1, ["starts", "expected_goals", "expected_goals_conceded"]].isna().all().all()
    assert not out.loc[out.gameweek > 1, ["starts", "expected_goals"]].isna().any().any()
    assert report["starts_anomalies"] == []


def test_linking_detects_score_mismatches():
    raw, matches = season(score_offset=1)
    _, report = link_fixtures(2023, raw["fixtures"], raw["teams"], matches)
    assert report["linked"] == 4 and report["score_matches"] == 0 and len(report["score_mismatches"]) == 4


def test_player_side_and_team_are_consistent():
    raw, matches = season()
    out, report = player_matches(2023, raw, matches)
    assert report["team_side_mismatches"] == 0
    first = out[out.gameweek == 1]
    assert set(first[first.is_home].team) == {"Arsenal", "Man United"}
    assert set(first[~first.is_home].team) == {"Tottenham", "Man City"}
    assert out.player_code.notna().all()


def test_start_price_check_detects_a_later_price():
    raw, matches = season(gameweeks=(1, 2, 3))
    out, report = player_matches(2023, raw, matches)
    assert report["start_price"]["agreement"] == 1.0
    leaked = out.assign(price=out.groupby("element")["price"].transform("max"))   # precio final pegado a todo
    assert start_price_agreement(leaked, raw["players"])["agreement"] == 0.0


def full_report(**overrides):
    base = {"fixtures": 380, "finished": 380, "linked": 380, "unlinked": [], "score_matches": 380,
            "score_mismatches": [], "max_day_gap": 0, "team_side_mismatches": 0, "positions": ["DEF", "GK", "MID"],
            "players_without_code": 0, "gameweeks": [1, 2, 3, 4, 5, 6, 8, 9], "gameweeks_without_lineups": [],
            "starts_anomalies": [], "xg_negative": 0, "start_price": {"agreement": 1.0}}
    return base | overrides


def test_quality_gate():
    assert_quality(2023, full_report())
    assert_quality(2023, full_report(gameweeks_without_lineups=[1, 2, 3, 4, 5, 6, 8]))   # salta la fecha 7 inexistente
    bad = [dict(gameweeks_without_lineups=[1, 3]), dict(linked=379), dict(score_matches=379), dict(max_day_gap=2),
           dict(positions=["AM", "MID"]), dict(starts_anomalies=[["m1", "Arsenal", 10]]),
           dict(start_price={"agreement": 0.9}), dict(team_side_mismatches=1), dict(players_without_code=2)]
    for override in bad:
        with pytest.raises(ArchiveQualityError):
            assert_quality(2023, full_report(**override))


def test_masking_ignores_real_zero_xg_when_lineups_exist():
    raw, matches = season(gameweeks=(1, 2))
    raw["gw"].loc[raw["gw"].team == "Spurs", "expected_goals"] = 0.0   # un equipo sin xG pero con titulares
    out, report = player_matches(2023, raw, matches)
    assert report["gameweeks_without_lineups"] == []
    assert (out.loc[out.team == "Tottenham", "expected_goals"] == 0).all()
    assert report["team_matches_with_zero_xg"] == 2
    assert np.isfinite(report["xg_total_over_goals"])
