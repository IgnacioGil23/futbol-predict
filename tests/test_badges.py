"""Identificación visual de los equipos: iniciales únicas (los escudos salen de Wikimedia Commons, league_media.py)."""

import json

import src.export.badges as badges
import src.export.league_media as media
from src.export.badges import SHORT_NAMES, badge
from src.export.league_context import LeagueContext


def test_badge_module_only_gives_initials_never_official_images():
    assert badge("Arsenal") == {"badge": None, "short": "ARS"}
    assert badge("Bolton") == {"badge": None, "short": "BOL"}
    assert not hasattr(badges, "BADGE_URL")          # los escudos de premierleague.com no tienen permiso de uso


def test_short_names_are_unique():
    teams = ["Birmingham", "Blackburn", "Blackpool", "Bolton", "Bradford", "Cardiff", "Charlton", "Derby",
             "Huddersfield", "Middlesbrough", "Portsmouth", "QPR", "Reading", "Stoke", "Swansea", "Wigan",
             *SHORT_NAMES]
    shorts = [badge(t)["short"] for t in set(teams)]
    assert len(shorts) == len(set(shorts))


def test_premier_crests_come_from_commons(tmp_path, monkeypatch):
    table = {"leagues": {"ENG": {"Arsenal": {"crest": {"file": "Arsenal FC.svg", "width": 500, "height": 600,
                                                        "author": "X", "license": "Public domain", "license_url": ""},
                                              "stadium": None}}}}
    path = tmp_path / "media.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    monkeypatch.setattr(media, "MEDIA_PATH", path)
    media._media.cache_clear()
    try:
        ctx = LeagueContext("ENG", None, None, None, 2004)
        b = ctx.badge_of("Arsenal")
        assert b["badge"].startswith("https://upload.wikimedia.org/") and b["short"] == "ARS"
        assert ctx.badge_of("Bolton") == {"badge": None, "badge_credit": None, "short": "BOL"}
    finally:
        media._media.cache_clear()
