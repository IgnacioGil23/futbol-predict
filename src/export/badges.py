"""Iniciales de los equipos de la Premier en la web (abreviatura de tres letras, con los colores neutros del sitio).

Los escudos salen de Wikimedia Commons con licencia libre (src/export/league_media.py), igual que en las otras ligas.
Hasta el 28/10/2026 se mostraban los de premierleague.com, pero sus términos no permiten usarlos sin autorización
escrita del titular: se dejaron de usar. No se usan colores de clubes para no inventar datos.
"""

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
    """{"badge": None, "short": abreviatura de tres letras} para un nombre canónico (el escudo lo pone league_media)."""
    short = SHORT_NAMES.get(team) or "".join(c for c in team if c.isalpha())[:3].upper()
    return {"badge": None, "short": short}
