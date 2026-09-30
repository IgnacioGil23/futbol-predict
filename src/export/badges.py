"""Identificación visual de los equipos en la web: escudo oficial o iniciales.

* Escudo: la imagen que sirve la Premier League para su código de equipo (el mismo código estable que usa Fantasy
  Premier League). Solo para los equipos cuyo código está verificado en el archivo de Fantasy (desde 2019-20 trae la
  columna de código): los 27 de src/data/fpl_archive.FPL_TEAM_CODES más West Brom, Norwich y Watford. Las 30 imágenes
  se verificaron el 30/09/2026. Los escudos son marcas registradas de cada club; se muestran solo como referencia visual.
* Iniciales: para los demás (equipos que no jugaron la Premier desde 2019-20), las tres primeras letras del nombre, con
  los colores neutros del sitio. No se usan colores de clubes para no inventar datos.
"""

from src.data.fpl_archive import FPL_TEAM_CODES

BADGE_URL = "https://resources.premierleague.com/premierleague/badges/70/t{code}.png"
BADGE_CODES: dict[str, int] = {team: code for code, team in FPL_TEAM_CODES.items()} | {
    "West Brom": 35, "Norwich": 45, "Watford": 57,
}
# Abreviatura de tres letras de Fantasy Premier League (archivo vaastav, teams.csv).
SHORT_NAMES: dict[str, str] = {
    "Man United": "MUN", "Leeds": "LEE", "Arsenal": "ARS", "Newcastle": "NEW", "Tottenham": "TOT",
    "Aston Villa": "AVL", "Chelsea": "CHE", "Coventry": "COV", "Everton": "EVE", "Leicester": "LEI",
    "Liverpool": "LIV", "Nott'm Forest": "NFO", "Southampton": "SOU", "West Ham": "WHU", "Crystal Palace": "CRY",
    "West Brom": "WBA", "Brighton": "BHA", "Wolves": "WOL", "Ipswich": "IPS", "Man City": "MCI", "Norwich": "NOR",
    "Sheffield United": "SHU", "Fulham": "FUL", "Sunderland": "SUN", "Watford": "WAT", "Hull": "HUL",
    "Burnley": "BUR", "Bournemouth": "BOU", "Brentford": "BRE", "Luton": "LUT",
    # Sin abreviatura de Fantasy: la regla de las tres primeras letras daría "BLA" a los dos.
    "Blackburn": "BLB", "Blackpool": "BLP",
}


def badge(team: str) -> dict:
    """{"badge": url o None, "short": abreviatura de tres letras} para un nombre canónico."""
    code = BADGE_CODES.get(team)
    short = SHORT_NAMES.get(team) or "".join(c for c in team if c.isalpha())[:3].upper()
    return {"badge": BADGE_URL.format(code=code) if code is not None else None, "short": short}
