import numpy as np
import pandas as pd
import pytest

from src.config import season_code, season_label, season_start_year
from src.data.checks import check_season
from src.data.football_data import clean_odds, read_season, validate_rows
from src.data.teams import canonical_team

HEADER = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A"


def write_csv(tmp_path, lines, encoding="utf-8"):
    path = tmp_path / "E0_test.csv"
    path.write_bytes(("\n".join(lines) + "\n").encode(encoding))
    return path


def test_rows_with_extra_fields_are_kept_not_dropped(tmp_path):
    # Reproduce el caso real de E0 2003/04: filas con más campos que el encabezado.
    path = write_csv(tmp_path, [
        HEADER,
        "E0,16/08/03,Arsenal,Everton,2,1,H,1.4,3.8,8",
        "E0,10/04/04,Arsenal,Liverpool,4,2,H,1.5,3.6,6,1.45,3.5,6.5",
    ])
    df = read_season(path, "E0", 2003)
    assert len(df) == 2
    assert df.attrs["n_long_rows"] == 1
    assert df.loc[1, "b365_home"] == 1.5  # los campos dentro del encabezado no se corren


def test_dates_two_and_four_digit_years(tmp_path):
    path = write_csv(tmp_path, [
        HEADER,
        "E0,16/08/03,Arsenal,Everton,2,1,H,1.4,3.8,8",
        "E0,17/08/2003,Chelsea,Leeds,0,0,D,2,3,4",
    ])
    df = read_season(path, "E0", 2003)
    assert list(df["date"]) == [pd.Timestamp("2003-08-16"), pd.Timestamp("2003-08-17")]


def test_unparseable_date_raises(tmp_path):
    path = write_csv(tmp_path, [HEADER, "E0,2003-08-16,Arsenal,Everton,2,1,H,1.4,3.8,8"])
    with pytest.raises(ValueError, match="Fechas"):
        read_season(path, "E0", 2003)


def test_blank_trailing_rows_and_unplayed_fixtures_are_ignored(tmp_path):
    path = write_csv(tmp_path, [
        HEADER,
        "E0,16/08/03,Arsenal,Everton,2,1,H,1.4,3.8,8",
        "E0,23/08/03,Arsenal,Leeds,,,,1.3,4,9",
        ",,,,,,,,,",
    ])
    assert len(read_season(path, "E0", 2003)) == 1


def test_utf8_bom_and_latin1_files(tmp_path):
    bom = write_csv(tmp_path, ["﻿" + HEADER, "E0,16/08/03,Arsenal,Everton,2,1,H,1.4,3.8,8"])
    assert read_season(bom, "E0", 2003).loc[0, "home_team"] == "Arsenal"
    latin = write_csv(tmp_path, [HEADER, "E0,16/08/03,Arsenal,Everton,2,1,H,1.4,3.8,8,Sérgio"], "latin-1")
    assert len(read_season(latin, "E0", 2003)) == 1


def test_team_aliases_are_canonicalized(tmp_path):
    path = write_csv(tmp_path, [HEADER, "E0,16/08/22,Nottm Forest,Everton,2,1,H,1.4,3.8,8"])
    assert read_season(path, "E0", 2022).loc[0, "home_team"] == "Nott'm Forest"
    assert canonical_team(" Nottm Forest ") == "Nott'm Forest"
    assert pd.isna(canonical_team(None))


def test_missing_bookmaker_columns_become_nan(tmp_path):
    path = write_csv(tmp_path, ["Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR", "E0,19/08/00,Charlton,Man City,4,0,H"])
    df = read_season(path, "E0", 2000)
    assert df[["b365_home", "psc_home", "avg_home"]].isna().all().all()


def _match(**overrides):
    base = dict(division="E0", season="2003-04", date=pd.Timestamp("2003-08-16"),
                home_team="Arsenal", away_team="Everton", home_goals=2, away_goals=1, result="H",
                ht_home_goals=1, ht_away_goals=0)
    for book in ("b365", "b365c", "ps", "psc", "avg"):
        base.update({f"{book}_home": np.nan, f"{book}_draw": np.nan, f"{book}_away": np.nan})
    base.update(overrides)
    return base


