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


def canonical_team(name: object) -> object:
    if not isinstance(name, str):
        return pd.NA if name is None or pd.isna(name) else name
    name = name.strip()
    return TEAM_ALIASES.get(name, name)
