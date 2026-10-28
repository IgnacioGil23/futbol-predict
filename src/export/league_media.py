"""Escudos y fotos de estadio de los clubes de LaLiga, Serie A, Bundesliga y Ligue 1 (la Premier: badges.py y
stadiums.py).

Mismo criterio que la Premier, a partir del artículo de cada club en la Wikipedia en inglés (CLUB_ARTICLES):
* Estadio: el campo "stadium" (o "ground") de la ficha del club; foto: la imagen principal del artículo del estadio,
  alojada en Wikimedia Commons.
* Escudo: el logo del club en Wikidata (propiedad P154), alojado en Wikimedia Commons. Los escudos son marcas
  registradas de cada club; se muestran solo como referencia visual.
* Solo se usan archivos con licencia libre (Creative Commons, CC0 o dominio público). Las licencias que exigen citar
  autor (CC BY, CC BY-SA) se citan en la ficha de cada equipo. Un club sin foto o sin escudo libre se muestra sin foto
  o con sus iniciales. Los archivos se enlazan en miniatura desde los servidores de Wikimedia, sin copiarlos.

La tabla generada (configs/leagues/media.json, con la fecha de verificación) es la que usa la web:
    python -m src.export.league_media --build     # vuelve a consultar Wikipedia, Wikidata y Commons
    python -m src.export.league_media             # verifica que los archivos y sus licencias no cambiaron
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from functools import lru_cache
from urllib.parse import quote

import requests

from src.config import PROJECT_ROOT

MEDIA_PATH = PROJECT_ROOT / "configs" / "leagues" / "media.json"
COMMONS = "https://upload.wikimedia.org/wikipedia/commons"
PHOTO_WIDTH = 960
CREST_WIDTH = 120          # Wikimedia solo sirve miniaturas en anchos estándar (140 da error 400)
UA = {"User-Agent": "futbol-predict/1.0 (https://github.com/IgnacioGil23/futbol-predict)"}
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
FREE_LICENSE = re.compile(r"^(CC BY(-SA)? [\d.]+( [a-z]{2})?|CC0|Public domain)$", re.I)

# Logos de Wikidata que no son el escudo actual del club (revisados a mano el 28/10/2026): no se usan.
CREST_EXCLUDE: dict[str, dict[str, str]] = {
    "FRA": {"Strasbourg": "es una foto de un partido", "Brest": "es el escudo anterior a 1985",
            "Rennes": "es el escudo de 1960"},
    "GER": {"RB Leipzig": "es una foto de un partido"},
    "ITA": {"Roma": "es solo el logotipo de texto, no el escudo"},
}

# Artículo del club en la Wikipedia en inglés (nombre canónico de Football-Data -> título), revisado a mano.
CLUB_ARTICLES: dict[str, dict[str, str]] = {
    "ESP": {
        "Alaves": "Deportivo Alavés",
        "Ath Bilbao": "Athletic Bilbao",
        "Ath Madrid": "Atlético Madrid",
        "Barcelona": "FC Barcelona",
        "Betis": "Real Betis",
        "Celta": "RC Celta de Vigo",
        "Elche": "Elche CF",
        "Espanol": "RCD Espanyol",
        "Getafe": "Getafe CF",
        "La Coruna": "Deportivo de A Coruña",
        "Levante": "Levante UD",
        "Malaga": "Málaga CF",
        "Osasuna": "CA Osasuna",
        "Real Madrid": "Real Madrid CF",
        "Santander": "Racing de Santander",
        "Sevilla": "Sevilla FC",
        "Sociedad": "Real Sociedad",
        "Valencia": "Valencia CF",
        "Vallecano": "Rayo Vallecano",
        "Villarreal": "Villarreal CF",
    },
    "ITA": {
        "Atalanta": "Atalanta BC",
        "Bologna": "Bologna FC 1909",
        "Cagliari": "Cagliari Calcio",
        "Como": "Como 1907",
        "Fiorentina": "ACF Fiorentina",
        "Frosinone": "Frosinone Calcio",
        "Genoa": "Genoa CFC",
        "Inter": "Inter Milan",
        "Juventus": "Juventus FC",
        "Lazio": "SS Lazio",
        "Lecce": "US Lecce",
        "Milan": "AC Milan",
        "Monza": "AC Monza",
        "Napoli": "SSC Napoli",
        "Parma": "Parma Calcio 1913",
        "Roma": "AS Roma",
        "Sassuolo": "US Sassuolo Calcio",
        "Torino": "Torino FC",
        "Udinese": "Udinese Calcio",
        "Venezia": "Venezia FC",
    },
    "GER": {
        "Augsburg": "FC Augsburg",
        "Bayern Munich": "FC Bayern Munich",
        "Dortmund": "Borussia Dortmund",
        "Ein Frankfurt": "Eintracht Frankfurt",
        "Elversberg": "SV Elversberg",
        "FC Koln": "1. FC Köln",
        "Freiburg": "SC Freiburg",
        "Hamburg": "Hamburger SV",
        "Hoffenheim": "TSG 1899 Hoffenheim",
        "Leverkusen": "Bayer 04 Leverkusen",
        "M'gladbach": "Borussia Mönchengladbach",
        "Mainz": "1. FSV Mainz 05",
        "Paderborn": "SC Paderborn 07",
        "RB Leipzig": "RB Leipzig",
        "Schalke 04": "FC Schalke 04",
        "Stuttgart": "VfB Stuttgart",
        "Union Berlin": "1. FC Union Berlin",
        "Werder Bremen": "SV Werder Bremen",
    },
    "FRA": {
        "Angers": "Angers SCO",
        "Auxerre": "AJ Auxerre",
        "Brest": "Stade Brestois 29",
        "Le Havre": "Le Havre AC",
        "Le Mans": "Le Mans FC",
        "Lens": "RC Lens",
        "Lille": "Lille OSC",
        "Lorient": "FC Lorient",
        "Lyon": "Olympique Lyonnais",
        "Marseille": "Olympique de Marseille",
        "Monaco": "AS Monaco FC",
        "Nice": "OGC Nice",
        "Paris FC": "Paris FC",
        "Paris SG": "Paris Saint-Germain FC",
        "Rennes": "Stade Rennais FC",
        "Strasbourg": "RC Strasbourg Alsace",
        "Toulouse": "Toulouse FC",
        "Troyes": "ES Troyes AC",
    },
}


def _get(url: str, **params) -> dict:
    r = requests.get(url, headers=UA, timeout=30, params={"format": "json", "formatversion": 2, **params})
    r.raise_for_status()
    return r.json()


def commons_file(file: str) -> dict | None:
    """Tamaño, autor y licencia de un archivo de Commons; None si no está en Commons o su licencia no es libre."""
    page = _get(COMMONS_API, action="query", prop="imageinfo", iiprop="extmetadata|size", titles=f"File:{file}")
    page = page["query"]["pages"][0]
    if "imageinfo" not in page:
        return None
    info = page["imageinfo"][0]
    md = info["extmetadata"]
    text = lambda key: re.sub(r"<[^>]+>", "", md.get(key, {}).get("value", "")).strip()  # noqa: E731
    license = text("LicenseShortName")
    if not FREE_LICENSE.match(license):
        return None
    return {"file": file, "width": info["width"], "height": info["height"], "author": text("Artist") or "Desconocido",
            "license": license, "license_url": text("LicenseUrl")}


def _club_media(article: str) -> dict:
    page = _get(WIKIPEDIA_API, action="query", prop="revisions|pageprops", rvprop="content", rvslots="main",
                titles=article, redirects=1)["query"]["pages"][0]
    text = page["revisions"][0]["slots"]["main"]["content"]
    out: dict = {"article": page["title"], "stadium": None, "crest": None}
    m = re.search(r"\|\s*(?:stadium|ground)\s*=\s*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", text)
    if m:
        stadium_article = m.group(1).strip()
        img = _get(WIKIPEDIA_API, action="query", prop="pageimages", piprop="name", titles=stadium_article,
                   redirects=1)["query"]["pages"][0]
        photo = commons_file(img["pageimage"]) if img.get("pageimage") else None
        if photo:
            out["stadium"] = {"name": (m.group(2) or m.group(1)).strip(), "article": img["title"], **photo}
    qid = page.get("pageprops", {}).get("wikibase_item")
    if qid:
        claims = _get(WIKIDATA_API, action="wbgetclaims", entity=qid, property="P154").get("claims", {}).get("P154", [])
        claims = sorted(claims, key=lambda c: c.get("rank") != "preferred")          # el preferido, si lo hay
        logo = claims[0]["mainsnak"].get("datavalue", {}).get("value") if claims else None
        out["crest"] = commons_file(logo) if logo else None
    return out


def build() -> dict:
    table = {"verified_on": date.today().isoformat(), "leagues": {}}
    for code, clubs in CLUB_ARTICLES.items():
        table["leagues"][code] = {team: _club_media(article) for team, article in clubs.items()}
    MEDIA_PATH.write_text(json.dumps(table, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    _media.cache_clear()
    return table


@lru_cache(maxsize=1)
def _media() -> dict:
    return json.loads(MEDIA_PATH.read_text(encoding="utf-8")) if MEDIA_PATH.exists() else {"leagues": {}}


def image_url(file: str, width: int, thumb: int) -> str:
    """Miniatura de Commons de `thumb` px de ancho (el original si ya es más angosto; los SVG, en PNG)."""
    h = hashlib.md5(file.replace(" ", "_").encode("utf-8")).hexdigest()
    name = quote(file.replace(" ", "_"))
    base = f"{COMMONS}/{h[0]}/{h[:2]}/{name}"
    if file.lower().endswith(".svg"):
        return f"{COMMONS}/thumb/{h[0]}/{h[:2]}/{name}/{thumb}px-{name}.png"
    return base if width <= thumb else f"{COMMONS}/thumb/{h[0]}/{h[:2]}/{name}/{thumb}px-{name}"


def _credit(f: dict) -> dict:
    return {"author": f["author"], "license": f["license"], "license_url": f["license_url"],
            "source": f"https://commons.wikimedia.org/wiki/File:{quote(f['file'].replace(' ', '_'))}"}


def league_stadium(team: str, code: str) -> dict:
    """{"stadium": ... o None}, con la misma forma que src.export.stadiums.stadium."""
    s = (_media()["leagues"].get(code, {}).get(team) or {}).get("stadium")
    if not s:
        return {"stadium": None}
    return {"stadium": {"name": s["name"], "image": image_url(s["file"], s["width"], PHOTO_WIDTH), "credit": _credit(s),
                        "wikipedia": f"https://en.wikipedia.org/wiki/{quote(s['article'].replace(' ', '_'))}"}}


def league_crest(team: str, code: str) -> tuple[str | None, dict | None]:
    """(URL del escudo, crédito si la licencia exige citar autor) o (None, None)."""
    c = (_media()["leagues"].get(code, {}).get(team) or {}).get("crest")
    if not c or team in CREST_EXCLUDE.get(code, {}):
        return None, None
    needs_credit = not re.match(r"^(CC0|Public domain)$", c["license"], re.I)
    return image_url(c["file"], c["width"], CREST_WIDTH), (_credit(c) if needs_credit else None)


def verify() -> list[str]:
    """Vuelve a consultar Commons: cada archivo existe, con la licencia registrada, y su miniatura carga."""
    problems = []
    for code, clubs in _media()["leagues"].items():
        for team, m in clubs.items():
            for kind, thumb in (("stadium", PHOTO_WIDTH), ("crest", CREST_WIDTH)):
                f = m.get(kind)
                if not f or (kind == "crest" and team in CREST_EXCLUDE.get(code, {})):
                    continue
                now = commons_file(f["file"])
                if now is None or now["license"] != f["license"]:
                    problems.append(f"{code} {team}: cambió la licencia o no existe {f['file']}")
                elif requests.head(image_url(f["file"], f["width"], thumb), headers=UA, timeout=30,
                                   allow_redirects=True).status_code != 200:
                    problems.append(f"{code} {team}: la miniatura de {f['file']} no carga")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build", action="store_true", help="regenerar la tabla desde Wikipedia/Wikidata/Commons")
    args = parser.parse_args()
    if args.build:
        table = build()
        for code, clubs in table["leagues"].items():
            crests = sum(bool(m["crest"]) and team not in CREST_EXCLUDE.get(code, {}) for team, m in clubs.items())
            print(f"{code}: {sum(bool(m['stadium']) for m in clubs.values())}/{len(clubs)} fotos, "
                  f"{crests}/{len(clubs)} escudos")
        return
    found = verify()
    print("\n".join(found) or "Fotos y escudos siguen verificados.")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
