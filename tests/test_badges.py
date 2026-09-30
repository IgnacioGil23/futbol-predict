"""Identificación visual de los equipos: escudo con código verificado o iniciales únicas."""

from src.export.badges import BADGE_CODES, SHORT_NAMES, badge


def test_known_team_gets_its_official_badge_and_short_name():
    assert badge("Arsenal") == {"badge": "https://resources.premierleague.com/premierleague/badges/70/t3.png",
                                "short": "ARS"}
    assert badge("Watford")["badge"].endswith("/t57.png")


def test_team_without_verified_code_gets_initials_only():
    assert badge("Bolton") == {"badge": None, "short": "BOL"}


def test_codes_and_short_names_are_unique():
    assert len(set(BADGE_CODES.values())) == len(BADGE_CODES)
    teams = ["Birmingham", "Blackburn", "Blackpool", "Bolton", "Bradford", "Cardiff", "Charlton", "Derby",
             "Huddersfield", "Middlesbrough", "Portsmouth", "QPR", "Reading", "Stoke", "Swansea", "Wigan",
             *SHORT_NAMES]
    shorts = [badge(t)["short"] for t in set(teams)]
    assert len(shorts) == len(set(shorts))
