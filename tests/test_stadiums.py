"""Estadios de la web: URL de Commons bien armada, crédito completo y un estadio por club actual."""

from src.export.stadiums import STADIUMS, stadium


def test_thumbnail_url_follows_the_commons_md5_layout():
    # Ruta devuelta por la API de Commons para este archivo (imageinfo con iiurlwidth=960, 30/09/2026).
    assert stadium("Arsenal")["stadium"]["image"] == (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/2/29/London_Emirates_Stadium_arsenal.jpg/"
        "960px-London_Emirates_Stadium_arsenal.jpg")
    # Los caracteres especiales van codificados, igual que en la API.
    assert "Portman_Road_aerial_%28cropped%29.jpg/960px-Portman_Road_aerial_%28cropped%29.jpg" in \
        stadium("Ipswich")["stadium"]["image"]


def test_narrow_originals_are_linked_without_upscaling():
    assert stadium("Fulham")["stadium"]["image"] == (
        "https://upload.wikimedia.org/wikipedia/commons/a/af/Craven_Cottage_-_geograph.org.uk_-_7559163.jpg")


def test_every_photo_carries_author_and_creative_commons_license():
    for team in STADIUMS:
        credit = stadium(team)["stadium"]["credit"]
        assert credit["author"] and credit["license"].startswith("CC BY")
        assert credit["license_url"].startswith("https://creativecommons.org/licenses/by")
        assert credit["source"].startswith("https://commons.wikimedia.org/wiki/File:")


def test_one_stadium_per_club_and_none_for_unknown_teams():
    assert len({s.name for s in STADIUMS.values()}) == len(STADIUMS) == 20
    assert stadium("Bolton") == {"stadium": None}
