"""Escudos y fotos de las otras ligas (src/export/league_media.py)."""

import json

import src.export.league_media as media


def test_free_licenses_only():
    for ok in ("CC BY-SA 4.0", "CC BY 2.0 de", "CC BY-SA 3.0 de", "CC0", "Public domain"):
        assert media.FREE_LICENSE.match(ok), ok
    for bad in ("Fair use", "Non-free", "CC BY-NC 4.0", ""):
        assert not media.FREE_LICENSE.match(bad), bad


def test_svg_crests_are_served_as_png_thumbnails_and_small_photos_as_originals():
    svg = media.image_url("FC Barcelona (crest).svg", 600, 140)
    assert svg.endswith("/140px-FC_Barcelona_%28crest%29.svg.png") and "/thumb/" in svg
    assert "/thumb/" not in media.image_url("small.jpg", 800, 960)
    assert media.image_url("big.jpg", 4000, 960).endswith("/960px-big.jpg")


def test_crest_credit_only_when_the_license_asks_for_it(tmp_path, monkeypatch):
    table = {"leagues": {"ESP": {
        "Barcelona": {"crest": {"file": "a.svg", "width": 500, "height": 500, "author": "X", "license": "CC0",
                                "license_url": ""}, "stadium": None},
        "Getafe": {"crest": {"file": "b.svg", "width": 500, "height": 500, "author": "Y", "license": "CC BY-SA 4.0",
                             "license_url": "https://creativecommons.org/licenses/by-sa/4.0"}, "stadium": None},
        "Elche": {"crest": None, "stadium": None}}}}
    path = tmp_path / "media.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    monkeypatch.setattr(media, "MEDIA_PATH", path)
    media._media.cache_clear()
    try:
        url, credit = media.league_crest("Barcelona", "ESP")
        assert url and credit is None
        url, credit = media.league_crest("Getafe", "ESP")
        assert url and credit["author"] == "Y" and credit["license"] == "CC BY-SA 4.0"
        assert media.league_crest("Elche", "ESP") == (None, None)
        assert media.league_stadium("Elche", "ESP") == {"stadium": None}
    finally:
        media._media.cache_clear()


def test_excluded_crests_are_not_used(tmp_path, monkeypatch):
    table = {"leagues": {"FRA": {"Strasbourg": {"crest": {"file": "partido.jpg", "width": 4000, "height": 3000,
                                                          "author": "X", "license": "CC BY-SA 4.0", "license_url": ""},
                                                "stadium": None}}}}
    path = tmp_path / "media.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    monkeypatch.setattr(media, "MEDIA_PATH", path)
    media._media.cache_clear()
    try:
        assert "Strasbourg" in media.CREST_EXCLUDE["FRA"]
        assert media.league_crest("Strasbourg", "FRA") == (None, None)
    finally:
        media._media.cache_clear()


def test_crest_thumbnails_use_a_standard_wikimedia_width():
    assert media.CREST_WIDTH in (20, 40, 60, 120, 250, 330, 500, 960)
