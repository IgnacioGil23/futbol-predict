"""Ligas en vivo: datos de la temporada en curso, ids estables y metadatos de cada liga."""

import pandas as pd

from src.data.leagues import LEAGUES, PRODUCT_LEAGUES, assign_match_ids


def test_match_ids_do_not_depend_on_row_order():
    base = pd.DataFrame({"division": ["SP1", "SP1", "SP2"], "season_start": [2024, 2024, 2024],
                         "date": pd.to_datetime(["2024-08-16", "2024-08-17", "2024-08-17"]),
                         "home_team": ["Ath Bilbao", "Sociedad", "M'gladbach"],
                         "away_team": ["Getafe", "Vallecano", "Real Madrid"]})
    ids = assign_match_ids(base, "ESP")
    assert list(ids) == ["ESP-SP1-2024-20240816-AthBilbao-Getafe", "ESP-SP1-2024-20240817-Sociedad-Vallecano",
                         "ESP-SP2-2024-20240817-Mgladbach-RealMadrid"]
    # un partido postergado que aparece en el medio no cambia los ids de los demás
    grown = pd.concat([base.iloc[:1], base.iloc[1:]], ignore_index=True).iloc[::-1].reset_index(drop=True)
    assert set(assign_match_ids(grown, "ESP")) == set(ids)


def test_every_product_league_has_what_the_site_needs():
    assert list(PRODUCT_LEAGUES)[0] == "ENG" and set(LEAGUES) <= set(PRODUCT_LEAGUES)
    slugs = [lg["slug"] for lg in PRODUCT_LEAGUES.values()]
    assert len(set(slugs)) == len(slugs)
    for lg in PRODUCT_LEAGUES.values():
        assert {"competition", "slug", "top", "second", "timezone", "schedule_url", "relegation"} <= set(lg)
        assert "{season}" in lg["schedule_url"]


def test_merge_names_keeps_saved_translations():
    from src.data.team_names import merge_names
    assert merge_names({"Sevilla FC": "Sevilla"}, {"Getafe CF": "Getafe"}) == {"Getafe CF": "Getafe",
                                                                               "Sevilla FC": "Sevilla"}
    assert merge_names({"X": "A"}, {"X": "B"}) == {"X": "B"}


def test_simulation_model_trains_from_the_same_season_as_its_validation():
    from src.models.season_eval import SIM_TRAIN_START
    from src.serving.league_models import train_start
    assert train_start("ESP", "elo") == SIM_TRAIN_START == 2002
    assert train_start("ESP", "odds_elo") == 2005 and train_start("ITA", "odds_elo") == 2006
