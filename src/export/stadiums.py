"""Estadio de cada club de la Premier 2026-27 y su foto, para las fichas de equipo de la web.

* Estadio: el campo "ground" de la ficha (infobox) del artículo del club en la Wikipedia en inglés. No se usa Wikidata
  porque tiene datos viejos (por ejemplo, ubica a Brentford en Griffin Park, que el club dejó en 2020).
* Foto: la imagen principal del artículo del estadio, alojada en Wikimedia Commons. Todas tienen licencia Creative
  Commons (CC BY o CC BY-SA), que exige citar autor y licencia: la web los muestra junto a cada foto y en "Cómo
  funciona". Las fotos se enlazan en miniatura (960 px de ancho) desde los servidores de Wikimedia, sin copiarlas.
* Verificado el 30/09/2026 con las APIs de Wikipedia y Commons (estadio, archivo, tamaño, autor y licencia). Para
  volver a verificar: ``python -m src.export.stadiums``.

Los equipos que no figuran (clubes que no juegan la Premier 2026-27) no tienen foto; la web no la muestra.
"""

import hashlib
import sys
from dataclasses import dataclass
from urllib.parse import quote

import requests

COMMONS = "https://upload.wikimedia.org/wikipedia/commons"
THUMB_WIDTH = 960
VERIFIED_ON = "2026-09-30"


@dataclass(frozen=True)
class Stadium:
    name: str        # como lo nombra la ficha del club en Wikipedia
    article: str     # artículo del estadio en la Wikipedia en inglés
    file: str        # archivo en Wikimedia Commons (foto principal del artículo)
    width: int
    height: int
    author: str
    license: str
    license_url: str


STADIUMS: dict[str, Stadium] = {
    "Arsenal": Stadium("Emirates Stadium", "Emirates Stadium",
        "London_Emirates_Stadium_arsenal.jpg", 4241, 3176,
        "Arne Müseler", "CC BY-SA 3.0 de", "https://creativecommons.org/licenses/by-sa/3.0/de/deed.en"),
    "Aston Villa": Stadium("Villa Park", "Villa Park",
        "Birmingham_aston_villa_park_stadium.jpg", 4631, 3468,
        "Arne Müseler", "CC BY-SA 3.0 de", "https://creativecommons.org/licenses/by-sa/3.0/de/deed.en"),
    "Bournemouth": Stadium("Dean Court", "Dean Court",
        "Deancourt_14092013_vblackpool.jpg", 7915, 2456,
        "Matthew Jackson", "CC BY-SA 3.0", "https://creativecommons.org/licenses/by-sa/3.0"),
    "Brentford": Stadium("Brentford Community Stadium", "Brentford Community Stadium",
        "Brentford_Community_Stadium_2020.jpg", 4000, 2660,
        "AndyScott", "CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0"),
    "Brighton": Stadium("Falmer Stadium", "Falmer Stadium",
        "Amex_Community_Stadium.jpg", 3008, 2000,
        "Barbara van Cleve", "CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0"),
    "Chelsea": Stadium("Stamford Bridge", "Stamford Bridge (stadium)",
        "London_Stamford_Bridge.jpg", 4316, 3232,
        "Arne Müseler", "CC BY-SA 3.0 de", "https://creativecommons.org/licenses/by-sa/3.0/de/deed.en"),
    "Coventry": Stadium("Coventry Building Society Arena", "Coventry Building Society Arena",
        "Coventry_Derby_October_2021_-_2.jpg", 4032, 1960,
        "Amakuru", "CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0"),
    "Crystal Palace": Stadium("Selhurst Park", "Selhurst Park",
        "2023_09_09_arne_mueseler_17_18_07_00743-Verbessert-RR_(53283239217).jpg", 5075, 3800,
        "Arne Müseler", "CC BY-SA 2.0", "https://creativecommons.org/licenses/by-sa/2.0"),
    "Everton": Stadium("Hill Dickinson Stadium", "Hill Dickinson Stadium",
        "Hill_Dickinson_Stadium,_Liverpool_Waterfront_-_geograph.org.uk_-_8170881.jpg", 1024, 768,
        "David Dixon", "CC BY-SA 2.0", "https://creativecommons.org/licenses/by-sa/2.0"),
    "Fulham": Stadium("Craven Cottage", "Craven Cottage",
        "Craven_Cottage_-_geograph.org.uk_-_7559163.jpg", 640, 296,
        "Elliot Smith", "CC BY-SA 2.0", "https://creativecommons.org/licenses/by-sa/2.0"),
    "Hull": Stadium("MKM Stadium", "MKM Stadium",
        "Match_day_at_the_KC_Stadium_-_geograph.org.uk_-_1497910.jpg", 640, 480,
        "David Brown", "CC BY-SA 2.0", "https://creativecommons.org/licenses/by-sa/2.0"),
    "Ipswich": Stadium("Portman Road", "Portman Road",
        "Portman_Road_aerial_(cropped).jpg", 3525, 2234,
        "John Fielding", "CC BY 2.0", "https://creativecommons.org/licenses/by/2.0"),
    "Leeds": Stadium("Elland Road", "Elland Road",
        "Leeds_United_-_31559864360.jpg", 4032, 3024,
        "chillilogic.com", "CC BY 2.0", "https://creativecommons.org/licenses/by/2.0"),
    "Liverpool": Stadium("Anfield", "Anfield",
        "Liverpool_anfield_road_stadium.jpg", 4595, 3441,
        "Arne Müseler", "CC BY-SA 3.0 de", "https://creativecommons.org/licenses/by-sa/3.0/de/deed.en"),
    "Man City": Stadium("Etihad Stadium", "Etihad Stadium",
        "City_of_Manchester_Stadium_2023_cropped.jpg", 4500, 3000,
        "Arne Müseler (recorte: Blackcat)", "CC BY-SA 3.0 de", "https://creativecommons.org/licenses/by-sa/3.0/de/deed.en"),
    "Man United": Stadium("Old Trafford", "Old Trafford",
        "2023_07_31_arne_mueseler_00060-Verbessert-RR_(53106651455).jpg", 4995, 3741,
        "Arne Müseler", "CC BY-SA 2.0", "https://creativecommons.org/licenses/by-sa/2.0"),
    "Newcastle": Stadium("St James' Park", "St James' Park",
        "Newcastle_st-james-park_stadium.jpg", 4306, 3225,
        "Arne Müseler", "CC BY-SA 3.0 de", "https://creativecommons.org/licenses/by-sa/3.0/de/deed.en"),
    "Nott'm Forest": Stadium("City Ground", "City Ground",
        "CityGroundFromAboveTrentBridgeCricketGround.jpg", 2247, 1227,
        "Stadisimo", "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0"),
    "Sunderland": Stadium("Stadium of Light", "Stadium of Light",
        "Sunderland_stadium_of_light.jpg", 4610, 3452,
        "Arne Müseler", "CC BY-SA 3.0 de", "https://creativecommons.org/licenses/by-sa/3.0/de/deed.en"),
    "Tottenham": Stadium("Tottenham Hotspur Stadium", "Tottenham Hotspur Stadium",
        "London_Tottenham_Hotspur_Stadium.jpg", 3906, 2925,
        "Arne Müseler", "CC BY-SA 3.0 de", "https://creativecommons.org/licenses/by-sa/3.0/de/deed.en"),
}


