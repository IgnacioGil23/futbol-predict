"""Nombres canónicos de equipos.

El nombre canónico es el que usa Football-Data.co.uk (fuente base). Todas las
variantes conocidas se mapean a él para que la tabla de posiciones, el
head-to-head y el Elo no traten a un mismo club como dos equipos distintos.
"""

import pandas as pd

# Variante -> nombre canónico de Football-Data.
TEAM_ALIASES: dict[str, str] = {
    # El dataset de Adam Gábor usa "Nottm Forest" en 2022/23-2024/25.
    "Nottm Forest": "Nott'm Forest",
}


# Nombre para mostrar en la web de los clubes que jugaron la Premier desde 2000-01.
# Los que no figuran se muestran con el nombre de Football-Data.
DISPLAY_NAMES: dict[str, str] = {
    "Birmingham": "Birmingham City", "Blackburn": "Blackburn Rovers", "Bolton": "Bolton Wanderers",
    "Bournemouth": "AFC Bournemouth", "Bradford": "Bradford City", "Brighton": "Brighton & Hove Albion",
    "Cardiff": "Cardiff City", "Charlton": "Charlton Athletic", "Coventry": "Coventry City",
    "Derby": "Derby County", "Huddersfield": "Huddersfield Town", "Hull": "Hull City",
    "Ipswich": "Ipswich Town", "Leeds": "Leeds United", "Leicester": "Leicester City", "Luton": "Luton Town",
    "Man City": "Manchester City", "Man United": "Manchester United", "Newcastle": "Newcastle United",
    "Norwich": "Norwich City", "Nott'm Forest": "Nottingham Forest", "QPR": "Queens Park Rangers",
    "Stoke": "Stoke City", "Swansea": "Swansea City", "Tottenham": "Tottenham Hotspur",
    "West Brom": "West Bromwich Albion", "West Ham": "West Ham United", "Wigan": "Wigan Athletic",
    "Wolves": "Wolverhampton Wanderers",
}


def display_name(team: str) -> str:
    return DISPLAY_NAMES.get(team, team)


def slug(team: str) -> str:
    """Identificador para URLs y nombres de archivo: "Nott'm Forest" -> "nottm-forest"."""
    out = "".join(c.lower() if c.isalnum() else ("-" if c in " &" else "") for c in team)
    return "-".join(p for p in out.split("-") if p)


def canonical_team(name: object) -> object:
    if not isinstance(name, str):
        return pd.NA if name is None or pd.isna(name) else name
    name = name.strip()
    return TEAM_ALIASES.get(name, name)
