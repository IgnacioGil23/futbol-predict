import pandas as pd

from src.data.schedule import check_against_results, parse_schedule, to_argentina, to_canonical

SAMPLE = """= English Premier League 2026/27
# Date       Fri Aug 21 2026 - Sun May 30 2027 (282d)

▪ Matchday 1
  Fri Aug 21 2026
    20:00  Arsenal FC              v Coventry City FC         3-0 (2-0)
  Sat Aug 22
    15:00  Ipswich Town FC         v Sunderland AFC           2-1 (1-1)
           Brighton & Hove Albion FC v Aston Villa FC           4-0 (4-0)
           Leeds United FC         v Crystal Palace FC        0-0

▪ Matchday 20
  Wed Dec 30
    19:30  Chelsea FC              v AFC Bournemouth
  Sat Jan 2
    15:00  Nottingham Forest FC    v Manchester City FC
    ?? línea rara que no es un partido
"""


def test_parse_schedule_structure_and_names():
    df = parse_schedule(SAMPLE, 2026)
    assert len(df) == 6
    assert df.matchday.tolist() == [1, 1, 1, 1, 20, 20]
    assert df.home_team.tolist() == ["Arsenal", "Ipswich", "Brighton", "Leeds", "Chelsea", "Nott'm Forest"]
    assert df.away_team.tolist()[-2:] == ["Bournemouth", "Man City"]


def test_parse_schedule_scores_and_unplayed():
    df = parse_schedule(SAMPLE, 2026)
    assert df.loc[0, ["home_goals", "away_goals"]].tolist() == [3, 0]
    assert df.loc[3, ["home_goals", "away_goals"]].tolist() == [0, 0]      # 0-0 sin resultado al entretiempo
    assert df.played.tolist() == [True, True, True, True, False, False]


def test_parse_schedule_dates_cross_new_year_and_times_carry_over():
    df = parse_schedule(SAMPLE, 2026)
    assert df.date.tolist()[-2:] == [pd.Timestamp("2026-12-30"), pd.Timestamp("2027-01-02")]
    assert df.time_uk.tolist()[1:4] == ["15:00", "15:00", "15:00"]        # heredan el horario de la línea anterior


def test_argentina_time_follows_uk_daylight_saving():
    # Horario de verano británico (BST, UTC+1): 20:00 en Londres = 16:00 en Argentina (UTC-3)
    assert to_argentina(pd.Timestamp("2026-08-21"), "20:00") == "2026-08-21 16:00"
    # Horario de invierno (GMT, UTC+0): 15:00 en Londres = 12:00 en Argentina
    assert to_argentina(pd.Timestamp("2027-01-02"), "15:00") == "2027-01-02 12:00"
    assert to_argentina(pd.Timestamp("2027-01-02"), None) is None


def test_to_canonical_fallback_uses_display_names():
    assert to_canonical("Leicester City FC") == "Leicester"
    assert to_canonical("Wolverhampton Wanderers FC") == "Wolves"
    assert to_canonical("Everton FC") == "Everton"


def test_check_against_results_reports_mismatches():
    sched = parse_schedule(SAMPLE, 2026)
    results = pd.DataFrame({"home_team": ["Arsenal", "Ipswich", "Brighton"], "away_team": ["Coventry", "Sunderland", "Aston Villa"],
                            "home_goals": [3.0, 2.0, 3.0], "away_goals": [0.0, 1.0, 0.0]})
    report = check_against_results(sched, results)
    assert report["played_in_schedule"] == 4
    assert report["not_found_in_football_data"] == ["Leeds v Crystal Palace"]
    assert report["score_mismatches"] == ["Brighton v Aston Villa: 4-0 vs 3-0"]


# ------------------------------------------------------------------ otras ligas
SPAIN = """= Spain Primera División 2026/27

▪ Matchday 1
  Sat Aug 15 2026
    19:30  Deportivo Alavés        v Getafe CF                3-0 (0-0)
    21:30  Sevilla FC              v Rayo Vallecano de Madrid  2-1 (0-1)
  Sun Aug 16
    17:00  Club Atlético de Madrid v Sevilla FC
"""


def test_other_league_keeps_raw_names_and_uses_its_time_zone():
    from zoneinfo import ZoneInfo

    from src.data.schedule import parse_schedule
    df = parse_schedule(SPAIN, 2026, names={"Deportivo Alavés": "Alaves"}, tz=ZoneInfo("Europe/Madrid"))
    assert list(df.home_team) == ["Alaves", "Sevilla FC", "Club Atlético de Madrid"]
    assert list(df.home_raw) == ["Deportivo Alavés", "Sevilla FC", "Club Atlético de Madrid"]
    # 19:30 en Madrid (CEST, UTC+2) = 14:30 en Argentina (UTC-3)
    assert df.kickoff_ar.iloc[0] == "2026-08-15 14:30"


def test_names_are_inferred_from_played_results():
    from src.data.schedule import infer_names, parse_schedule
    schedule = parse_schedule(SPAIN, 2026, names={})
    results = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-15", "2026-08-15"]),
        "home_team": ["Alaves", "Sevilla"], "away_team": ["Getafe", "Vallecano"],
        "home_goals": [3.0, 2.0], "away_goals": [0.0, 1.0]})
    names = infer_names(schedule, results)
    assert names == {"Deportivo Alavés": "Alaves", "Getafe CF": "Getafe", "Sevilla FC": "Sevilla",
                     "Rayo Vallecano de Madrid": "Vallecano"}


def test_ambiguous_results_are_not_guessed():
    from src.data.schedule import infer_names, parse_schedule
    schedule = parse_schedule(SPAIN, 2026, names={})
    # dos partidos 3-0 ese día: no se puede saber cuál es cuál
    results = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-15", "2026-08-15"]),
        "home_team": ["Alaves", "Betis"], "away_team": ["Getafe", "Osasuna"],
        "home_goals": [3.0, 3.0], "away_goals": [0.0, 0.0]})
    assert "Deportivo Alavés" not in infer_names(schedule, results)


def test_matches_without_kickoff_time_have_no_argentina_time():
    from src.data.schedule import parse_schedule
    text = "▪ Matchday 9\n  Sat Oct 31 2026\n    Real Madrid C.F.  v  Valencia CF\n"
    df = parse_schedule(text, 2026, names={})
    assert len(df) == 1 and df.kickoff_ar.iloc[0] is None


def test_to_argentina_treats_missing_kickoff_as_none():
    assert to_argentina(pd.Timestamp("2026-10-31"), float("nan")) is None


def test_missing_kickoff_stays_none_in_a_full_schedule():
    from src.data.schedule import parse_schedule
    lines = ["▪ Matchday 1", "  Sat Aug 15 2026"]
    lines += [f"    {18 + i % 4}:00  Equipo {i}  v  Rival {i}" for i in range(60)]
    lines += ["  Sun Aug 16", "    Equipo X  v  Rival X"]
    df = parse_schedule("\n".join(lines), 2026, names={})
    assert df.kickoff_ar.iloc[-1] is None and df.time_uk.iloc[-1] is None
