"""Colores de los equipos (src/export/team_colors.py): recuadro del plantel y, si falta, equipación local (Wikipedia)."""

import json

import src.export.team_colors as tc
from src.export.team_colors import choose_colors, colors_from_navbox, normalize_color, parse_kit

ARSENAL_KIT = """{{Infobox football club
| pattern_b1 = _arsenal2627h
| leftarm1 = FFFFFF
| body1 = F00000
| shorts1 = FFFFFF
| socks1 = F00000
| body2 = 000000
}}"""
JUVENTUS_KIT = "| pattern_b1 = _juventus2627h\n| leftarm1 =\n| body1 =\n| shorts1 =\n| socks1 = "


def test_normalize_color_accepts_hex_and_css_names():
    assert normalize_color("#ee0107") == "#EE0107"
    assert normalize_color("ee0107") == "#EE0107"
    assert normalize_color("#fff") == "#FFFFFF"
    assert normalize_color("Gold ") == "#FFD700"
    assert normalize_color("white") == "#FFFFFF"
    assert normalize_color("{{Arsenal colour}}") is None
    assert normalize_color("") is None


def test_navbox_colors_give_primary_secondary_and_text():
    barca = "{{Navbox\n| bgcolor = #26559B\n| textcolor = Gold \n| bordercolor = #C32148\n}}"
    assert colors_from_navbox(barca) == {"primary": "#26559B", "secondary": "#C32148", "text": "#FFD700"}
    # borde igual al fondo (Liverpool): el secundario es el color del texto
    lfc = "| bgcolor = #D10A11 | textcolor = #FFFFFF | bordercolor = #D10A11"
    assert colors_from_navbox(lfc) == {"primary": "#D10A11", "secondary": "#FFFFFF", "text": "#FFFFFF"}
    assert colors_from_navbox("| bgcolor = {{x}}") is None


def test_parse_kit_reads_the_home_kit_only_as_hex():
    assert parse_kit(ARSENAL_KIT) == {"body": "#F00000", "shorts": "#FFFFFF", "socks": "#F00000", "arms": "#FFFFFF"}
    assert parse_kit(JUVENTUS_KIT) == {"body": None, "shorts": None, "socks": None, "arms": None}
    assert parse_kit("| body1 = red") == {"body": None, "shorts": None, "socks": None, "arms": None}


def test_kit_secondary_is_the_first_clearly_different_color():
    assert choose_colors({"body": "#F00000", "shorts": "#FFFFFF", "socks": "#F00000", "arms": "#FFFFFF"}) == \
        ("#F00000", "#FFFFFF")
    assert choose_colors({"body": "#05003B", "shorts": "#06013C", "socks": "#A50044", "arms": None}) == \
        ("#05003B", "#A50044")
    assert choose_colors({"body": "#05003B", "shorts": "#05003B", "socks": "#05003B", "arms": "#05003B"}) == \
        ("#05003B", None)
    assert choose_colors({"body": None, "shorts": None, "socks": None, "arms": None}) == (None, None)


def test_context_exposes_colors_and_overrides_win(tmp_path, monkeypatch):
    from src.export.league_context import LeagueContext
    table = {"leagues": {"ESP": {
        "Barcelona": {"primary": "#26559B", "secondary": None, "text": "#FFD700", "source": "https://x/b",
                      "origin": "plantel", "review": True},
        "Elche": {"primary": None, "secondary": None, "text": None, "source": None, "origin": None, "review": True},
        "Getafe": {"primary": "#005999", "secondary": "#FFFFFF", "text": "#FFFFFF", "source": "https://x/g",
                   "origin": "plantel", "review": False}}}}
    path = tmp_path / "colors.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    monkeypatch.setattr(tc, "COLORS_PATH", path)
    monkeypatch.setitem(tc.OVERRIDES, "ESP", {"Barcelona": {"primary": "#004D98", "secondary": "#A50044",
                                                            "text": "#FFFFFF", "source": "revisado a mano"}})
    tc._table.cache_clear()
    try:
        ctx = LeagueContext("ESP", None, None, None, 2005)
        assert ctx.colors_of("Getafe") == {"colors": {"primary": "#005999", "secondary": "#FFFFFF", "text": "#FFFFFF",
                                                      "source": "https://x/g"}}
        assert ctx.colors_of("Barcelona")["colors"]["secondary"] == "#A50044"
        assert ctx.colors_of("Elche") == {"colors": None}
    finally:
        tc._table.cache_clear()
