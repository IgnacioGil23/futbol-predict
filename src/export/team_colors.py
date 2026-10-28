"""Colores de cada club (para diseños de la web: tarjetas de partido, escudos genéricos, etc.).

Fuentes, en este orden, desde la Wikipedia en inglés (mismos artículos que los escudos, league_media.py):
1. El recuadro del plantel del club ("Template:<club> squad"): sus colores de fondo, texto y borde (bgcolor, textcolor,
   bordercolor) son los colores con los que Wikipedia identifica al club. Principal: el fondo. Secundario: el borde o,
   si se confunde con el fondo, el texto. Texto: el color legible sobre el principal.
2. Si no hay recuadro, la equipación local de la ficha del club (body1, shorts1, socks1, leftarm1). En camisetas a
   rayas el dibujo está en una imagen y puede faltar un color.

Son los tonos que usan los editores de Wikipedia, no una guía de marca oficial (los clubes no publican las suyas).
Los clubes sin dos colores quedan marcados con "review", para completarlos a mano en OVERRIDES citando la fuente.
Los nombres de color CSS ("Gold", "white") se convierten con la tabla estándar de CSS (148 nombres).

    python -m src.export.team_colors --build                  # regenera configs/team_colors.json
    python -m src.export.team_colors --build --leagues ENG    # solo una liga (las demás quedan como estaban)
"""

import argparse
import json
import re
from datetime import date
from functools import lru_cache
from urllib.parse import quote

from src.config import PROJECT_ROOT
from src.export.league_media import CLUB_ARTICLES, WIKIPEDIA_API, _get

COLORS_PATH = PROJECT_ROOT / "configs" / "team_colors.json"
KIT_FIELDS = {"body": "body1", "shorts": "shorts1", "socks": "socks1", "arms": "leftarm1"}
MIN_DISTANCE = 60          # distancia RGB (0-441) a partir de la cual dos colores se consideran distintos
# Correcciones revisadas a mano: {liga: {equipo: {"primary", "secondary", "text", "source"}}}.
OVERRIDES: dict[str, dict[str, dict]] = {}


def normalize_color(value: str) -> str | None:
    """'#RRGGBB' desde un hexadecimal (#RGB, #RRGGBB, con o sin #) o un nombre de color CSS; None si no es un color."""
    v = value.strip().lower()
    if re.fullmatch(r"#?[0-9a-f]{6}", v):
        return "#" + v.lstrip("#").upper()
    if re.fullmatch(r"#?[0-9a-f]{3}", v):
        return "#" + "".join(c * 2 for c in v.lstrip("#")).upper()
    from matplotlib.colors import CSS4_COLORS  # tabla estándar de nombres CSS (solo al generar la tabla)
    return CSS4_COLORS.get(v)


def _distance(a: str, b: str) -> float:
    ra, rb = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (a, b))
    return sum((x - y) ** 2 for x, y in zip(ra, rb)) ** 0.5


def _field(wikitext: str, name: str) -> str | None:
    m = re.search(rf"\|\s*{name}\s*=\s*([^|\n}}]*)", wikitext)
    return normalize_color(m.group(1)) if m and m.group(1).strip() else None


def colors_from_navbox(wikitext: str) -> dict | None:
    """{"primary", "secondary", "text"} del recuadro del plantel, o None si su fondo no es un color."""
    bg, text, border = (_field(wikitext, f) for f in ("bgcolor", "textcolor", "bordercolor"))
    if bg is None:
        return None
    secondary = next((c for c in (border, text) if c and _distance(c, bg) >= MIN_DISTANCE), None)
    return {"primary": bg, "secondary": secondary, "text": text}


def parse_kit(wikitext: str) -> dict[str, str | None]:
    """Colores de la equipación local de la ficha; None en los campos vacíos o que no son un hexadecimal."""
    out = {}
    for key, field in KIT_FIELDS.items():
        m = re.search(rf"\|\s*{field}\s*=\s*#?([0-9A-Fa-f]{{6}})\s*(?:\||\n|$|<!--)", wikitext)
        out[key] = f"#{m.group(1).upper()}" if m else None
    return out


def choose_colors(kit: dict[str, str | None]) -> tuple[str | None, str | None]:
    """(principal, secundario) de la equipación: la camiseta y el primer color claramente distinto."""
    primary = kit["body"]
    if primary is None:
        return None, None
    return primary, next((kit[k] for k in ("shorts", "socks", "arms")
                          if kit[k] and _distance(kit[k], primary) >= MIN_DISTANCE), None)


def _wikitext(title: str) -> tuple[str, str] | None:
    page = _get(WIKIPEDIA_API, action="query", prop="revisions", rvprop="content", rvslots="main", titles=title,
                redirects=1)["query"]["pages"][0]
    if "revisions" not in page:
        return None
    return page["title"], page["revisions"][0]["slots"]["main"]["content"]


def _url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))


def _club_colors(article: str) -> dict:
    navbox = _wikitext(f"Template:{article} squad")
    found = colors_from_navbox(navbox[1]) if navbox else None
    if found:
        out = {**found, "source": _url(navbox[0]), "origin": "plantel"}
    else:
        page = _wikitext(article)
        primary, secondary = choose_colors(parse_kit(page[1])) if page else (None, None)
        out = {"primary": primary, "secondary": secondary, "text": None,
               "source": _url(page[0]) if page and primary else None, "origin": "equipación" if primary else None}
    out["review"] = out["primary"] is None or out["secondary"] is None
    return out


def build(codes: list[str] | None = None) -> dict:
    table = json.loads(COLORS_PATH.read_text(encoding="utf-8")) if COLORS_PATH.exists() else {"leagues": {}}
    for code in codes or list(CLUB_ARTICLES):
        table["leagues"][code] = {team: _club_colors(article) for team, article in CLUB_ARTICLES[code].items()}
    table["source"] = ("Wikipedia en inglés: recuadro del plantel de cada club (bgcolor/textcolor/bordercolor) o, si "
                       "falta, la equipación local de su ficha")
    table["verified_on"] = date.today().isoformat()
    COLORS_PATH.write_text(json.dumps(table, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    _table.cache_clear()
    return table


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads(COLORS_PATH.read_text(encoding="utf-8")) if COLORS_PATH.exists() else {"leagues": {}}


def team_colors(team: str, code: str) -> dict | None:
    """{"primary", "secondary" (o None), "text" (o None), "source"} del club, o None si no hay colores."""
    if team in OVERRIDES.get(code, {}):
        return dict(OVERRIDES[code][team])
    c = _table()["leagues"].get(code, {}).get(team)
    if not c or c["primary"] is None:
        return None
    return {"primary": c["primary"], "secondary": c["secondary"], "text": c["text"], "source": c["source"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build", action="store_true", help="regenerar la tabla desde Wikipedia")
    parser.add_argument("--leagues", nargs="*", default=None, help="solo estas ligas (por defecto, todas)")
    args = parser.parse_args()
    table = build(args.leagues) if args.build else _table()
    for code, clubs in table["leagues"].items():
        review = sorted(t for t, c in clubs.items() if c["review"] and t not in OVERRIDES.get(code, {}))
        print(f"{code}: {len(clubs) - len(review)}/{len(clubs)} con dos colores · revisar: {review}")


if __name__ == "__main__":
    main()
