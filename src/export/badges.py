"""Identificación visual de los equipos en la web: escudo oficial o iniciales.

* Escudo: la imagen que sirve la Premier League para el código estable de cada club (el número de la URL de sus
  escudos). Solo para los 30 clubes cuyo código se verificó; las 30 imágenes se comprobaron el 30/09/2026. Los escudos
  son marcas registradas de cada club; se muestran solo como referencia visual.
* Iniciales: para los demás (equipos que no jugaron la Premier desde 2019-20), una abreviatura de tres letras, con los
  colores neutros del sitio. No se usan colores de clubes para no inventar datos.
"""

BADGE_URL = "https://resources.premierleague.com/premierleague/badges/70/t{code}.png"
# Código de club de la Premier League -> nombre canónico de Football-Data.
BADGE_CODES: dict[str, int] = {
    "Man United": 1, "Leeds": 2, "Arsenal": 3, "Newcastle": 4, "Tottenham": 6, "Aston Villa": 7, "Chelsea": 8,
    "Coventry": 9, "Everton": 11, "Leicester": 13, "Liverpool": 14, "Nott'm Forest": 17, "Southampton": 20,
    "West Ham": 21, "Crystal Palace": 31, "West Brom": 35, "Brighton": 36, "Wolves": 39, "Ipswich": 40,
    "Man City": 43, "Norwich": 45, "Sheffield United": 49, "Fulham": 54, "Sunderland": 56, "Watford": 57,
    "Hull": 88, "Burnley": 90, "Bournemouth": 91, "Brentford": 94, "Luton": 102,
}
# Abreviatura de tres letras de cada club.
SHORT_NAMES: dict[str, str] = {
    "Man United": "MUN", "Leeds": "LEE", "Arsenal": "ARS", "Newcastle": "NEW", "Tottenham": "TOT",
    "Aston Villa": "AVL", "Chelsea": "CHE", "Coventry": "COV", "Everton": "EVE", "Leicester": "LEI",
    "Liverpool": "LIV", "Nott'm Forest": "NFO", "Southampton": "SOU", "West Ham": "WHU", "Crystal Palace": "CRY",
    "West Brom": "WBA", "Brighton": "BHA", "Wolves": "WOL", "Ipswich": "IPS", "Man City": "MCI", "Norwich": "NOR",
    "Sheffield United": "SHU", "Fulham": "FUL", "Sunderland": "SUN", "Watford": "WAT", "Hull": "HUL",
    "Burnley": "BUR", "Bournemouth": "BOU", "Brentford": "BRE", "Luton": "LUT",
    # La regla de las tres primeras letras daría "BLA" a los dos.
    "Blackburn": "BLB", "Blackpool": "BLP",
}


def badge(team: str) -> dict:
    """{"badge": url o None, "short": abreviatura de tres letras} para un nombre canónico."""
    code = BADGE_CODES.get(team)
    short = SHORT_NAMES.get(team) or "".join(c for c in team if c.isalpha())[:3].upper()
    return {"badge": BADGE_URL.format(code=code) if code is not None else None, "short": short}
