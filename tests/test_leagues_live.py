"""Ligas en vivo: datos de la temporada en curso, ids estables y metadatos de cada liga."""

import pandas as pd

from src.data.leagues import LEAGUES, PRODUCT_LEAGUES, assign_match_ids


def test_match_ids_are_stable_when_a_season_is_added():
    base = pd.DataFrame({"division": ["SP1", "SP1", "SP2"], "season_start": [2024, 2024, 2024]})
    grown = pd.concat([base.iloc[:2], pd.DataFrame({"division": ["SP1"], "season_start": [2025]}), base.iloc[2:]],
                      ignore_index=True)
    ids_base = assign_match_ids(base, "ESP")
    ids_grown = assign_match_ids(grown, "ESP")
    assert list(ids_base) == ["ESP-SP1-2024-0000", "ESP-SP1-2024-0001", "ESP-SP2-2024-0000"]
    assert set(ids_base) <= set(ids_grown) and "ESP-SP1-2025-0000" in set(ids_grown)


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