def test_clean_odds_nulls_impossible_triplets_only():
    df = pd.DataFrame([
        _match(b365_home=1.5, b365_draw=4.0, b365_away=6.0),                        # válido (suma 1.08)
        _match(home_team="Chelsea", b365_home=0.0, b365_draw=3.4, b365_away=3.4),   # 0 = sin dato
        _match(home_team="Leeds", psc_home=3.72, psc_draw=3.57, psc_away=2.6),      # suma 0.934
    ])
    cleaned, report = clean_odds(df)
    assert cleaned.loc[0, "b365_home"] == 1.5
    assert cleaned.loc[1, ["b365_home", "b365_draw", "b365_away"]].isna().all()
    assert cleaned.loc[2, ["psc_home", "psc_draw", "psc_away"]].isna().all()
    assert len(report) == 2
    validate_rows(cleaned)


def test_validate_rows_detects_result_goal_mismatch_and_duplicates():
    with pytest.raises(ValueError, match="resultados"):
        validate_rows(pd.DataFrame([_match(result="A")]))
    with pytest.raises(ValueError, match="duplicados"):
        validate_rows(pd.DataFrame([_match(), _match()]))
    with pytest.raises(ValueError, match="entretiempo"):
        validate_rows(pd.DataFrame([_match(ht_home_goals=3)]))


def _round_robin(teams, division="E0"):
    return pd.DataFrame([
        {"division": division, "season": "2010-11", "home_team": h, "away_team": a}
        for h in teams for a in teams if h != a
    ])


def test_check_season_accepts_complete_double_round_robin():
    season = _round_robin([f"T{i}" for i in range(20)])
    check = check_season(season, is_current=False)
    assert check.complete and not check.problems and check.matches == 380


def test_check_season_flags_missing_matches_but_not_in_current_season():
    season = _round_robin([f"T{i}" for i in range(20)]).iloc[:335]
    assert check_season(season, is_current=False).problems
    assert not check_season(season, is_current=True).problems


def test_check_season_flags_repeated_fixture():
    season = _round_robin([f"T{i}" for i in range(20)])
    season = pd.concat([season, season.iloc[[0]]])
    assert any("repetidos" in p for p in check_season(season, is_current=True).problems)


@pytest.mark.parametrize("day, expected", [
    ("2020-07-26", 2019),  # última fecha de 2019/20, jugada en julio por la pandemia
    ("2020-09-12", 2020),
    ("2026-08-01", 2026),
    ("2026-07-31", 2025),
])
def test_season_start_year(day, expected):
    assert season_start_year(pd.Timestamp(day).date()) == expected


def test_season_code_and_label():
    assert season_code(2003) == "0304"
    assert season_code(2099) == "9900"
    assert season_label(2019) == "2019-20"


def test_parse_fixtures_real_format():
    from src.data.fixtures import parse_fixtures
    text = ("﻿Div,Date,Time,HomeTeam,AwayTeam,Referee,B365H,B365D,B365A\n"
            "EC,29/09/2026,19:00,Boreham Wood,Kidderminster,A Humphries,1.33,5,7.5\n"
            "E0,03/10/2026,15:00,Nottm Forest,Arsenal,,3.1,3.4,2.3\n"
            "E0,04/10/2026,16:30,Chelsea,Liverpool,,,,\n")
    df = parse_fixtures(text)
    assert list(df.HomeTeam) == ["Nott'm Forest", "Chelsea"]           # solo Premier, nombres canónicos
    assert list(df.date) == [pd.Timestamp("2026-10-03"), pd.Timestamp("2026-10-04")]   # día/mes, no mes/día
    assert df.B365H.iloc[0] == 3.1 and np.isnan(df.B365H.iloc[1])
    assert parse_fixtures("Div,Date,HomeTeam,AwayTeam\nEC,29/09/2026,X,Y\n").empty