def image_url(file: str, width: int) -> str:
    """URL de la miniatura de Commons (o del original si ya es más angosto que la miniatura).

    Commons guarda cada archivo bajo las dos primeras cifras del MD5 de su nombre: /a/ab/<archivo>.
    """
    h = hashlib.md5(file.encode("utf-8")).hexdigest()
    name = quote(file)
    if width <= THUMB_WIDTH:
        return f"{COMMONS}/{h[0]}/{h[:2]}/{name}"
    return f"{COMMONS}/thumb/{h[0]}/{h[:2]}/{name}/{THUMB_WIDTH}px-{name}"


def stadium(team: str) -> dict:
    """{"stadium": {...} o None} para un nombre canónico de Football-Data."""
    s = STADIUMS.get(team)
    if s is None:
        return {"stadium": None}
    return {"stadium": {
        "name": s.name,
        "image": image_url(s.file, s.width),
        "credit": {"author": s.author, "license": s.license, "license_url": s.license_url,
                   "source": f"https://commons.wikimedia.org/wiki/File:{quote(s.file)}"},
        "wikipedia": f"https://en.wikipedia.org/wiki/{quote(s.article.replace(' ', '_'))}",
    }}


def verify() -> list[str]:
    """Vuelve a consultar Commons: cada archivo existe, con el tamaño y la licencia registrados, y su miniatura carga."""
    ua = {"User-Agent": "futbol-predict/1.0 (https://github.com/IgnacioGil23/futbol-predict)"}
    problems = []
    for team, s in STADIUMS.items():
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers=ua, timeout=30, params={
            "action": "query", "prop": "imageinfo", "iiprop": "extmetadata|size", "titles": f"File:{s.file}",
            "format": "json", "formatversion": 2}).json()
        info = r["query"]["pages"][0].get("imageinfo")
        if not info:
            problems.append(f"{team}: no existe File:{s.file}")
            continue
        license = info[0]["extmetadata"].get("LicenseShortName", {}).get("value")
        if (info[0]["width"], info[0]["height"]) != (s.width, s.height) or license != s.license:
            problems.append(f"{team}: cambió el archivo o la licencia ({license})")
        if requests.head(image_url(s.file, s.width), headers=ua, timeout=30, allow_redirects=True).status_code != 200:
            problems.append(f"{team}: la miniatura no carga")
    return problems


if __name__ == "__main__":
    found = verify()
    print("\n".join(found) or f"Los {len(STADIUMS)} estadios siguen verificados.")
    sys.exit(1 if found else 0)
